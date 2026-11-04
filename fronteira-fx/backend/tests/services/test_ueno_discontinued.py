"""ueno saiu do monitor (resolução do Banco Central del Paraguay em 03/11/2026): não é sondada, não entra em novos
ciclos e não é mais banco de recebimento padrão no demo. O histórico continua consultável."""

from __future__ import annotations

from fronteira_fx.adapters import registry
from fronteira_fx.schemas_candles import HouseHours
from fronteira_fx.services import demo
from fronteira_fx.services import market_hours as mh


def test_ueno_adapter_module_is_kept_for_history_but_out_of_the_registry():
    from fronteira_fx.adapters import ueno

    # o módulo fica como histórico (parsers e fixtures); o registro não o carrega mais
    assert ueno.adapter.info.discontinued is True
    assert "ueno" not in registry.ADAPTERS
    assert all(not a.info.discontinued for a in registry.ADAPTERS.values())


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


def test_market_hours_file_has_no_ueno_and_only_verified_houses():
    # contrato (Pregão): casa sem horário verificado não entra no arquivo; ueno sai do monitor e não tem horário
    hours = mh.load_market_hours()
    assert "ueno" not in hours
    assert all(isinstance(h, HouseHours) for h in hours.values())
    assert all(h.verified is True for h in hours.values())
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
