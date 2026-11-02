"""Geradores demo determinísticos do pregão (velas, resumo da sessão, sessões das casas).

Em modo `demo` os handlers nunca tocam o banco nem a rede: cada vela sai de FNV-1a + LCG sobre a chave da
série, o intervalo e o índice do bucket (§0.9). Só `demo_candles` lê o relógio, e só quando `end` é None.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fronteira_fx.schemas_candles import TF_SECONDS, Candle, HouseSession, SessionStats, Timeframe
from fronteira_fx.services.candles import bucket_start, ensure_utc, fmt, last_bucket_start, pair_of
from fronteira_fx.services.market_hours import house_sessions, load_market_hours
from fronteira_fx.services.session_stats import day_start_asuncion

DEMO_ANCHOR: dict[str, Decimal] = {"USD/PYG": Decimal("5940"), "USD/BRL": Decimal("5.43"), "BRL/PYG": Decimal("1100")}
DEMO_VOL: dict[str, float] = {"15m": 0.0015, "1h": 0.003, "4h": 0.006, "1d": 0.012}
DEMO_HOUSES: list[dict] = [
    {
        "id": "chaco",
        "name": "Cambios Chaco",
        "city": "CDE",
        "channel": "physical",
        "reference": False,
        "pairs": ["USD/PYG", "BRL/PYG"],
    },
    {
        "id": "alberdi",
        "name": "Cambios Alberdi",
        "city": "CDE",
        "channel": "physical",
        "reference": False,
        "pairs": ["USD/PYG", "BRL/PYG"],
    },
    {
        "id": "norte",
        "name": "Cambios Norte",
        "city": "ASU",
        "channel": "physical",
        "reference": False,
        "pairs": ["USD/PYG"],
    },
    {
        "id": "bonanza",
        "name": "Bonanza Cambios",
        "city": "ASU",
        "channel": "physical",
        "reference": False,
        "pairs": ["USD/PYG", "BRL/PYG"],
    },
    {
        "id": "ueno",
        "name": "ueno",
        "city": None,
        "channel": "digital",
        "reference": False,
        "pairs": ["USD/PYG", "BRL/PYG"],
    },
    {"id": "nomad", "name": "Nomad", "city": None, "channel": "digital", "reference": False, "pairs": ["USD/BRL"]},
    {
        "id": "bcp",
        "name": "BCP (referência)",
        "city": None,
        "channel": "digital",
        "reference": True,
        "pairs": ["USD/PYG", "BRL/PYG"],
    },
]

_WEEK_S = 604800
_FNV_OFFSET = 2166136261
_FNV_PRIME = 16777619
_LCG_MULT = 1664525
_LCG_INC = 1013904223
_MASK32 = 2**32 - 1
_SPREAD_RATIO = 0.006
_SUNDAY = 7  # `isoweekday()`


def fnv1a(s: str) -> int:
    """FNV-1a de 32 bits sobre os bytes UTF-8 de `s`."""
    h = _FNV_OFFSET
    for byte in s.encode("utf-8"):
        h = ((h ^ byte) * _FNV_PRIME) & _MASK32
    return h


def lcg(seed: int) -> Callable[[], float]:
    """Gerador congruente linear: cada chamada avança o estado e devolve `s / 2**32`, em `[0, 1)`."""
    state = seed & _MASK32

    def next_value() -> float:
        nonlocal state
        state = (state * _LCG_MULT + _LCG_INC) & _MASK32
        return state / 2**32

    return next_value


def drift(i: int, grid_s: int) -> float:
    """Deriva semanal suave: `1 + 0.004·sin(2π·((i·grid_s) mod 604800)/604800)`."""
    return 1 + 0.004 * math.sin(2 * math.pi * ((i * grid_s) % _WEEK_S) / _WEEK_S)


def _anchor(key: str) -> float:
    return float(DEMO_ANCHOR.get(pair_of(key), Decimal("1")))


def _is_physical(key: str) -> bool:
    """Casa presencial: segmento `[1]` diferente de `digital`; chave sem segmento `[1]` conta como presencial."""
    parts = key.split(":")
    return (parts[1] if len(parts) > 1 else "") != "digital"


def _is_sunday(i: int, grid_s: int) -> bool:
    return datetime.fromtimestamp(i * grid_s, tz=UTC).isoweekday() == _SUNDAY


def _canon(value: Decimal) -> Decimal:
    """Mesma normalização da API (`fmt`: 8 casas, sem zeros à direita), mantida como `Decimal`."""
    return Decimal(fmt(value) or "0")


def _from_float(x: float) -> Decimal:
    """Valor de 4 casas: `Decimal(str(round(x, 4)))`, sem passar por float binário na saída."""
    return _canon(Decimal(str(round(x, 4))))


def demo_close(key: str, tf: Timeframe, i: int) -> float:
    """Fechamento do bucket `i` (primeiro sorteio de `lcg(seed_i)`)."""
    u1 = lcg(fnv1a(f"{key}:{tf}:{i}"))()
    return _anchor(key) * drift(i, TF_SECONDS[tf]) * (1 + (u1 - 0.5) * DEMO_VOL[tf])


def demo_candle(key: str, tf: Timeframe, i: int) -> Candle:
    """Vela do bucket `i`: `o` é o fechamento do bucket anterior; `c` é `demo_close(key, tf, i)`."""
    grid_s = TF_SECONDS[tf]
    vol = DEMO_VOL[tf]
    r = lcg(fnv1a(f"{key}:{tf}:{i}"))
    _u1, u2, u3, u4 = r(), r(), r(), r()  # u1 já está embutido em `demo_close(key, tf, i)`
    o = demo_close(key, tf, i - 1)
    c = demo_close(key, tf, i)
    h = max(o, c) * (1 + u2 * vol / 2)
    lo = min(o, c) * (1 - u3 * vol / 2)
    spread = _anchor(key) * drift(i, grid_s) * _SPREAD_RATIO
    return Candle(
        t=datetime.fromtimestamp(i * grid_s, tz=UTC),
        o=_from_float(o),
        h=_from_float(h),
        l=_from_float(lo),
        c=_from_float(c),
        n=1 + math.floor(u4 * 12),
        spread_avg=_from_float(spread),
        buy_c=_from_float(c - spread / 2),
        sell_c=_from_float(c + spread / 2),
        data_mode="demo",
    )


def demo_candles(key: str, tf: Timeframe, start: datetime | None, end: datetime | None, limit: int) -> list[Candle]:
    """Até `limit` velas ascendentes terminando no último bucket antes de `end` (ou no do relógio, se `end` é None).

    `end` é exclusivo, como no caminho real: numa fronteira (`end` = 12:00Z em `1h`) a última vela é 11:00
    (`last_bucket_start`, QA-6). Com `start`, a caminhada para em `bucket_start(start)`. Em casas presenciais os
    buckets de domingo UTC não são emitidos nem contados; em `digital` são emitidos normalmente.
    """
    grid_s = TF_SECONDS[tf]
    last = bucket_start(datetime.now(UTC), grid_s) if end is None else last_bucket_start(end, grid_s)
    i = math.floor(last.timestamp()) // grid_s
    floor_i = None if start is None else math.floor(bucket_start(ensure_utc(start), grid_s).timestamp()) // grid_s
    physical = _is_physical(key)
    out: list[Candle] = []
    while len(out) < limit and (floor_i is None or i >= floor_i):
        if not (physical and _is_sunday(i, grid_s)):
            out.append(demo_candle(key, tf, i))
        i -= 1
    out.reverse()
    return out


def _session_stats_for(key: str, day_start: datetime, now: datetime) -> SessionStats:
    candles = [c for c in demo_candles(key, "15m", None, now, 96) if c.t >= day_start]
    if not candles:
        return SessionStats(key=key, day_start=day_start, data_mode="demo")
    first, last = candles[0], candles[-1]
    open_ = first.o
    last_c = last.c
    change_abs = last_c - open_
    change_pct = None if open_ == 0 else change_abs / open_ * 100
    spreads = [c.spread_avg for c in candles if c.spread_avg is not None]
    spread_avg = sum(spreads, Decimal(0)) / len(spreads) if spreads else None
    pair = pair_of(key)
    houses = sum(1 for h in DEMO_HOUSES if not h["reference"] and pair in h["pairs"])
    return SessionStats(
        key=key,
        day_start=day_start,
        open=_canon(open_),
        high=_canon(max(c.h for c in candles)),
        low=_canon(min(c.l for c in candles)),
        last=_canon(last_c),
        last_at=last.t + timedelta(seconds=TF_SECONDS["15m"] - 1),
        change_abs=_canon(change_abs),
        change_pct=None if change_pct is None else _canon(change_pct),
        n_quotes=sum(c.n for c in candles),
        spread_avg=None if spread_avg is None else _canon(spread_avg),
        houses=houses,
        data_mode="demo",
    )


def demo_session_stats(keys: list[str], now: datetime) -> list[SessionStats]:
    """Resumo do dia (00:00 em Assunção) por chave, na mesma ordem. Sem velas no dia → campos nulos."""
    now = ensure_utc(now)
    day_start = day_start_asuncion(now)
    return [_session_stats_for(key, day_start, now) for key in keys]


def demo_house_sessions(now: datetime) -> list[HouseSession]:
    """Uma `HouseSession` por entrada de `DEMO_HOUSES`, na mesma ordem; nome, cidade e canal vêm da lista."""
    hours = load_market_hours()
    table = {f"demo-{h['id']}": hours.get(h["id"]) for h in DEMO_HOUSES}
    reference_ids = {f"demo-{h['id']}" for h in DEMO_HOUSES if h["reference"]}
    sessions = house_sessions(ensure_utc(now), table, "demo", reference_ids=reference_ids)
    return [
        session.model_copy(update={"name": h["name"], "city": h["city"], "channel": h["channel"]})
        for session, h in zip(sessions, DEMO_HOUSES, strict=True)
    ]
