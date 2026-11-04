"""Leituras de mercado calculadas no worker e gravadas em `market_reads`.

Triângulos (grafo de posições, três pernas) por modo e indicadores técnicos por instrumento e intervalo. A API só lê
essas linhas (`api/market_reads.py`): nenhum ciclo nem indicador é recalculado numa requisição, porque a Vercel tem
4 h de CPU por mês. Só leitura e cálculo: nada envia ordem e nada move dinheiro.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..config import Settings
from ..db import session_scope
from ..indicators import core, sinais
from ..models import MarketRead
from ..services.cycles import find_cycles_for
from . import quotes as q
from .service import load_candles

log = logging.getLogger("fronteira_fx.market.reads")

TRIANGLE_KIND = "triangles"
INDICATOR_KIND = "indicators"
TRIANGLE_MODES = ("celular", "todos")
TRIANGLE_STORE_LIMIT = 200  # ordenados por ROI; a API filtra min_roi, start e limit sobre esta lista
# Sem conta cadastrada, cada ponto de partida simula este valor em reais (o mesmo orçamento padrão do site,
# DEFAULT_SETTINGS.defaultCapital). Com saldo cadastrado vale o saldo real e este número é ignorado.
TRIANGLE_NOTIONAL_BRL = Decimal("5000")
INDICATOR_INTERVALS = ("5m", "1d")
INSTRUMENTS = tuple(inst for _sym, _label, inst in q.BINANCE_SYMBOLS)
INDICATOR_FIELDS = (
    "rsi_14",
    "macd_line",
    "macd_signal",
    "macd_hist",
    "stoch_k",
    "stoch_d",
    "adx_14",
    "plus_di_14",
    "minus_di_14",
    "atr_14",
    "natr_14",
    "ichimoku_tenkan",
    "ichimoku_kijun",
    "ichimoku_senkou_a",
    "ichimoku_senkou_b",
)
REFRESH_EVERY_S = 60  # piso de recálculo no worker; o worker roda a cada tick e este intervalo limita o trabalho


def _dec(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _last(series: list[Decimal | None]) -> Decimal | None:
    return series[-1] if series else None


def indicator_payload(instrument: str, interval: str, closed: list[Any], data_mode: str) -> dict[str, Any]:
    """Forma pública de um conjunto de indicadores (strings decimais). `closed`: só velas já fechadas, em ordem."""
    base: dict[str, Any] = {
        "instrument": instrument,
        "interval": interval,
        "closed_candles": len(closed),
        "data_mode": data_mode,
    }
    if not closed:
        return {**base, "status": "insufficient_data", "as_of": None, **{k: None for k in INDICATOR_FIELDS}}
    leituras = sinais.calcula_leituras(closed)  # VelaInvalidaError sobe para quem grava
    # A nuvem que vale no último fechamento foi calculada 26 velas antes. O valor do índice atual é a projeção
    # para daqui a 26 velas e não pode ser publicado como nuvem vigente.
    cloud = core.nuvem_vigente(leituras.ichimoku, len(closed) - 1)
    values = {
        "rsi_14": _last(leituras.rsi),
        "macd_line": _last(leituras.macd.line),
        "macd_signal": _last(leituras.macd.signal),
        "macd_hist": _last(leituras.macd.hist),
        "stoch_k": _last(leituras.stoch.k),
        "stoch_d": _last(leituras.stoch.d),
        "adx_14": _last(leituras.adx.adx),
        "plus_di_14": _last(leituras.adx.plus_di),
        "minus_di_14": _last(leituras.adx.minus_di),
        "atr_14": _last(leituras.atr),
        "natr_14": _last(leituras.natr),
        "ichimoku_tenkan": _last(leituras.ichimoku.tenkan),
        "ichimoku_kijun": _last(leituras.ichimoku.kijun),
        "ichimoku_senkou_a": cloud[0] if cloud else None,
        "ichimoku_senkou_b": cloud[1] if cloud else None,
    }
    # RSI e ADX são as leituras mais exigentes em janela: sem elas o conjunto não está completo
    complete = values["rsi_14"] is not None and values["adx_14"] is not None
    return {
        **base,
        "status": "ok" if complete else "insufficient_data",
        "as_of": closed[-1].close_time.isoformat(),
        **{k: _dec(v) for k, v in values.items()},
    }


def triangle_cycles(
    session: Session,
    *,
    data_mode: str,
    lookback_s: int,
    mode: str,
    notional_brl: Decimal | None = TRIANGLE_NOTIONAL_BRL,
) -> list[dict[str, Any]]:
    cycles = find_cycles_for(
        session,
        data_mode=data_mode,
        max_len=3,
        min_roi=None,
        start=None,
        limit=TRIANGLE_STORE_LIMIT,
        lookback_s=lookback_s,
        mode=mode,
        notional_brl=notional_brl,
    )
    return [c for c in cycles if len(c["edges"]) == 3]


def store_read(session: Session, kind: str, key: str, data_mode: str, payload: Any, now: datetime) -> None:
    row = session.scalar(
        select(MarketRead).where(MarketRead.kind == kind, MarketRead.key == key, MarketRead.data_mode == data_mode)
    )
    if row is None:
        session.add(MarketRead(kind=kind, key=key, data_mode=data_mode, payload=payload, computed_at=now))
    else:
        row.payload = payload  # atribuição nova: o JSON é regravado
        row.computed_at = now


def read_row(session: Session, kind: str, key: str, data_mode: str) -> MarketRead | None:
    """Leitura para a API: uma linha já calculada, ou None."""
    return session.scalar(
        select(MarketRead).where(MarketRead.kind == kind, MarketRead.key == key, MarketRead.data_mode == data_mode)
    )


def refresh_reads(session: Session, settings: Settings, now: datetime) -> int:
    """Recalcula e grava triângulos (um por modo) e indicadores (instrumento × intervalo). Devolve linhas gravadas.
    Quem chama faz o commit."""
    data_mode = settings.data_mode
    written = 0
    for mode in TRIANGLE_MODES:
        cycles = triangle_cycles(session, data_mode=data_mode, lookback_s=settings.quotes_lookback_s, mode=mode)
        store_read(session, TRIANGLE_KIND, mode, data_mode, cycles, now)
        written += 1
    for instrument in INSTRUMENTS:
        c5, c1 = load_candles(session, instrument, data_mode)
        for interval, candles in (("5m", c5), ("1d", c1)):
            at = now
            if data_mode == "demo" and candles:  # dados semeados: o relógio é o último fechamento
                at = candles[-1].close_time.replace(microsecond=0)
            closed = sinais.apenas_fechadas(candles, at)
            try:
                payload = indicator_payload(instrument, interval, closed, data_mode)
            except sinais.VelaInvalidaError:
                log.warning("leitura de indicadores de %s %s ignorada: velas inconsistentes", instrument, interval)
                continue
            store_read(session, INDICATOR_KIND, f"{instrument}|{interval}", data_mode, payload, now)
            written += 1
    return written


class ReadsRefresher:
    """Recalcula as leituras no máximo a cada `every_s` segundos. O controle de frequência fica no banco (carimbo de
    `computed_at`), e não na memória, para valer também numa função serverless (rota de coleta disparada de fora)."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        settings: Settings,
        *,
        every_s: int = REFRESH_EVERY_S,
    ) -> None:
        self.factory = session_factory
        self.settings = settings
        self.every_s = every_s

    def maybe_refresh(self, now: datetime | None = None) -> int:
        now = now or datetime.now(tz=UTC)
        with session_scope(self.factory) as session:
            row = read_row(session, TRIANGLE_KIND, TRIANGLE_MODES[0], self.settings.data_mode)
            if row is not None and (now - row.computed_at).total_seconds() < self.every_s:
                return 0
            return refresh_reads(session, self.settings, now)
