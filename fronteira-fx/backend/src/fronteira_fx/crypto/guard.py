"""Barreiras de somente leitura: cliente HTTP que só faz GET em caminhos permitidos, e registro de bloqueio regional.

O cliente não expõe `post`, `request` nem `send`. Qualquer caminho fora da allowlist do adaptador levanta
`ReadOnlyViolation` antes de sair da máquina. Redirecionamentos não são seguidos (um 3xx para outro host
não pode trocar o destino sem passar pela allowlist de novo).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from .types import utc_now

USER_AGENT = "fronteira-fx-readonly/0.1 (+dados publicos, sem chave)"


class VenueError(RuntimeError):
    """Falha de uma exchange (transporte, HTTP de erro, JSON ou formato inesperado)."""


class ReadOnlyViolation(VenueError):
    """Tentativa de chamar um caminho que não é de leitura pública allowlistada."""


class RateLimited(VenueError):
    def __init__(self, venue: str, retry_at: float | None, message: str) -> None:
        super().__init__(message)
        self.venue = venue
        self.retry_at = retry_at


class RegionalBlocked(VenueError):
    """HTTP 451 (ou equivalente): a fonte está desligada nesta região. Nunca há tentativa de contorno."""

    def __init__(self, venue: str, message: str) -> None:
        super().__init__(message)
        self.venue = venue


@dataclass(frozen=True, slots=True)
class RegionalBlock:
    venue: str
    status_code: int
    at: datetime
    reason: str


class RegionalGate:
    """Registro em memória das fontes desligadas por bloqueio regional. Uma vez bloqueada, não se tenta de novo."""

    def __init__(self) -> None:
        self._blocked: dict[str, RegionalBlock] = {}

    def block(self, venue: str, status_code: int, reason: str) -> RegionalBlock:
        entry = RegionalBlock(venue=venue, status_code=status_code, at=utc_now(), reason=reason)
        self._blocked.setdefault(venue, entry)
        return self._blocked[venue]

    def is_blocked(self, venue: str) -> RegionalBlock | None:
        return self._blocked.get(venue)

    def snapshot(self) -> list[RegionalBlock]:
        return list(self._blocked.values())


class ReadOnlyClient:
    """GET apenas, contra um host fixo, em caminhos que casam com a allowlist (regex com fullmatch)."""

    def __init__(
        self,
        base_url: str,
        allowed: Iterable[re.Pattern[str]],
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._allowed = tuple(allowed)
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            transport=transport,
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )

    def is_allowed(self, path: str) -> bool:
        return any(pattern.fullmatch(path) for pattern in self._allowed)

    async def get(self, path: str, params: Mapping[str, Any] | None = None) -> httpx.Response:
        if not self.is_allowed(path):
            raise ReadOnlyViolation(f"caminho fora da allowlist de leitura: {path}")
        return await self._client.get(path, params=dict(params) if params else None)

    async def aclose(self) -> None:
        await self._client.aclose()
