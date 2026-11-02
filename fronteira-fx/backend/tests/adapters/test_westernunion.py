from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from fronteira_fx.adapters import westernunion as wu
from fronteira_fx.adapters.base import AdapterStatus

from .conftest import load

FIXTURE = "westernunion_5000_brl_pyg.json"
URL = wu.START_URL


def test_fixture_is_marked_historical() -> None:
    data = json.loads(load(FIXTURE))
    assert data["historical"] is True and "historical" in data["note"].lower()


def test_parse_two_receive_methods(captured_at: datetime) -> None:
    res = wu.adapter.parse(load(FIXTURE), captured_at=captured_at, url=URL)
    # historical data is never served as current
    assert res.status == AdapterStatus.STALE and "historical" in (res.message or "")
    assert len(res.quotes) == 2
    bank = next(q for q in res.quotes if q.context and q.context["receive"] == "bank_account")
    cash = next(q for q in res.quotes if q.context and q.context["receive"] == "cash_pickup")

    # effective rate = receive / amount
    assert bank.amount_base == Decimal("5000") and bank.base == "BRL" and bank.quote == "PYG"
    assert bank.buy == Decimal("1080.3742")  # 5,401,871 / 5,000
    assert bank.sell is None and "PYG por 1 BRL" in bank.unit_note
    assert cash.buy == Decimal("1065.6418")  # 5,328,209 / 5,000
    assert bank.buy != cash.buy

    # the two receive methods are different quotes with different, complete contexts
    assert bank.context != cash.context
    assert bank.context["delivery"] == "0–4 dias úteis" and cash.context["delivery"] == "minutos"
    for q in (bank, cash):
        assert q.context is not None
        assert q.context["origin"] == "BR" and q.context["destination"] == "PY"
        assert q.context["send_currency"] == "BRL" and q.context["receive_currency"] == "PYG"
        assert q.context["amount_brl"] == "5000" and q.context["payment"] == "pix"
        assert q.context["bank"] is None and q.context["channel"] == "web"
        assert q.context["promo"] == "100% desconto na tarifa"
        assert q.fees and q.fees[0].amount == Decimal("0") and q.fees[0].currency == "BRL"
        assert q.kind == "indicative" and q.channel == "digital" and q.city is None
    assert bank.modality == "transfer" and cash.modality == "cash"
    assert res.evidence is not None and res.evidence.kind == "json" and "bank_account" in res.evidence.excerpt


def test_single_live_scenario_is_ok() -> None:
    now = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
    sc = json.loads(load(FIXTURE))["scenarios"][0]
    sc["captured_at"] = now.isoformat()
    res = wu.adapter.parse(json.dumps(sc), captured_at=now, url=URL)
    assert res.status == AdapterStatus.OK, res.message
    assert res.quotes[0].buy == Decimal("1080.3742") and res.quotes[0].declared_updated_at == now


def test_screenshot_evidence_kind() -> None:
    now = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
    sc = json.loads(load(FIXTURE))["scenarios"][1]
    sc["captured_at"] = now.isoformat()
    res = wu.adapter.parse(json.dumps(sc), captured_at=now, url=URL, screenshot_path="/tmp/x.png",
                           screenshot_bytes=b"png")
    assert res.evidence is not None and res.evidence.kind == "screenshot" and res.evidence.raw_path == "/tmp/x.png"


def test_bad_payloads(captured_at: datetime) -> None:
    assert wu.adapter.parse("", captured_at=captured_at, url=URL).status == AdapterStatus.ERROR
    assert wu.adapter.parse("{}", captured_at=captured_at, url=URL).status == AdapterStatus.ERROR
    html = wu.adapter.parse("<html>spa</html>", captured_at=captured_at, url=URL)
    assert html.status == AdapterStatus.DEGRADED and html.quotes == []
    missing = json.dumps({"scenarios": [{"amount_brl": "5000", "receive": "bank_account", "payment": "pix"}]})
    res = wu.adapter.parse(missing, captured_at=captured_at, url=URL)
    assert res.status == AdapterStatus.ERROR and res.quotes == []  # no receive value -> no invented rate
    zero = json.dumps({"amount_brl": "5000", "receive_amount_pyg": "0", "receive": "bank_account", "payment": "pix"})
    assert wu.adapter.parse(zero, captured_at=captured_at, url=URL).status == AdapterStatus.ERROR


def test_unknown_method_is_degraded() -> None:
    now = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
    sc = json.loads(load(FIXTURE))["scenarios"][0]
    sc["captured_at"] = now.isoformat()
    sc["receive"] = "pigeon"
    res = wu.adapter.parse(json.dumps(sc), captured_at=now, url=URL)
    assert res.status == AdapterStatus.DEGRADED and "pigeon" in (res.message or "")


@pytest.mark.asyncio
async def test_fetch_without_playwright_is_degraded(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):  # noqa: ANN001, ANN202
        if name.startswith("playwright"):
            raise ImportError("no playwright")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    res = await wu.adapter.fetch(amount_brl="5000", payment="pix", receive="bank_account")
    assert res.status == AdapterStatus.DEGRADED and "playwright" in (res.message or "").lower()


@pytest.mark.asyncio
async def test_fetch_rejects_bad_params() -> None:
    assert (await wu.adapter.fetch(amount_brl="abc")).status == AdapterStatus.ERROR
    assert (await wu.adapter.fetch(receive="pigeon")).status == AdapterStatus.ERROR  # type: ignore[arg-type]


def test_evidence_dir_is_gitignored() -> None:
    gitignore = wu.evidence_dir().parent / ".gitignore"
    assert gitignore.read_text().splitlines()[0].strip() == "*"  # everything under var/ is ignored
    assert wu.evidence_dir().parts[-2:] == ("var", "evidence")
