"""Rotas do pregão: velas OHLC, resumo da sessão e status das casas (tag `pregao`, sem `ApiKey`).

O prefixo `/v1` vem do `v1_router` quando a integração registra este router em `api/__init__.py`.
Em modo `demo` nenhum handler toca o banco: usam os geradores de `services/candles_demo.py`.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from fronteira_fx.api.deps import DataModeDep, DbDep
from fronteira_fx.models import Source
from fronteira_fx.schemas_candles import CandleSeries, HouseSession, SessionStats, Timeframe
from fronteira_fx.services.candles import candles_series, ensure_utc
from fronteira_fx.services.candles_demo import demo_candles, demo_house_sessions, demo_session_stats
from fronteira_fx.services.market_hours import house_sessions, load_market_hours, strip_demo_prefix
from fronteira_fx.services.session_stats import session_stats

router = APIRouter(tags=["pregao"])

MAX_STATS_KEYS = 20


def _with_source_names(sessions: list[HouseSession], sources: Sequence[Source]) -> list[HouseSession]:
    """Fonte sem horário (ou horário sem `name`): o nome de exibição é `Source.name`, não o `source_id` cru."""
    names = {s.id: s.name for s in sources if s.name}
    return [
        hs.model_copy(update={"name": names[hs.source_id]}) if hs.name == hs.source_id and hs.source_id in names else hs
        for hs in sessions
    ]


@router.get("/candles", operation_id="get_candles", response_model=CandleSeries)
def get_candles(
    session: DbDep,
    mode: DataModeDep,
    key: Annotated[str, Query(min_length=1)],
    tf: Timeframe,
    start: Annotated[datetime | None, Query(alias="from")] = None,
    end: Annotated[datetime | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 300,
) -> CandleSeries:
    """Velas OHLC do `mid` de uma série. `from` inclusivo, `to` exclusivo; datas sem fuso são UTC.

    Sem cotações → `200` com `candles: []`, nunca 404.
    """
    if start is not None:
        start = ensure_utc(start)
    if end is not None:
        end = ensure_utc(end)
    if start is not None and end is not None and start >= end:
        raise HTTPException(status_code=422, detail="from deve ser anterior a to")
    if mode == "demo":
        return CandleSeries(key=key, tf=tf, candles=demo_candles(key, tf, start, end, limit), data_mode="demo")
    return candles_series(session, key, tf, start, end, limit, mode)


@router.get("/pregao/stats", operation_id="get_pregao_stats", response_model=list[SessionStats])
def get_pregao_stats(
    session: DbDep, mode: DataModeDep, keys: Annotated[str, Query(min_length=1)]
) -> list[SessionStats]:
    """Resumo do dia (00:00 em Assunção) por chave; `keys` separadas por vírgula, 1 a 20, mesma ordem na resposta."""
    wanted = [k.strip() for k in keys.split(",") if k.strip()]
    if not 1 <= len(wanted) <= MAX_STATS_KEYS:
        raise HTTPException(status_code=422, detail=f"keys: informe de 1 a {MAX_STATS_KEYS} chaves")
    now = datetime.now(UTC)
    if mode == "demo":
        return demo_session_stats(wanted, now)
    return session_stats(session, wanted, now, mode)


@router.get("/pregao/sessions", operation_id="get_pregao_sessions", response_model=list[HouseSession])
def get_pregao_sessions(session: DbDep, mode: DataModeDep) -> list[HouseSession]:
    """Status de funcionamento por fonte do modo (ordem por `Source.id`); referências (BCP) com `reference: true`."""
    now = datetime.now(UTC)
    if mode == "demo":
        return demo_house_sessions(now)
    sources = session.scalars(select(Source).where(Source.data_mode == mode).order_by(Source.id)).all()
    hours = load_market_hours()
    table = {s.id: hours.get(strip_demo_prefix(s.id)) for s in sources}
    reference_ids = {s.id for s in sources if s.kind == "central_bank"}
    return _with_source_names(house_sessions(now, table, mode, reference_ids), sources)
