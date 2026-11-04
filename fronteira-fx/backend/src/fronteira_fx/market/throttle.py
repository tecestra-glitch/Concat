"""Limitador de taxa e recuo para fontes macro (módulo `market`). Funções puras: relógio e espera são injetados.

- `SlidingWindowLimiter.reserve(now)` devolve quantos segundos esperar antes de uma chamada, sem dormir. Com
  `max_calls` por `window_s`, nenhuma janela de 60 s recebe mais chamadas que o limite.
- `backoff_delay` calcula a espera após HTTP 429 (exponencial, com teto e `Retry-After` quando for numérico).
- `BlockedError` é o sinal de "fonte recusou": o agendador recua mais que num erro comum.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class BlockedError(RuntimeError):
    """Provedor recusou (418/429 ou WAF): o agendador recua mais que num erro comum."""


@dataclass(slots=True)
class SlidingWindowLimiter:
    max_calls: int
    window_s: float = 60.0
    _slots: list[float] = field(default_factory=list)  # instantes já reservados, em ordem crescente

    def __post_init__(self) -> None:
        if self.max_calls < 1 or self.window_s <= 0:
            raise ValueError("limite e janela devem ser positivos")

    def reserve(self, now: float) -> float:
        """Reserva uma chamada. Devolve a espera em segundos (0.0 = pode ir agora)."""
        horizon = now - self.window_s
        self._slots = [t for t in self._slots if t > horizon]
        if len(self._slots) < self.max_calls:
            start = now
        else:
            # a chamada que libera a vaga é a `max_calls`-ésima mais recente
            start = max(now, self._slots[-self.max_calls] + self.window_s)
        self._slots.append(start)
        return start - now


def backoff_delay(attempt: int, *, base_s: float = 2.0, cap_s: float = 30.0, retry_after: float | None = None) -> float:
    """Espera antes da tentativa seguinte após 429: base × 2^attempt, limitada a `cap_s`.

    `Retry-After` numérico do provedor vale quando é maior que a espera calculada, sempre limitado a `cap_s`.
    """
    if attempt < 0:
        raise ValueError("attempt não pode ser negativo")
    delay = min(cap_s, base_s * (2**attempt))
    if retry_after is not None and retry_after > delay:
        delay = min(cap_s, retry_after)
    return delay


def parse_retry_after(value: str | None) -> float | None:
    """Só segundos decimais. Data HTTP e lixo viram `None` (o chamador usa o cálculo próprio)."""
    if value is None:
        return None
    text = value.strip()
    if not text or len(text) > 10:
        return None
    try:
        seconds = float(text)
    except ValueError:
        return None
    return seconds if seconds >= 0 else None
