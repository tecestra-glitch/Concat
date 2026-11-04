"""Rotas do módulo `market`: manchetes, referências de mercado e volatilidade. Só leitura do banco.

As referências são comparação de mercado: `executable` é sempre `false` e nenhuma delas entra no grafo de
posições nem no motor de ciclos.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from ..market import news as news_mod
from ..market import read as market_read
from ..market import sentiment as sentiment_mod
from ..models import MarketQuote, NewsItem
from .deps import DataModeDep, DbDep

router = APIRouter(prefix="/market", tags=["market"])

QUOTE_NOTE = "Referência de mercado. Não é preço executável nem cotação de casa de câmbio."


class NewsOut(BaseModel):
    id: str
    source: str
    feed: str
    title: str
    link: str
    excerpt: str | None  # trecho curto; só em feed que autoriza (hoje investinglive), senão null
    attribution: str  # sempre presente: quem é a fonte e de onde vem o item
    published_at: datetime | None
    captured_at: datetime
    data_mode: str


class SentimentOut(BaseModel):
    index_id: str
    label: str
    value: int
    classification: str
    provider: str
    observed_at: datetime
    captured_at: datetime
    attribution: str
    executable: Literal[False] = False
    data_mode: str


class MarketQuoteOut(BaseModel):
    instrument: str
    label: str
    kind: Literal["crypto", "fx_reference", "bcb_series"]
    source: str
    price: str
    change_pct: str | None
    observed_at: datetime
    captured_at: datetime
    executable: Literal[False] = False
    note: str = QUOTE_NOTE
    data_mode: str


class MarketVolatilityOut(BaseModel):
    instrument: str
    status: Literal["ok", "insufficient_data", "stale_input"]
    as_of: datetime | None
    last_close: str | None
    last_move_pct: str | None
    ewma_pct_5m: str | None
    parkinson_1d_pct: str | None
    parkinson_20d_pct: str | None
    ratio_1d_20d: str | None
    atr_14_5m: str | None
    regime: Literal["normal", "alta", "muito_alta"] | None
    alert: bool
    reasons: list[str]
    data_mode: str


@router.get("/news", operation_id="list_market_news", summary="Manchetes de feeds públicos (sem texto da matéria)")
def list_news(
    db: DbDep,
    data_mode: DataModeDep,
    source: Annotated[
        str | None,
        Query(max_length=32, description="investinglive | infomoney | agencia-brasil | bcb | mercopress | demo"),
    ] = None,
    since: Annotated[datetime | None, Query(description="só manchetes publicadas (ou capturadas) a partir de")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[NewsOut]:
    when = func.coalesce(NewsItem.published_at, NewsItem.captured_at)
    stmt = select(NewsItem).where(NewsItem.data_mode == data_mode)
    if source:
        stmt = stmt.where(NewsItem.source == source)
    if since is not None:
        stmt = stmt.where(when >= since)
    rows = db.scalars(stmt.order_by(when.desc()).limit(limit)).all()
    return [
        NewsOut(
            id=r.id,
            source=r.source,
            feed=r.feed,
            title=r.title,
            link=r.link,
            excerpt=r.excerpt,
            attribution=news_mod.attribution_for(r.feed),
            published_at=r.published_at,
            captured_at=r.captured_at,
            data_mode=r.data_mode,
        )
        for r in rows
    ]


@router.get(
    "/sentiment",
    operation_id="list_market_sentiment",
    summary="Sentimento de mercado (Fear & Greed, Alternative.me), com atribuição; nunca executável",
)
def list_sentiment(
    db: DbDep,
    data_mode: DataModeDep,
    limit: Annotated[int, Query(ge=1, le=90)] = 30,
) -> list[SentimentOut]:
    return [
        SentimentOut(
            index_id=r.index_id,
            label=sentiment_mod.FNG_LABEL,
            value=r.value,
            classification=r.classification,
            provider=r.provider,
            observed_at=r.observed_at,
            captured_at=r.captured_at,
            attribution=sentiment_mod.FNG_ATTRIBUTION,
            data_mode=r.data_mode,
        )
        for r in sentiment_mod.list_readings(db, data_mode, limit)
    ]


@router.get(
    "/quotes", operation_id="get_market_quotes", summary="Referências de mercado (cripto, câmbio de referência, BCB)"
)
def get_quotes(db: DbDep, data_mode: DataModeDep) -> list[MarketQuoteOut]:
    rows = db.scalars(
        select(MarketQuote).where(MarketQuote.data_mode == data_mode).order_by(MarketQuote.instrument)
    ).all()
    return [
        MarketQuoteOut(
            instrument=r.instrument,
            label=r.label,
            kind=r.kind,  # type: ignore[arg-type]
            source=r.source,
            price=format(r.price, "f"),
            change_pct=None if r.change_pct is None else format(r.change_pct, "f"),
            observed_at=r.observed_at,
            captured_at=r.captured_at,
            data_mode=r.data_mode,
        )
        for r in rows
    ]


@router.get(
    "/volatility",
    operation_id="get_market_volatility",
    summary="Volatilidade (EWMA, Parkinson, ATR) e selo normal / alta / muito alta",
)
def get_volatility(db: DbDep, data_mode: DataModeDep) -> list[MarketVolatilityOut]:
    return [
        MarketVolatilityOut(**payload, data_mode=data_mode)
        for payload in market_read.volatility_payloads(db, data_mode)
    ]
