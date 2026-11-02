from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query

from ..schemas import City, Currency, Modality, QuoteOut, QuoteRequestIn, QuoteRequestOut
from ..services.quotes import latest_quotes, quote_to_out
from .deps import ApiKey, CollectorDep, DataModeDep, DbDep, SettingsDep

router = APIRouter(prefix="/quotes", tags=["quotes"])


@router.get("", operation_id="get_quotes", summary="Latest quote per comparable context")
def get_quotes(
    db: DbDep,
    data_mode: DataModeDep,
    settings: SettingsDep,
    city: Annotated[City | None, Query()] = None,
    base: Annotated[Currency | None, Query()] = None,
    quote: Annotated[Currency | None, Query()] = None,
    source: Annotated[str | None, Query(max_length=64)] = None,
    modality: Annotated[Modality | None, Query()] = None,
    amount: Annotated[Decimal | None, Query(gt=0)] = None,
) -> list[QuoteOut]:
    rows = latest_quotes(
        db,
        data_mode=data_mode,
        city=city,
        base=base,
        quote=quote,
        source=source,
        modality=modality,
        amount=amount,
        lookback_s=settings.quotes_lookback_s,
    )
    return [quote_to_out(q) for q in rows]


@router.post(
    "/request",
    operation_id="request_quote",
    dependencies=[ApiKey],
    summary="Fetch a quote from one source now (or queue it for the worker)",
)
async def request_quote(body: QuoteRequestIn, collector: CollectorDep) -> QuoteRequestOut:
    result = await collector.request_quote(body.source_id, body.params)
    return QuoteRequestOut.model_validate(result)
