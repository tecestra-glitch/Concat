"""brapi.dev (B3), somente para TESTE e validação manual. Não entra no agendador de produção.

Limites do plano gratuito: 15.000 requisições por mês e um ticker por chamada. Este módulo recusa lista de
tickers e para ao atingir o teto mensal. O token vem só da variável `BRAPI_TOKEN` (via `Settings`).
Erros nunca carregam a URL (o token vai na query string).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

import httpx

from . import quotes as q

BRAPI_BASE = "https://brapi.dev/api/quote"
BRAPI_MONTHLY_CAP = 15_000
TICKER_RE = re.compile(r"^[A-Z]{4}[0-9]{1,2}$")  # ações e FIIs da B3, ex.: PETR4, VALE3, HGLG11


class BrapiError(RuntimeError):
    """Falha da brapi sem URL nem token na mensagem."""


class BrapiQuota:
    """Contador mensal em memória. Ao atingir `cap`, `consume` recusa a chamada."""

    def __init__(self, cap: int = BRAPI_MONTHLY_CAP) -> None:
        if cap < 1:
            raise ValueError("teto mensal deve ser positivo")
        self.cap = cap
        self.used = 0

    def consume(self) -> None:
        if self.used >= self.cap:
            raise BrapiError("brapi: teto mensal de requisições atingido")
        self.used += 1


@dataclass(frozen=True, slots=True)
class BrapiQuote:
    ticker: str
    price: Decimal
    change_pct: Decimal | None
    observed_at: datetime | None


def single_ticker(ticker: str) -> str:
    """Exatamente um ticker por chamada. Lista (com vírgula ou espaço) é recusada."""
    value = ticker.strip().upper()
    if not TICKER_RE.match(value):
        raise ValueError("ticker inválido ou lista: a brapi aceita um ticker por chamada")
    return value


def brapi_request(ticker: str, token: str | None) -> tuple[str, dict[str, str]]:
    """URL e parâmetros. O token entra só como parâmetro e nunca aparece em mensagens de erro."""
    url = f"{BRAPI_BASE}/{single_ticker(ticker)}"
    params: dict[str, str] = {}
    if token:
        params["token"] = token
    return url, params


def parse_brapi_quote(data: Any, ticker: str) -> BrapiQuote:
    if not isinstance(data, dict) or not isinstance(data.get("results"), list) or not data["results"]:
        raise BrapiError("brapi: resposta sem resultados")
    row = data["results"][0]
    price = row.get("regularMarketPrice")
    if price is None:
        raise BrapiError("brapi: preço ausente")
    change = row.get("regularMarketChangePercent")
    observed: datetime | None = None
    raw_time = row.get("regularMarketTime")
    if isinstance(raw_time, str):
        try:
            observed = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        except ValueError:
            observed = None
    return BrapiQuote(
        ticker=single_ticker(ticker),
        price=Decimal(str(price)),
        change_pct=None if change is None else Decimal(str(change)),
        observed_at=observed,
    )


async def fetch_quote(client: httpx.AsyncClient, ticker: str, token: str | None, quota: BrapiQuota) -> BrapiQuote:
    url, params = brapi_request(ticker, token)
    quota.consume()
    try:
        resp = await client.get(url, params=params)
    except httpx.HTTPError as exc:
        raise BrapiError(f"brapi: erro de rede ({type(exc).__name__})") from None
    if resp.status_code != 200:
        raise BrapiError(f"brapi: HTTP {resp.status_code}")
    return parse_brapi_quote(q.loads_exact(resp.text), ticker)
