"""FRED (St. Louis Fed), série DTWEXBGS: dólar amplo ponderado por comércio (aproximação; não é o DXY).

Referência de mercado, nunca executável. Requer `FRED_API_KEY` (variável de ambiente, via `Settings`). Sem a chave
a fonte fica desligada: nenhuma requisição é feita. O limite publicado é de 120 requisições por minuto; aqui o
teto é 100 por minuto (`SlidingWindowLimiter`). Erro 429 é tentado de novo com recuo; esgotadas as tentativas,
vira `BlockedError` e o agendador recua. Mensagens de erro nunca contêm a URL nem a chave.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx

from . import quotes as q
from .throttle import BlockedError, SlidingWindowLimiter, backoff_delay, parse_retry_after

FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_SERIES_ID = "DTWEXBGS"
FRED_SOURCE = "fred-dtwexbgs"  # id da fonte no agendador
FRED_INSTRUMENT = "USD amplo (DTWEXBGS, FRED)"
FRED_LABEL = "Dólar amplo ponderado por comércio (DTWEXBGS, FRED; aproximação, não é o DXY)"
FRED_LIMIT_PER_MIN = 120  # limite publicado pelo FRED
FRED_MAX_PER_MINUTE = 100  # teto usado aqui, com folga abaixo do publicado
FRED_LOOKBACK_DAYS = 30
FRED_MAX_ATTEMPTS = 3  # uma chamada + duas tentativas após 429
FRED_BACKOFF_BASE_S = 2.0
FRED_BACKOFF_CAP_S = 30.0
FRED_POLL_INTERVAL_S = 3600  # série diária: uma consulta por hora basta

Sleep = Callable[[float], Awaitable[None]]


class FredError(RuntimeError):
    """Falha da FRED sem URL nem chave na mensagem."""


def fred_params(api_key: str, *, today: date) -> dict[str, str]:
    """Parâmetros da consulta. A chave entra só aqui e nunca é ecoada em erros."""
    if not api_key:
        raise ValueError("FRED: chave ausente (defina FRED_API_KEY)")
    return {
        "series_id": FRED_SERIES_ID,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": (today - timedelta(days=FRED_LOOKBACK_DAYS)).isoformat(),
        "sort_order": "desc",
        "limit": "10",
    }


async def fred_observations(
    client: httpx.AsyncClient,
    api_key: str,
    *,
    today: date,
    limiter: SlidingWindowLimiter,
    clock: Callable[[], float],
    sleep: Sleep = asyncio.sleep,
    max_attempts: int = FRED_MAX_ATTEMPTS,
) -> Any:
    """Uma consulta com limitador de taxa e recuo em 429. Devolve o JSON decodificado."""
    params = fred_params(api_key, today=today)
    for attempt in range(max_attempts):
        wait = limiter.reserve(clock())
        if wait > 0:
            await sleep(wait)
        try:
            resp = await client.get(FRED_URL, params=params)
        except httpx.HTTPError as exc:
            raise FredError(f"FRED: erro de rede ({type(exc).__name__})") from None
        if resp.status_code == 429:
            if attempt + 1 >= max_attempts:
                raise BlockedError("FRED: HTTP 429 após novas tentativas")
            retry_after = parse_retry_after(resp.headers.get("Retry-After"))
            await sleep(
                backoff_delay(attempt, base_s=FRED_BACKOFF_BASE_S, cap_s=FRED_BACKOFF_CAP_S, retry_after=retry_after)
            )
            continue
        if resp.status_code != 200:
            raise FredError(f"FRED: HTTP {resp.status_code}")
        return q.loads_exact(resp.text)
    raise BlockedError("FRED: HTTP 429 após novas tentativas")  # inalcançável; mantém o contrato explícito


def parse_fred_observations(data: Any) -> q.QuoteDraft:
    """Última observação válida (valor "." significa ausente e é ignorado). Variação vs. a observação anterior."""
    if not isinstance(data, dict) or not isinstance(data.get("observations"), list):
        raise q.FeedFormatError("FRED: resposta sem observações")
    valid: list[tuple[date, Decimal]] = []
    for row in data["observations"]:
        raw = row.get("value")
        if raw in (None, "", "."):
            continue
        try:
            valid.append((date.fromisoformat(row["date"]), Decimal(str(raw))))
        except (KeyError, ValueError, ArithmeticError):
            continue
    if not valid:
        raise q.FeedFormatError("FRED: nenhuma observação válida")
    valid.sort(key=lambda item: item[0])
    day, price = valid[-1]
    change: Decimal | None = None
    if len(valid) >= 2 and valid[-2][1] != 0:
        change = (price - valid[-2][1]) / valid[-2][1] * 100
    observed = datetime(day.year, day.month, day.day, tzinfo=UTC)
    return q.QuoteDraft(FRED_INSTRUMENT, FRED_LABEL, "fx_reference", "fred", price, change, observed)
