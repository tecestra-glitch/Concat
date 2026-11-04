"""Referências de câmbio (U03): Frankfurter, PTAX e Open Exchange Rates. HTTP mockado (respx), sem rede.

Cobre: toda cotação é referência (referencia=true, fonte e data de coleta); alerta de desvio só acima do limite;
contador da OXR nunca passa de 1.000 no mês; chave só na query e nunca em erro; sem chave a fonte fica desligada.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import func, select

from fronteira_fx.config import Settings
from fronteira_fx.market import quotes as q
from fronteira_fx.market import reference as ref
from fronteira_fx.market.service import EVENT_REFERENCE_DEVIATION, FX_SOURCE, MarketPoller
from fronteira_fx.models import FxReferenceQuote, ReferenceApiUsage
from fronteira_fx.services import events as events_svc

from .conftest import read_fixture

T0 = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
SECRET = "TESTE-CHAVE-OXR-0000"  # chave falsa, só para o teste de vazamento
ROOT = Path(__file__).resolve().parents[2]


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def settings(*, key: str | None = None, cap: int = 1000, threshold: str = "1.0") -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite://",
        data_mode="real",
        seed_demo=False,
        seed_knowledge=False,
        oxr_app_id=key,
        oxr_monthly_cap=cap,
        fx_reference_deviation_alert_pct=Decimal(threshold),
        quotes_lookback_s=10 * 365 * 86400,
    )


def make_poller(factory, clock: Clock, cfg: Settings, *, keep: set[str] | None = None) -> MarketPoller:
    poller = MarketPoller(factory, cfg, clock=clock)
    for source in poller.scheduler.sources():
        if keep is not None and source.source_id not in keep:
            poller.scheduler.remove_source(source.source_id)
    return poller


def oxr_payload(*, brl: str = "5.4", ts: int = 1793793600) -> dict:
    return {"base": "USD", "timestamp": ts, "rates": {"BRL": float(brl), "PYG": 5950.0, "EUR": 0.92}}


# ------------------------------------------------------------------ parsers e flags
def test_oxr_parse_marks_every_quote_as_reference_and_inverts_eur(tmp_path):
    data = q.loads_exact(read_fixture("oxr_latest.json").decode())
    collected = T0
    quotes = ref.parse_oxr_latest(data, collected_at=collected)
    by = {qt.instrument: qt for qt in quotes}
    assert set(by) == {"USD/BRL", "USD/PYG", "EUR/USD"}
    assert all(qt.referencia is True and qt.source == ref.OXR_SOURCE for qt in quotes)
    assert all(qt.collected_at == collected for qt in quotes)
    assert by["USD/BRL"].price == Decimal("5.4")
    assert by["EUR/USD"].price == Decimal(1) / Decimal("0.92")
    assert by["USD/BRL"].observed_at == datetime.fromtimestamp(1793793600, tz=UTC)


def test_oxr_rejects_non_usd_base():
    with pytest.raises(q.FeedFormatError):
        ref.parse_oxr_latest({"base": "EUR", "timestamp": 1, "rates": {}}, collected_at=T0)


def test_reference_quote_is_always_reference_and_read_only():
    qt = ref.ReferenceQuote("USD/BRL", "frankfurter", Decimal("5.4"), T0, T0)
    assert qt.referencia is True
    with pytest.raises(AttributeError):
        qt.referencia = False  # type: ignore[misc]
    with pytest.raises(ValueError):
        ref.ReferenceQuote("USD/BRL", "frankfurter", Decimal("0"), T0, T0)


def test_frankfurter_and_ptax_drafts_become_reference_rows_only_for_fx():
    drafts = q.parse_frankfurter(q.loads_exact(read_fixture("frankfurter_v2_rates.json").decode()))
    fx = ref.from_frankfurter_drafts(drafts, collected_at=T0)
    assert fx and all(qt.source == ref.FRANKFURTER_SOURCE and qt.referencia for qt in fx)
    bcb = [
        q.parse_bcb_series(q.loads_exact(read_fixture("bcb_sgs_1_ultimos2.json").decode()), "PTAX venda", "x"),
        q.parse_bcb_series(q.loads_exact(read_fixture("bcb_sgs_432_ultimo.json").decode()), "Selic meta", "y"),
    ]
    ptax = ref.from_bcb_drafts(bcb, collected_at=T0)
    assert [qt.instrument for qt in ptax] == ["USD/BRL"] and ptax[0].source == ref.PTAX_SOURCE


def test_bcb_window_is_at_most_ninety_days_in_brasilia_dates():
    start, end = q.bcb_window(datetime(2026, 11, 4, 2, 0, tzinfo=UTC))  # 03/11 23:00 em Brasília
    assert end == "03/11/2026"
    assert start == "05/08/2026"  # 90 dias antes de 03/11/2026
    url = q.BCB_SGS_URL.format(code=1, start=start, end=end)
    assert "dataInicial=05/08/2026" in url and "dataFinal=03/11/2026" in url


# ------------------------------------------------------------------ desvio
def test_deviation_math_and_strict_threshold():
    assert ref.deviation_pct(Decimal("5.50"), Decimal("5.00")) == Decimal("10")
    qa = ref.ReferenceQuote("USD/BRL", "a", Decimal("5.00"), T0, T0)
    qb = ref.ReferenceQuote("USD/BRL", "b", Decimal("5.00"), T0, T0)
    assert [d.over for d in ref.compare(ref.latest_by_source([qa, qb]), Decimal("1.0"))] == [False]
    qc = ref.ReferenceQuote("USD/BRL", "b", Decimal("5.05"), T0, T0)  # exatamente 1,0 %: não passa do limite
    assert [d.over for d in ref.compare(ref.latest_by_source([qa, qc]), Decimal("1.0"))] == [False]
    qd = ref.ReferenceQuote("USD/BRL", "b", Decimal("5.06"), T0, T0)
    assert [d.over for d in ref.compare(ref.latest_by_source([qa, qd]), Decimal("1.0"))] == [True]


def test_deviation_alert_fires_only_above_limit_and_once_per_episode(market_factory_ref):
    clock = Clock(T0)
    cfg = settings(threshold="1.0")
    poller = make_poller(market_factory_ref, clock, cfg, keep=set())
    frank = ref.ReferenceQuote("USD/BRL", "frankfurter", Decimal("5.40"), T0, T0)
    ptax = ref.ReferenceQuote("USD/BRL", "bcb-ptax-venda", Decimal("5.41"), T0, T0)  # 0,185 %: dentro do limite
    oxr_hi = ref.ReferenceQuote("USD/BRL", "openexchangerates", Decimal("5.50"), T0, T0)  # 1,85 %: acima
    with market_factory_ref() as s:
        ref.upsert_reference_quotes(s, [frank, ptax], data_mode="real")
        poller._check_reference_deviations(s, T0)
        s.commit()
    with market_factory_ref() as s:
        assert events_svc.replay(s, 0, data_mode="real") == []
    with market_factory_ref() as s:
        ref.upsert_reference_quotes(s, [oxr_hi], data_mode="real")
        poller._check_reference_deviations(s, T0)
        poller._check_reference_deviations(s, T0)  # mesma situação: nenhum evento novo
        s.commit()
    with market_factory_ref() as s:
        events = [e for e in events_svc.replay(s, 0, data_mode="real") if e.type == EVENT_REFERENCE_DEVIATION]
    # OXR (5,50) fica 1,8182 % acima do Frankfurter (5,40) e 1,6364 % acima da PTAX (5,41): dois pares acima do limite
    pairs = sorted((e.payload["source_a"], e.payload["source_b"]) for e in events)
    assert pairs == [("bcb-ptax-venda", "openexchangerates"), ("frankfurter", "openexchangerates")]
    assert {abs(Decimal(e.payload["deviation_pct"])) for e in events} == {Decimal("1.6364"), Decimal("1.8182")}
    payload = events[0].payload
    assert payload["referencia"] is True and payload["executavel"] is False
    assert payload["threshold_pct"] == "1.0"


# ------------------------------------------------------------------ orçamento da OXR
def test_budget_never_passes_one_thousand_per_month(market_factory_ref):
    with market_factory_ref() as s:
        for _ in range(1000):
            assert ref.reserve_call(s, ref.OXR_SOURCE, T0, 5000) is True  # teto configurado acima do plano: ignorado
        s.commit()
    with market_factory_ref() as s:
        assert ref.reserve_call(s, ref.OXR_SOURCE, T0, 5000) is False
        assert ref.calls_used(s, ref.OXR_SOURCE, T0) == 1000
        s.commit()
    with market_factory_ref() as s:
        assert s.scalar(select(func.max(ReferenceApiUsage.calls))) == 1000


def test_budget_resets_next_utc_month_and_zero_cap_blocks(market_factory_ref):
    with market_factory_ref() as s:
        assert ref.reserve_call(s, ref.OXR_SOURCE, T0, 0) is False  # teto zero: nem a primeira chamada
        assert ref.reserve_call(s, ref.OXR_SOURCE, T0, 1) is True
        assert ref.reserve_call(s, ref.OXR_SOURCE, T0, 1) is False
        s.commit()
    nxt = datetime(2026, 12, 1, 0, 5, tzinfo=UTC)
    with market_factory_ref() as s:
        assert ref.reserve_call(s, ref.OXR_SOURCE, nxt, 1) is True
        assert ref.calls_used(s, ref.OXR_SOURCE, nxt) == 1


def test_effective_ceiling_clamps_only_the_oxr():
    assert ref.effective_ceiling(ref.OXR_SOURCE, 5000) == 1000
    assert ref.effective_ceiling(ref.OXR_SOURCE, -4) == 0
    assert ref.effective_ceiling("frankfurter", 5000) == 5000


# ------------------------------------------------------------------ poller (HTTP mockado)
@pytest.fixture
def market_factory_ref():
    from fronteira_fx.db import create_schema, make_engine, make_session_factory

    engine = make_engine("sqlite://")
    create_schema(engine)
    yield make_session_factory(engine)
    engine.dispose()


def test_oxr_is_disabled_without_key(market_factory_ref):
    poller = MarketPoller(market_factory_ref, settings(key=None), clock=Clock(T0))
    assert ref.OXR_SOURCE not in {s.source_id for s in poller.scheduler.sources()}


@respx.mock
async def test_oxr_polls_hourly_key_only_in_query_and_stops_at_cap(market_factory_ref):
    clock = Clock(T0)
    route = respx.get(ref.OXR_URL).mock(return_value=httpx.Response(200, json=oxr_payload()))
    poller = make_poller(market_factory_ref, clock, settings(key=SECRET, cap=3), keep={ref.OXR_SOURCE})
    try:
        for hour in range(5):
            clock.now = T0 + timedelta(hours=hour)
            await poller.run_once()
    finally:
        await poller.aclose()
    assert route.call_count == 3  # teto de 3: a quarta e a quinta horas não consultam
    request = route.calls[0].request
    assert request.url.params["app_id"] == SECRET
    assert request.url.params["symbols"] == "BRL,PYG,EUR"
    with market_factory_ref() as s:
        assert ref.calls_used(s, ref.OXR_SOURCE, T0) == 3
        rows = s.scalars(select(FxReferenceQuote)).all()
        assert rows and all(r.referencia is True and r.source == ref.OXR_SOURCE for r in rows)


@respx.mock
async def test_oxr_month_of_hourly_polls_stays_under_limit(market_factory_ref):
    clock = Clock(T0)
    route = respx.get(ref.OXR_URL).mock(return_value=httpx.Response(200, json=oxr_payload()))
    poller = make_poller(market_factory_ref, clock, settings(key=SECRET), keep={ref.OXR_SOURCE})
    try:
        for hour in range(24 * 30):  # 30 dias de coleta horária
            clock.now = T0 + timedelta(hours=hour)
            await poller.run_once()
    finally:
        await poller.aclose()
    assert 0 < route.call_count <= 720
    with market_factory_ref() as s:
        nov = ref.calls_used(s, ref.OXR_SOURCE, T0)  # novembro (UTC)
        dec = ref.calls_used(s, ref.OXR_SOURCE, clock.now)  # o relógio já passou para dezembro
    assert nov + dec == route.call_count
    assert nov <= 1000 and dec <= 1000


@respx.mock
async def test_oxr_errors_never_show_the_key(market_factory_ref):
    clock = Clock(T0)
    respx.get(ref.OXR_URL).mock(return_value=httpx.Response(500))
    poller = make_poller(market_factory_ref, clock, settings(key=SECRET), keep={ref.OXR_SOURCE})
    try:
        result = await poller.run_once()
    finally:
        await poller.aclose()
    assert result[0].ok is False
    assert "HTTP 500" in (result[0].error or "")
    assert SECRET not in (result[0].error or "")


@respx.mock
async def test_oxr_network_error_hides_url_with_key(market_factory_ref):
    clock = Clock(T0)
    respx.get(ref.OXR_URL).mock(side_effect=httpx.ConnectError(f"falhou em {ref.OXR_URL}?app_id={SECRET}"))
    poller = make_poller(market_factory_ref, clock, settings(key=SECRET), keep={ref.OXR_SOURCE})
    try:
        result = await poller.run_once()
    finally:
        await poller.aclose()
    assert result[0].ok is False and SECRET not in (result[0].error or "")
    assert "erro de rede" in (result[0].error or "")


@respx.mock
async def test_frankfurter_and_ptax_store_references_with_collection_date(market_factory_ref):
    clock = Clock(T0)
    respx.get(url__startswith=q.FRANKFURTER_URL).mock(
        return_value=httpx.Response(200, content=read_fixture("frankfurter_v2_rates.json"))
    )

    def bcb(request: httpx.Request) -> httpx.Response:
        code = request.url.path.split("sgs.")[1].split("/")[0]
        name = {
            "1": "bcb_sgs_1_ultimos2.json",
            "10813": "bcb_sgs_10813_ultimos2.json",
            "432": "bcb_sgs_432_ultimo.json",
        }[code]
        assert "dataInicial=" in str(request.url) and "dataFinal=" in str(request.url)
        return httpx.Response(200, content=read_fixture(name))

    respx.route(url__startswith="https://api.bcb.gov.br/").mock(side_effect=bcb)
    poller = make_poller(market_factory_ref, clock, settings(), keep={FX_SOURCE, "bcb-sgs"})
    try:
        results = await poller.run_once()
    finally:
        await poller.aclose()
    assert all(r.ok for r in results)
    with market_factory_ref() as s:
        rows = s.scalars(select(FxReferenceQuote)).all()
        sources = {r.source for r in rows}
        assert {"frankfurter", ref.PTAX_SOURCE} <= sources
        assert all(r.referencia is True and r.collected_at == T0 for r in rows)
        assert not any(r.instrument == "Selic meta" for r in rows)


def test_reference_code_never_reaches_the_cycle_engine():
    """Referência nunca vira aresta: o motor, o grafo e os ciclos não importam o módulo market."""
    for rel in ("src/fronteira_fx/engine", "src/fronteira_fx/graph", "src/fronteira_fx/services/cycles.py"):
        base = ROOT / rel
        files = [base] if base.is_file() else list(base.rglob("*.py"))
        for f in files:
            text = f.read_text(encoding="utf-8")
            assert not re.search(r"from\s+\.+(market|\.market)|fronteira_fx\.market", text), f
