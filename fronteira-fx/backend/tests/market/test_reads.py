"""Leituras calculadas pelo worker (`market/reads.py`): triângulos e indicadores gravados em `market_reads`, com
recálculo com piso de 60 s. A API só lê essas linhas (ver tests/api/test_market_reads.py)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fronteira_fx.indicators import core
from fronteira_fx.market import reads, vol
from fronteira_fx.models import MarketCandle
from tests.conftest import NOW, make_settings, seed_market

from .conftest import market_settings

T0 = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)


def _closed_series(db, n: int, start: datetime) -> list[vol.Candle]:
    rows: list[vol.Candle] = []
    for i in range(n):
        close = Decimal(100 + (i % 17)) + Decimal(i) / 10
        open_time = start + timedelta(minutes=5 * i)
        db.add(
            MarketCandle(
                instrument="BTC/USDT",
                interval="5m",
                open_time=open_time,
                close_time=open_time + timedelta(minutes=5),
                open=close - Decimal("0.3"),
                high=close + Decimal("1"),
                low=close - Decimal("1"),
                close=close,
                data_mode="real",
            )
        )
        rows.append(
            vol.Candle(open_time, open_time + timedelta(minutes=5), close - Decimal("0.3"), close + 1, close - 1, close)
        )
    return rows


def test_worker_grava_triangulos_iguais_ao_grafo_e_json_puro(db):
    seed_market(db)
    settings = make_settings()
    refresh_written = reads.refresh_reads(db, settings, NOW)
    db.commit()
    assert refresh_written >= 2 + 6  # dois modos de triângulos e seis indicadores (3 instrumentos × 2 intervalos)
    row = reads.read_row(db, reads.TRIANGLE_KIND, "celular", "real")
    assert row is not None and row.computed_at is not None
    expected = reads.triangle_cycles(db, data_mode="real", lookback_s=settings.quotes_lookback_s, mode="celular")
    assert row.payload == json.loads(json.dumps(expected))  # o que sai do grafo é JSON puro (strings e listas)
    assert all(len(c["edges"]) == 3 for c in row.payload)


def test_indicadores_gravados_com_nuvem_vigente_e_status(db):
    closes = _closed_series(db, 130, NOW - timedelta(minutes=5 * 130))
    db.commit()
    reads.refresh_reads(db, make_settings(), NOW)
    db.commit()
    row = reads.read_row(db, reads.INDICATOR_KIND, "BTC/USDT|5m", "real")
    assert row is not None and row.payload["status"] == "ok"
    assert row.payload["closed_candles"] == 130
    ich = core.ichimoku(
        core.Ohlc(
            open=[c.open for c in closes],
            high=[c.high for c in closes],
            low=[c.low for c in closes],
            close=[c.close for c in closes],
        )
    )
    assert Decimal(row.payload["ichimoku_senkou_a"]) == ich.senkou_a[129 - 26]  # type: ignore[index]


def test_indicador_sem_velas_grava_insufficient_data(db):
    reads.refresh_reads(db, make_settings(), NOW)
    db.commit()
    row = reads.read_row(db, reads.INDICATOR_KIND, "USDT/BRL|1d", "real")
    assert row is not None and row.payload["status"] == "insufficient_data"
    assert row.payload["as_of"] is None and row.payload["rsi_14"] is None


def test_refresher_recalcula_no_maximo_a_cada_60_segundos(market_factory):
    seed_market_session = market_factory()
    try:
        seed_market(seed_market_session)
        seed_market_session.commit()
    finally:
        seed_market_session.close()
    refresher = reads.ReadsRefresher(market_factory, market_settings())
    first = refresher.maybe_refresh(T0)
    assert first > 0
    assert refresher.maybe_refresh(T0 + timedelta(seconds=30)) == 0
    assert refresher.maybe_refresh(T0 + timedelta(seconds=60)) > 0


def test_frequencia_vale_entre_instancias_serverless(market_factory):
    """Função serverless: cada rodada cria outro objeto. O controle de 60 s está no banco, não na memória."""
    session = market_factory()
    try:
        seed_market(session)
        session.commit()
    finally:
        session.close()
    assert reads.ReadsRefresher(market_factory, market_settings()).maybe_refresh(T0) > 0
    assert reads.ReadsRefresher(market_factory, market_settings()).maybe_refresh(T0 + timedelta(seconds=45)) == 0
    assert reads.ReadsRefresher(market_factory, market_settings()).maybe_refresh(T0 + timedelta(seconds=61)) > 0
