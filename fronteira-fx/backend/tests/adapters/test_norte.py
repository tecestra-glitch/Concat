from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from fronteira_fx.adapters import norte
from fronteira_fx.adapters.base import AdapterStatus

from .conftest import load, without_tables

URL = norte.HOME_URL


def test_parse_home_active_branch(captured_at: datetime) -> None:
    fresh = datetime(2026, 10, 31, 16, 0, tzinfo=UTC)
    res = norte.adapter.parse(load("norte.html"), captured_at=fresh, url=URL)
    assert res.status == AdapterStatus.OK, res.message
    assert len(res.quotes) == 2
    usd = next(q for q in res.quotes if q.base == "USD")
    brl = next(q for q in res.quotes if q.base == "BRL")
    assert (usd.buy, usd.sell) == (Decimal("5760"), Decimal("5950"))
    assert (brl.buy, brl.sell) == (Decimal("1080"), Decimal("1140"))
    assert usd.branch_id == "norte-1" and usd.city == "PJC" and usd.quote == "PYG"
    assert usd.unit_note == "PYG por 1 USD" and brl.unit_note == "PYG por 1 BRL"
    assert usd.declared_updated_at == datetime(2026, 10, 31, 14, 24, 14, tzinfo=UTC)
    assert usd.modality == "cash" and usd.channel == "physical"
    assert res.evidence is not None and res.evidence.kind == "html"
    # cross rates like "BRL•USD" (5,22 / 5,44) must not become PYG quotes
    assert all(q.buy > 100 for q in res.quotes)


def test_branch_tabs_and_cities() -> None:
    branches = norte._branches_from_html(load("norte.html"))
    assert branches["1"].city == "PJC" and branches["1"].name == "Pedro Juan Caballero"
    assert branches["2"].city == "ASU" and branches["2"].name == "Asunción"
    assert branches["3"].city == "CDE" and branches["3"].name == "Ciudad del Este"
    assert branches["4"].city is None  # Bella Vista Norte


def test_livewire_fragment_for_other_branch(captured_at: datetime) -> None:
    html = load("norte.html")
    table = re.search(r"<table\b.*?</table>", html, flags=re.S).group(0)
    payload = json.dumps({"components": [{"snapshot": "{}", "effects": {"html": f"<div>{table}</div>"}}]})
    res = norte.adapter.parse(
        payload, captured_at=datetime(2026, 10, 31, 16, 0, tzinfo=UTC), url=norte.LIVEWIRE_URL, branch_id="3"
    )
    assert res.status == AdapterStatus.OK, res.message
    assert {q.branch_id for q in res.quotes} == {"norte-3"} and {q.city for q in res.quotes} == {"CDE"}
    bad = norte.adapter.parse(
        json.dumps({"components": []}), captured_at=captured_at, url=norte.LIVEWIRE_URL, branch_id="3"
    )
    assert bad.status == AdapterStatus.ERROR


def test_stale(captured_at: datetime) -> None:
    # fixture declared 2026-10-31T14:24Z; captured 2026-11-02T06Z -> 39.6h > 36h
    res = norte.adapter.parse(load("norte.html"), captured_at=captured_at, url=URL)
    assert res.status == AdapterStatus.STALE and len(res.quotes) == 2


def test_layout_change(captured_at: datetime) -> None:
    assert norte.adapter.parse("", captured_at=captured_at, url=URL).status == AdapterStatus.ERROR
    res = norte.adapter.parse(without_tables(load("norte.html")), captured_at=captured_at, url=URL)
    assert res.status == AdapterStatus.ERROR and res.quotes == [] and "table" in (res.message or "")


def test_tls_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FX_NORTE_CA_BUNDLE", raising=False)
    monkeypatch.delenv("FX_NORTE_INSECURE", raising=False)
    assert norte.tls_verify_setting() == (True, None)
    monkeypatch.setenv("FX_NORTE_INSECURE", "1")
    verify, note = norte.tls_verify_setting()
    assert verify is False and note and "DISABLED" in note
    monkeypatch.setenv("FX_NORTE_CA_BUNDLE", "/tmp/bundle.pem")
    assert norte.tls_verify_setting() == ("/tmp/bundle.pem", None)
    assert norte.TLS_MESSAGE == "TLS chain invalid; set FX_NORTE_CA_BUNDLE or allow insecure explicitly"


@pytest.mark.asyncio
async def test_fetch_reports_tls_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    from fronteira_fx.adapters._http import HttpOutcome

    monkeypatch.delenv("FX_NORTE_CA_BUNDLE", raising=False)
    monkeypatch.delenv("FX_NORTE_INSECURE", raising=False)

    async def fake_get(url, **kwargs):  # noqa: ANN001, ANN202
        return HttpOutcome(
            ok=False,
            status_code=None,
            text="",
            url=url,
            error="TLS verification failed: CERTIFICATE_VERIFY_FAILED",
            tls_error=True,
        )

    monkeypatch.setattr(norte, "http_get", fake_get)
    res = await norte.adapter.fetch()
    assert res.status == AdapterStatus.ERROR
    assert res.message is not None and res.message.startswith(norte.TLS_MESSAGE)
