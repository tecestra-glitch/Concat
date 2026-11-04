"""ueno saiu do monitor (resolução do Banco Central del Paraguay em 03/11/2026): não é sondada, não entra em novos
ciclos e não é mais banco de recebimento padrão no demo. O histórico continua consultável."""

from __future__ import annotations

from fronteira_fx.adapters import registry
from fronteira_fx.schemas_candles import HouseHours
from fronteira_fx.services import demo
from fronteira_fx.services import market_hours as mh


def test_ueno_adapter_is_marked_discontinued_but_kept_for_history():
    assert "ueno" in registry.ADAPTERS  # o histórico e os testes de parser continuam
    assert registry.ADAPTERS["ueno"].info.discontinued is True
    assert all(not a.info.discontinued for a in registry.ADAPTERS.values() if a.info.id != "ueno")


def test_active_adapters_leave_ueno_out_of_polling():
    active = registry.active_adapters()
    assert "ueno" not in active
    assert set(active) == set(registry.ADAPTERS) - {"ueno"}
    assert list(active) == sorted(active)


def test_collector_and_watch_poll_only_active_adapters():
    from fronteira_fx.services import collector
    from fronteira_fx.watch import service as watch_service

    assert "ueno" not in collector.load_registry()
    assert "ueno" not in watch_service.load_registry()


def test_market_hours_flag_marks_ueno_discontinued_and_others_are_untouched():
    hours = mh.load_market_hours()
    assert isinstance(hours["ueno"], HouseHours)
    assert hours["ueno"].discontinued is True
    assert hours["nomad"].discontinued is False
    assert hours["chaco"].discontinued is False


def test_demo_has_no_ueno_account_and_uses_generic_py_bank_or_revolut():
    institutions = {a["institution"] for a in demo.ACCOUNTS}
    assert "ueno" not in institutions
    assert {"banco_py", "revolut", "nomad"} <= institutions
    currencies_revolut = {a["currency"] for a in demo.ACCOUNTS if a["institution"] == "revolut"}
    assert currencies_revolut == {"USD", "BRL"}  # Revolut guarda USD e BRL, não PYG


def test_demo_receiving_bank_is_never_ueno():
    specs = demo.QUOTE_SPECS
    banks = {q["context"]["bank"] for q in specs if q.get("context") and q["context"].get("bank")}
    assert "ueno" not in banks
    assert "banco_py" in banks  # o banco PY genérico recebe o WU em PYG
    assert "ueno" not in {q.get("source_id") for q in specs}
    assert "ueno" not in {s["id"] for s in demo.SOURCES}


def test_demo_pregao_has_no_ueno_house():
    # o monitor do pregão demo não lista o ueno (o frontend demo também não); o histórico real continua
    from datetime import UTC, datetime

    from fronteira_fx.services.candles_demo import demo_house_sessions

    ids = {s.source_id for s in demo_house_sessions(datetime(2026, 11, 4, 12, tzinfo=UTC))}
    assert "demo-ueno" not in ids
    assert "demo-chaco" in ids and "demo-nomad" in ids


def test_real_pregao_sessions_leave_discontinued_houses_out(app, client, db):
    from fronteira_fx.api.candles import router
    from tests.api.test_candles_api import _mount
    from tests.conftest import seed_market

    _mount(app)
    seed_market(db)
    ids = [s["source_id"] for s in client.get("/v1/pregao/sessions").json()]
    assert "ueno" not in ids and "chaco" in ids
    assert router is not None


def test_sources_list_flags_the_discontinued_source(app, client, db):
    from tests.conftest import seed_market

    seed_market(db)
    rows = {s["id"]: s for s in client.get("/v1/sources").json()}
    assert rows["ueno"]["discontinued"] is True
    assert rows["wu"]["discontinued"] is False
