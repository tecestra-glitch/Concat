"""Sentimento de mercado: Fear & Greed Index da Alternative.me (módulo `market`).

Uma leitura por dia (o índice muda uma vez ao dia), consultada no máximo a cada hora. Cada leitura guarda valor
(0 a 100), rótulo do provedor, data da observação e hora da captura, e sai sempre com a atribuição do provedor.
É tendência de humor de mercado, não preço: `executable` é sempre `false`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import SentimentReading

FNG_SOURCE = "alternative-fng"  # id da fonte no agendador
FNG_INDEX_ID = "fng"
FNG_PROVIDER = "alternative.me"
FNG_URL = "https://api.alternative.me/fng/"
FNG_PARAMS = {"limit": "1", "format": "json"}
FNG_POLL_INTERVAL_S = 3600  # o índice é diário: uma consulta por hora já é folga
FNG_LABEL = "Fear & Greed Index"
FNG_ATTRIBUTION = "Fear & Greed Index: Alternative.me (api.alternative.me/fng). Dado de humor de mercado, não preço."
MAX_CLASSIFICATION_CHARS = 32


class SentimentFormatError(ValueError):
    """Resposta que não tem a forma esperada ou que traz erro do próprio provedor."""


@dataclass(frozen=True, slots=True)
class SentimentDraft:
    index_id: str
    value: int
    classification: str
    observed_at: datetime


def _int_value(raw: Any) -> int:
    if isinstance(raw, bool):
        raise SentimentFormatError("valor booleano")
    if isinstance(raw, int):
        value = raw
    elif isinstance(raw, str) and raw.isdigit():
        value = int(raw)
    else:
        raise SentimentFormatError("valor do índice ausente ou fora de forma")
    if not 0 <= value <= 100:
        raise SentimentFormatError("valor do índice fora de 0 a 100")
    return value


def parse_fng(data: Any) -> SentimentDraft:
    """Resposta de `api.alternative.me/fng/`: a leitura mais recente, validada. Qualquer desvio é erro."""
    if not isinstance(data, dict):
        raise SentimentFormatError("esperado um objeto JSON")
    meta = data.get("metadata")
    if isinstance(meta, dict) and meta.get("error"):
        raise SentimentFormatError(f"provedor recusou a consulta: {str(meta['error'])[:120]}")
    rows = data.get("data")
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        raise SentimentFormatError("lista 'data' ausente ou vazia")
    row = rows[0]
    value = _int_value(row.get("value"))
    classification = row.get("value_classification")
    if not isinstance(classification, str) or not classification.strip():
        raise SentimentFormatError("rótulo do índice ausente")
    classification = " ".join(classification.split())[:MAX_CLASSIFICATION_CHARS]
    stamp = row.get("timestamp")
    if not isinstance(stamp, str) or not stamp.isdigit():
        raise SentimentFormatError("timestamp ausente ou fora de forma")
    try:
        observed = datetime.fromtimestamp(int(stamp), tz=UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise SentimentFormatError("timestamp fora do intervalo") from exc
    return SentimentDraft(FNG_INDEX_ID, value, classification, observed)


def ingest_fng(session: Session, draft: SentimentDraft, *, captured_at: datetime, data_mode: str) -> bool:
    """Grava a leitura se ainda não houver uma para a mesma data de observação. Devolve True quando gravou."""
    known = session.scalar(
        select(SentimentReading.id).where(
            SentimentReading.index_id == draft.index_id,
            SentimentReading.observed_at == draft.observed_at,
            SentimentReading.data_mode == data_mode,
        )
    )
    if known is not None:
        return False
    session.add(
        SentimentReading(
            index_id=draft.index_id,
            provider=FNG_PROVIDER,
            value=draft.value,
            classification=draft.classification,
            observed_at=draft.observed_at,
            captured_at=captured_at,
            data_mode=data_mode,
        )
    )
    session.flush()
    return True


def list_readings(session: Session, data_mode: str, limit: int) -> list[SentimentReading]:
    """Leituras mais recentes primeiro."""
    return list(
        session.scalars(
            select(SentimentReading)
            .where(SentimentReading.data_mode == data_mode)
            .order_by(SentimentReading.observed_at.desc())
            .limit(limit)
        )
    )
