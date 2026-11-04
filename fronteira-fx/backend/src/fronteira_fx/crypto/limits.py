"""Limitadores de taxa: janela deslizante com custo (contagem de requisições ou peso) e backoff.

Relógio e `sleep` são injetados para que os testes avancem o tempo sem esperar de verdade.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable

Clock = Callable[[], float]
Sleep = Callable[[float], Awaitable[None]]


class WindowLimiter:
    """No máximo `max_cost` de custo em qualquer janela de `window_s` segundos."""

    def __init__(
        self,
        max_cost: float,
        window_s: float,
        *,
        clock: Clock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        if max_cost <= 0 or window_s <= 0:
            raise ValueError("max_cost e window_s devem ser positivos")
        self.max_cost = max_cost
        self.window_s = window_s
        self._clock = clock
        self._sleep = sleep
        self._events: deque[tuple[float, float]] = deque()
        self._used = 0.0
        self._lock = asyncio.Lock()

    def _prune(self, now: float) -> None:
        while self._events and self._events[0][0] <= now - self.window_s:
            _, cost = self._events.popleft()
            self._used -= cost

    async def acquire(self, cost: float = 1.0) -> None:
        if cost <= 0 or cost > self.max_cost:
            raise ValueError(f"custo inválido: {cost} (máximo {self.max_cost})")
        async with self._lock:
            while True:
                now = self._clock()
                self._prune(now)
                if self._used + cost <= self.max_cost:
                    self._events.append((now, cost))
                    self._used += cost
                    return
                wait = self._events[0][0] + self.window_s - now
                await self._sleep(max(wait, 0.0))


def backoff_delay(attempt: int, *, base: float = 1.0, cap: float = 60.0) -> float:
    """Espera exponencial: base * 2^(tentativa-1), limitada a `cap`. `attempt` começa em 1."""
    if attempt < 1:
        raise ValueError("attempt começa em 1")
    return min(cap, base * (2 ** (attempt - 1)))


def parse_retry_after(value: str | None) -> float | None:
    """Retry-After em segundos (inteiro ou decimal). Data HTTP não é usada: retorna None e o chamador faz backoff."""
    if value is None:
        return None
    try:
        seconds = float(value.strip())
    except ValueError:
        return None
    return seconds if seconds >= 0 else None
