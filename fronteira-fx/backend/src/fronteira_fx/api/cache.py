"""Cache em memória com TTL para as rotas de leitura. Um por aplicação (`app.state.read_cache`), para que dois apps
com bancos diferentes (testes, instâncias) nunca compartilhem respostas.

Só guarda respostas de sucesso: uma exceção não é cacheada. TTL 0 desliga o cache. O relógio é injetável.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

MAX_ENTRIES = 256


class TtlCache:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._items: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get_or_set(self, key: str, ttl_s: float, compute: Callable[[], Any]) -> Any:
        if ttl_s <= 0:
            return compute()
        now = self._clock()
        with self._lock:
            hit = self._items.get(key)
        if hit is not None and hit[0] > now:
            return hit[1]
        value = compute()
        with self._lock:
            if len(self._items) >= MAX_ENTRIES:
                self._prune(now)
            self._items[key] = (now + ttl_s, value)
        return value

    def _prune(self, now: float) -> None:
        for k in [k for k, (expires, _) in self._items.items() if expires <= now]:
            del self._items[k]
        if len(self._items) >= MAX_ENTRIES:  # tudo ainda válido: descarta o mais antigo (ordem de inserção)
            del self._items[next(iter(self._items))]

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)
