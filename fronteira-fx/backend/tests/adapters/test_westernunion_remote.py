"""Western Union through the mini navegador (fronteira-fx/browser): transport mocked with respx, no network."""

from __future__ import annotations

import base64
import builtins
import json
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
import respx

from fronteira_fx.adapters import westernunion as wu
from fronteira_fx.adapters.base import AdapterStatus
from fronteira_fx.config import Settings

from .conftest import load

FIXTURE = "westernunion_5000_brl_pyg.json"
BASE = "https://fx-browser.example"
ENDPOINT = f"{BASE}/api/westernunion"
SECRET = "segredo-de-teste-remoto"  # test value only
PNG = b"\x89PNG\r\n\x1a\nfake-png"


def _settings(**overrides) -> Settings:
    base = dict(FX_BROWSER_URL=BASE, FX_BROWSER_SECRET=SECRET, evidence_dir=None)
    base.update(overrides)
    return Settings(_env_file=None, database_url="sqlite://", **{k: v for k, v in base.items() if v is not None})


@pytest.fixture
def remote(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Remote mode on, evidence written under tmp_path."""
    monkeypatch.setenv("EVIDENCE_DIR", str(tmp_path / "evidence"))
    monkeypatch.setattr(wu, "get_settings", lambda: _settings())
    return tmp_path / "evidence"


def _scenario(**overrides) -> dict:
    sc = json.loads(load(FIXTURE))["scenarios"][0]
    sc["captured_at"] = datetime.now(UTC).isoformat()
    sc.update(overrides)
    return sc


def _ok_body(scenario: dict | None = None, *, png: bool = True) -> dict:
    body = {
        "status": "ok",
        "message": "quote read",
        "trail": ["goto=200", "tile:Paraguai", "amount=5000", "receive=5,401,871.00"],
        "scenario": scenario if scenario is not None else _scenario(),
    }
    if png:
        body["screenshot_png_b64"] = base64.b64encode(PNG).decode()
    return body


async def _fetch():
    return await wu.adapter.fetch(amount_brl="5000", payment="pix", receive="bank_account")


@respx.mock
async def test_remote_ok_parses_scenario_and_stores_screenshot(remote) -> None:
    route = respx.post(ENDPOINT).mock(return_value=httpx.Response(200, json=_ok_body()))
    res = await _fetch()

    assert res.status == AdapterStatus.OK, res.message
    assert res.quotes[0].buy == Decimal("1080.3742")  # 5,401,871 / 5,000
    assert res.quotes[0].context["payment"] == "pix" and res.quotes[0].context["receive"] == "bank_account"
    assert res.evidence is not None and res.evidence.kind == "screenshot"
    assert res.evidence.raw_path and res.evidence.raw_path.startswith(str(remote))
    assert (remote).exists() and any(p.read_bytes() == PNG for p in remote.iterdir())
    assert "remoto" in (res.message or "")

    sent = route.calls.last.request
    assert sent.headers["Authorization"] == f"Bearer {SECRET}"
    body = json.loads(sent.content)
    assert body == {"amount_brl": "5000", "payment": "pix", "receive": "bank_account", "screenshot": True}
    assert "url" not in body  # nunca um URL do cliente


@respx.mock
async def test_remote_ok_without_screenshot_is_json_evidence(remote) -> None:
    respx.post(ENDPOINT).mock(return_value=httpx.Response(200, json=_ok_body(png=False)))
    res = await _fetch()
    assert res.status == AdapterStatus.OK
    assert res.evidence is not None and res.evidence.kind == "json"


@respx.mock
async def test_remote_cannot_change_the_request_context(remote) -> None:
    respx.post(ENDPOINT).mock(
        return_value=httpx.Response(200, json=_ok_body(_scenario(amount_brl="1", payment="card", receive="cash_pickup")))
    )
    res = await _fetch()
    assert res.status == AdapterStatus.OK
    ctx = res.quotes[0].context
    assert ctx["amount_brl"] == "5000" and ctx["payment"] == "pix" and ctx["receive"] == "bank_account"


@pytest.mark.parametrize(
    ("code", "fragment"),
    [(401, "401"), (404, "404"), (400, "HTTP 400")],
)
@respx.mock
async def test_remote_http_errors_are_error_status(remote, code: int, fragment: str) -> None:
    respx.post(ENDPOINT).mock(return_value=httpx.Response(code, json={"error": "x"}))
    res = await _fetch()
    assert res.status == AdapterStatus.ERROR and fragment in (res.message or "")
    assert res.quotes == []


@respx.mock
async def test_remote_blocked_maps_to_blocked(remote) -> None:
    respx.post(ENDPOINT).mock(
        return_value=httpx.Response(200, json={"status": "blocked", "message": "anti-bot page", "trail": ["goto=200"]})
    )
    res = await _fetch()
    assert res.status == AdapterStatus.BLOCKED and "anti-bot page" in (res.message or "")
    assert res.quotes == [] and res.evidence is None


@respx.mock
async def test_remote_degraded_maps_to_degraded(remote) -> None:
    respx.post(ENDPOINT).mock(
        return_value=httpx.Response(200, json={"status": "degraded", "message": "country tile not found", "trail": []})
    )
    res = await _fetch()
    assert res.status == AdapterStatus.DEGRADED and "country tile" in (res.message or "")


@respx.mock
async def test_remote_error_status_and_missing_scenario(remote) -> None:
    respx.post(ENDPOINT).mock(return_value=httpx.Response(200, json={"status": "error", "message": "ReferenceError"}))
    assert (await _fetch()).status == AdapterStatus.ERROR

    respx.post(ENDPOINT).mock(return_value=httpx.Response(200, json={"status": "ok", "message": "x"}))
    res = await _fetch()
    assert res.status == AdapterStatus.ERROR and "scenario" in (res.message or "")


@respx.mock
async def test_remote_timeout_and_network_failures_do_not_raise(remote) -> None:
    respx.post(ENDPOINT).mock(side_effect=httpx.ReadTimeout("slow"))
    res = await _fetch()
    assert res.status == AdapterStatus.ERROR and "tempo esgotado" in (res.message or "")

    respx.post(ENDPOINT).mock(side_effect=httpx.ConnectError("refused"))
    res = await _fetch()
    assert res.status == AdapterStatus.ERROR and "inacessível" in (res.message or "")


@respx.mock
async def test_remote_non_json_is_error(remote) -> None:
    respx.post(ENDPOINT).mock(return_value=httpx.Response(200, text="<html>oops</html>"))
    res = await _fetch()
    assert res.status == AdapterStatus.ERROR and "não é JSON" in (res.message or "")


@respx.mock
async def test_remote_never_follows_redirects_with_the_secret(remote) -> None:
    redirect = respx.post(ENDPOINT).mock(return_value=httpx.Response(302, headers={"Location": "https://other.example"}))
    res = await _fetch()
    assert res.status == AdapterStatus.ERROR and "HTTP 302" in (res.message or "")
    assert redirect.call_count == 1
    assert respx.calls.call_count == 1  # the Bearer never followed the redirect


async def test_without_remote_config_nothing_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    """No FX_BROWSER_URL / FX_BROWSER_SECRET: the local Playwright path runs, and the remote path is never called."""
    monkeypatch.setattr(wu, "get_settings", lambda: _settings(FX_BROWSER_URL=None, FX_BROWSER_SECRET=None))

    def boom(*_a, **_k):
        raise AssertionError("remote path must not run without configuration")

    monkeypatch.setattr(wu.WesternUnionAdapter, "_fetch_remote", boom)
    real_import = builtins.__import__

    def no_playwright(name, *args, **kwargs):
        if name.startswith("playwright"):
            raise ImportError("no playwright")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_playwright)
    res = await _fetch()
    assert res.status == AdapterStatus.DEGRADED and "playwright" in (res.message or "").lower()
