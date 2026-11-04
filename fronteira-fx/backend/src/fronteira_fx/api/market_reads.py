"""Rotas de leitura do módulo `market` que faltavam para o MCP: cotações de cripto, triângulos, referências de câmbio,
macro (BCB e FRED), indicadores técnicos. Somente leitura: só `GET` e só banco, nenhuma chamada de rede, nenhum laço,
nenhum websocket e nenhum cálculo de ciclo ou indicador (a Vercel tem 4 h de CPU por mês). Respostas cacheadas por
`READ_CACHE_TTL_S` (ver `api/cache.py`).

Triângulos e indicadores são lidos de `market_reads`, gravados pelo worker (`market/reads.py`). Tudo que sai daqui é
referência ou leitura de posição: `executable` é sempre `false` em cotação, referência, macro e indicador. Triângulos
têm as mesmas três pernas e a mesma regra de execução de `find_cycles` no grafo de posições.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import or_, select

from ..market import quotes as q
from ..market import reads
from ..market import reference as ref
from ..models import MarketQuote
from ..schemas import CycleOut
from .deps import DataModeDep, DbDep
from .market import MarketQuoteOut

router = APIRouter(prefix="/market", tags=["market"])

REFERENCE_NOTE = "Referência de câmbio. Não executável: nunca é preço de casa de câmbio nem entra num ciclo executável."
INDICATOR_NOTE = (
    "Indicadores calculados sobre velas fechadas (shift 1). Leitura de mercado, não é sinal de compra ou venda."
)
BINANCE_INSTRUMENTS = tuple(inst for _sym, _label, inst in q.BINANCE_SYMBOLS)


class ReferenceOut(BaseModel):
    instrument: str
    source: str
    price: str
    observed_at: datetime
    collected_at: datetime
    referencia: Literal[True] = True
    executable: Literal[False] = False
    note: str = REFERENCE_NOTE
    data_mode: str


class MacroOut(MarketQuoteOut):
    """Mesma forma de `MarketQuoteOut` (`kind`, `source`, `price`, `change_pct`), só para séries macro."""


class IndicatorsOut(BaseModel):
    instrument: str
    interval: Literal["5m", "1d"]
    status: Literal["ok", "insufficient_data"]
    as_of: datetime | None  # close_time da última vela fechada usada
    closed_candles: int
    rsi_14: str | None
    macd_line: str | None
    macd_signal: str | None
    macd_hist: str | None
    stoch_k: str | None
    stoch_d: str | None
    adx_14: str | None
    plus_di_14: str | None
    minus_di_14: str | None
    atr_14: str | None
    natr_14: str | None
    ichimoku_tenkan: str | None
    ichimoku_kijun: str | None
    ichimoku_senkou_a: str | None  # nuvem vigente: calculada 26 velas antes do último fechamento
    ichimoku_senkou_b: str | None
    source: Literal["binance"] = "binance"
    executable: Literal[False] = False
    note: str = INDICATOR_NOTE
    data_mode: str


def _cached(request: Request, response: Response, key: str, compute: Any) -> Any:
    """Resposta por `key` (rota + modo + parâmetros). `Cache-Control: private`: a resposta depende da chave da API."""
    ttl = request.app.state.settings.read_cache_ttl_s
    response.headers["Cache-Control"] = f"private, max-age={ttl}"
    return request.app.state.read_cache.get_or_set(key, ttl, compute)


def _dec(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


@router.get(
    "/crypto",
    operation_id="get_crypto_quotes",
    summary="Cotações de cripto (referência de mercado da Binance, dados públicos); nunca executáveis",
)
def get_crypto_quotes(request: Request, response: Response, db: DbDep, data_mode: DataModeDep) -> list[MarketQuoteOut]:
    def compute() -> list[MarketQuoteOut]:
        rows = db.scalars(
            select(MarketQuote)
            .where(MarketQuote.data_mode == data_mode, MarketQuote.kind == "crypto")
            .order_by(MarketQuote.instrument)
        ).all()
        return [
            MarketQuoteOut(
                instrument=r.instrument,
                label=r.label,
                kind="crypto",
                source=r.source,
                price=format(r.price, "f"),
                change_pct=_dec(r.change_pct),
                observed_at=r.observed_at,
                captured_at=r.captured_at,
                data_mode=r.data_mode,
            )
            for r in rows
        ]

    return _cached(request, response, f"crypto|{data_mode}", compute)


@router.get(
    "/triangles",
    operation_id="get_triangles",
    summary="Triângulos (três pernas) no grafo de posições, com lucro líquido e confiança; só leitura",
    response_model=list[CycleOut],
)
def get_triangles(
    request: Request,
    response: Response,
    db: DbDep,
    data_mode: DataModeDep,
    min_roi: Annotated[Decimal | None, Query(description="ROI mínimo como string decimal, ex. 0.001")] = None,
    start: Annotated[str | None, Query(description="nó de partida, ex. BRL@nubank", max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    mode: Annotated[Literal["celular", "todos"], Query(description="celular (padrão) ou todos")] = "celular",
) -> list[dict[str, Any]]:
    """Lê a lista calculada pelo worker (`market_reads`, ordenada por ROI) e aplica os filtros sobre ela.
    Sem linha gravada ainda: lista vazia. Nenhum ciclo é calculado aqui."""

    def compute() -> list[dict[str, Any]]:
        row = reads.read_row(db, reads.TRIANGLE_KIND, mode, data_mode)
        cycles = [c for c in (row.payload if row is not None else []) if len(c["edges"]) == 3]
        if min_roi is not None:
            cycles = [c for c in cycles if Decimal(c["roi"]) >= min_roi]
        if start:
            cycles = [c for c in cycles if c["start"] == start]
        return cycles[:limit]

    key = f"triangles|{data_mode}|{min_roi}|{start}|{limit}|{mode}"
    return _cached(request, response, key, compute)


@router.get(
    "/references",
    operation_id="list_fx_references",
    summary="Referências de câmbio (Frankfurter, PTAX, OXR): última cotação por fonte; nunca executáveis",
)
def list_fx_references(request: Request, response: Response, db: DbDep, data_mode: DataModeDep) -> list[ReferenceOut]:
    def compute() -> list[ReferenceOut]:
        now = datetime.now(tz=UTC)
        quotes = ref.recent_references(db, now=now, data_mode=data_mode)
        latest = ref.latest_by_source(quotes)
        return [
            ReferenceOut(
                instrument=r.instrument,
                source=r.source,
                price=format(r.price, "f"),
                observed_at=r.observed_at,
                collected_at=r.collected_at,
                data_mode=data_mode,
            )
            for by_source in latest.values()
            for r in by_source.values()
        ]

    return _cached(request, response, f"references|{data_mode}", compute)


@router.get(
    "/macro",
    operation_id="get_macro_series",
    summary="Séries macro: SGS do BCB (Selic, IPCA, PTAX) e dólar amplo do FRED; nunca executáveis",
)
def get_macro_series(request: Request, response: Response, db: DbDep, data_mode: DataModeDep) -> list[MacroOut]:
    def compute() -> list[MacroOut]:
        rows = db.scalars(
            select(MarketQuote)
            .where(
                MarketQuote.data_mode == data_mode,
                or_(MarketQuote.kind == "bcb_series", MarketQuote.source == "fred"),
            )
            .order_by(MarketQuote.instrument)
        ).all()
        return [
            MacroOut(
                instrument=r.instrument,
                label=r.label,
                kind=r.kind,  # type: ignore[arg-type]
                source=r.source,
                price=format(r.price, "f"),
                change_pct=_dec(r.change_pct),
                observed_at=r.observed_at,
                captured_at=r.captured_at,
                data_mode=r.data_mode,
            )
            for r in rows
        ]

    return _cached(request, response, f"macro|{data_mode}", compute)


@router.get(
    "/indicators",
    operation_id="get_market_indicators",
    summary="Indicadores técnicos (RSI, MACD, estocástico, ADX, ATR, NATR, Ichimoku) de uma série Binance; só leitura",
)
def get_market_indicators(
    request: Request,
    response: Response,
    db: DbDep,
    data_mode: DataModeDep,
    instrument: Annotated[Literal["BTC/USDT", "ETH/USDT", "USDT/BRL"], Query()],
    interval: Annotated[Literal["5m", "1d"], Query()] = "5m",
) -> IndicatorsOut:
    """Lê os indicadores que o worker calculou sobre velas fechadas (`market_reads`). Sem linha: insufficient_data."""
    if instrument not in BINANCE_INSTRUMENTS:  # o Literal já garante; a checagem protege contra mudança futura
        raise HTTPException(status_code=422, detail="instrumento sem indicadores")

    def compute() -> IndicatorsOut:
        row = reads.read_row(db, reads.INDICATOR_KIND, f"{instrument}|{interval}", data_mode)
        if row is None:
            return IndicatorsOut(
                instrument=instrument,
                interval=interval,
                status="insufficient_data",
                as_of=None,
                closed_candles=0,
                data_mode=data_mode,
                **{k: None for k in reads.INDICATOR_FIELDS},
            )
        return IndicatorsOut.model_validate(row.payload)

    key = f"indicators|{data_mode}|{instrument}|{interval}"
    return _cached(request, response, key, compute)
