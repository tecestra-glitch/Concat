"""Stream público da Binance no worker (klines fechadas e bookTicker), ligado só com `FX_BINANCE_WS=1`.

Só leitura: não há nenhuma função de ordem neste módulo. Tudo o que entra aqui é REFERÊNCIA de mercado, nunca
executável, e não alimenta o grafo de ciclos.

Regras:
- Conexão válida por 24 h: a renovação acontece em `rotate_after` (23 h por padrão). A conexão nova abre antes de a
  antiga fechar, com `overlap` de escuta dupla; a gravação é idempotente, então nenhuma vela fechada se perde.
- Ping do cliente a cada `ping_s` (20 s); pings do servidor recebem pong automático da biblioteca `websockets`.
- No máximo 300 conexões novas a cada 5 min (janela deslizante, `ConnectionRateLimiter`).
- Recuo exponencial após erro; HTTP 418/429 espera um cooldown longo; HTTP 451 (bloqueio regional) desliga a fonte.
- Velas só entram quando fechadas (`k.x == true`). Gravação em lote a cada `flush_s`, em uma transação por lote.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import InvalidStatus

from ..config import Settings
from ..db import session_scope
from ..models import MarketBookTop, MarketCandle
from . import quotes as q
from . import vol

log = logging.getLogger("fronteira_fx.market.binance_ws")

MAX_NEW_CONNECTIONS = 300
CONNECTION_WINDOW = timedelta(minutes=5)
MAX_CONNECTION_AGE = timedelta(hours=23, minutes=50)  # a Binance encerra em 24 h; renovar antes disso
BLOCKED_COOLDOWN_S = 600.0  # HTTP 418/429 no handshake
STABLE_AFTER_S = 60.0  # conexão que ficou de pé tanto tempo zera o recuo
BACKOFF_CAP_S = 300.0
MAX_PENDING = 50_000  # limite de velas aguardando gravação (se o banco cair, não cresce sem fim)
INTERVALS = frozenset({"1m", "5m", "15m", "1h", "4h", "1d"})


class RegionBlockedError(RuntimeError):
    """HTTP 451: bloqueio regional. A fonte é desligada naquela região; não há contorno."""


class RateLimitedError(RuntimeError):
    """HTTP 418/429 no handshake: espera um cooldown longo antes de tentar de novo."""


class ConnectionLostError(RuntimeError):
    """A conexão caiu (fechamento ou erro de leitura)."""


class _Stopped(Exception):
    """Pedido de parada chegou durante uma espera."""


class ConnectionRateLimiter:
    """Janela deslizante: no máximo `max_new` conexões novas em cada `window`."""

    def __init__(self, max_new: int = MAX_NEW_CONNECTIONS, window: timedelta = CONNECTION_WINDOW) -> None:
        if max_new < 1:
            raise ValueError("max_new precisa ser pelo menos 1")
        self.max_new = max_new
        self.window = window
        self._stamps: deque[datetime] = deque()

    def _prune(self, now: datetime) -> None:
        cutoff = now - self.window
        while self._stamps and self._stamps[0] <= cutoff:
            self._stamps.popleft()

    def delay_s(self, now: datetime) -> float:
        """Segundos até poder abrir uma conexão nova (0 = agora)."""
        self._prune(now)
        n = len(self._stamps)
        if n < self.max_new:
            return 0.0
        free_at = self._stamps[n - self.max_new] + self.window
        return max(0.0, (free_at - now).total_seconds())

    def record(self, now: datetime) -> None:
        self._prune(now)
        self._stamps.append(now)

    def in_window(self, now: datetime) -> int:
        self._prune(now)
        return len(self._stamps)


def backoff_delay(attempt: int, base_s: float = 1.0, cap_s: float = BACKOFF_CAP_S) -> float:
    """Recuo exponencial: base, 2·base, 4·base… limitado por `cap_s`. `attempt` começa em 1."""
    if attempt < 1:
        raise ValueError("attempt começa em 1")
    return min(cap_s, base_s * (2 ** min(attempt - 1, 30)))


def build_url(base: str, symbols: list[str], interval: str) -> str:
    streams: list[str] = []
    for symbol in symbols:
        streams.append(f"{symbol.lower()}@kline_{interval}")
        streams.append(f"{symbol.lower()}@bookTicker")
    return f"{base.rstrip('/')}?streams={'/'.join(streams)}"


@dataclass(frozen=True, slots=True)
class KlineEvent:
    symbol: str
    interval: str
    candle: vol.Candle


@dataclass(frozen=True, slots=True)
class BookEvent:
    symbol: str
    update_id: int
    bid: Decimal
    bid_qty: Decimal
    ask: Decimal
    ask_qty: Decimal


def _ms(value: Any) -> datetime:
    return datetime(1970, 1, 1, tzinfo=UTC) + timedelta(milliseconds=int(value))


def parse_message(raw: str | bytes) -> KlineEvent | BookEvent | None:
    """Uma mensagem do stream combinado. None para o que não é dado (confirmações, vela ainda aberta, outros).

    Levanta `FeedFormatError` para JSON ou campos malformados.
    """
    try:
        msg = json.loads(raw, parse_float=Decimal)
    except (ValueError, TypeError) as exc:
        raise q.FeedFormatError("mensagem não é JSON") from exc
    if not isinstance(msg, dict):
        raise q.FeedFormatError("mensagem fora do formato")
    data = msg["data"] if "data" in msg and "stream" in msg else msg
    if not isinstance(data, dict):
        raise q.FeedFormatError("payload fora do formato")
    try:
        if data.get("e") == "kline":
            k = data["k"]
            if k.get("x") is not True:
                return None  # vela ainda aberta: nunca grava
            return KlineEvent(
                symbol=str(k["s"]),
                interval=str(k["i"]),
                candle=vol.Candle(
                    open_time=_ms(k["t"]),
                    close_time=_ms(k["T"]),
                    open=Decimal(str(k["o"])),
                    high=Decimal(str(k["h"])),
                    low=Decimal(str(k["l"])),
                    close=Decimal(str(k["c"])),
                ),
            )
        if data.get("e") is None and {"u", "s", "b", "B", "a", "A"} <= data.keys():
            return BookEvent(
                symbol=str(data["s"]),
                update_id=int(data["u"]),
                bid=Decimal(str(data["b"])),
                bid_qty=Decimal(str(data["B"])),
                ask=Decimal(str(data["a"])),
                ask_qty=Decimal(str(data["A"])),
            )
    except (KeyError, TypeError, ValueError, InvalidOperation, OverflowError) as exc:
        raise q.FeedFormatError("campos ausentes ou inválidos") from exc
    return None


@dataclass(frozen=True, slots=True)
class _PendingCandle:
    instrument: str
    interval: str
    candle: vol.Candle


@dataclass(frozen=True, slots=True)
class _PendingBook:
    instrument: str
    event: BookEvent


class PendingBuffer:
    """Itens aguardando gravação. Velas deduplicadas por (instrumento, intervalo, abertura); topo só o último."""

    def __init__(self, max_items: int = MAX_PENDING) -> None:
        self.max_items = max_items
        self.candles: dict[tuple[str, str, datetime], _PendingCandle] = {}
        self.books: dict[str, _PendingBook] = {}
        self.dropped = 0

    def __len__(self) -> int:
        return len(self.candles) + len(self.books)

    def add_candle(self, instrument: str, interval: str, candle: vol.Candle) -> None:
        self.candles[(instrument, interval, candle.open_time)] = _PendingCandle(instrument, interval, candle)
        self._trim()

    def set_book(self, instrument: str, event: BookEvent) -> None:
        self.books[event.symbol] = _PendingBook(instrument, event)

    def _trim(self) -> None:
        # descarta as velas mais antigas quando passa do limite (banco parado por muito tempo)
        while len(self.candles) > self.max_items:
            self.candles.pop(next(iter(self.candles)))
            self.dropped += 1

    def clear(self) -> None:
        self.candles.clear()
        self.books.clear()


@dataclass(frozen=True, slots=True)
class FlushResult:
    candles_added: int
    books_written: int


def flush_buffer(
    buf: PendingBuffer, session_factory: sessionmaker[Session], data_mode: str, now: datetime
) -> FlushResult:
    """Grava tudo em uma transação só. O buffer só é esvaziado depois do commit; falha mantém os itens."""
    if not buf.candles and not buf.books:
        return FlushResult(0, 0)
    candles = list(buf.candles.values())
    books = list(buf.books.values())
    with session_scope(session_factory) as session:
        added = _write_candles(session, candles, data_mode, now)
        for pending in books:
            _upsert_book(session, pending, data_mode, now)
    buf.clear()
    return FlushResult(added, len(books))


def _write_candles(session: Session, candles: list[_PendingCandle], data_mode: str, now: datetime) -> int:
    groups: dict[tuple[str, str], list[_PendingCandle]] = {}
    for c in candles:
        groups.setdefault((c.instrument, c.interval), []).append(c)
    added = 0
    for (instrument, interval), group in groups.items():
        existing = set(
            session.scalars(
                select(MarketCandle.open_time).where(
                    MarketCandle.instrument == instrument,
                    MarketCandle.interval == interval,
                    MarketCandle.data_mode == data_mode,
                    MarketCandle.open_time.in_([c.candle.open_time for c in group]),
                )
            )
        )
        for c in group:
            if c.candle.open_time in existing:
                continue
            session.add(
                MarketCandle(
                    instrument=instrument,
                    interval=interval,
                    open_time=c.candle.open_time,
                    close_time=c.candle.close_time,
                    open=c.candle.open,
                    high=c.candle.high,
                    low=c.candle.low,
                    close=c.candle.close,
                    captured_at=now,
                    data_mode=data_mode,
                )
            )
            added += 1
    return added


def _upsert_book(session: Session, pending: _PendingBook, data_mode: str, now: datetime) -> None:
    ev = pending.event
    row = session.get(MarketBookTop, (ev.symbol, data_mode))
    if row is None:
        row = MarketBookTop(symbol=ev.symbol, data_mode=data_mode)
        session.add(row)
    row.instrument = pending.instrument
    row.bid, row.bid_qty, row.ask, row.ask_qty = ev.bid, ev.bid_qty, ev.ask, ev.ask_qty
    row.update_id = ev.update_id
    row.captured_at = now


@dataclass(slots=True)
class _Link:
    ws: ClientConnection
    opened_at: datetime
    reader: asyncio.Task[None]


ConnectFn = Callable[..., Awaitable[ClientConnection]]


class BinanceStream:
    """Conexão com renovação antes de 24 h, limitador de conexões e gravação em lote. Roda como tarefa do worker."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        settings: Settings,
        *,
        clock: Callable[[], datetime] | None = None,
        url: str | None = None,
        rotate_after: timedelta | None = None,
        overlap_s: float | None = None,
        flush_s: float | None = None,
        ping_s: float | None = None,
        tick_s: float = 1.0,
        backoff_base_s: float = 1.0,
        limiter: ConnectionRateLimiter | None = None,
        connect_fn: ConnectFn | None = None,
    ) -> None:
        self.factory = session_factory
        self.settings = settings
        self.clock = clock or (lambda: datetime.now(tz=UTC))
        self.symbols = [s.strip().upper() for s in settings.binance_ws_symbols.split(",") if s.strip()]
        known = {sym: inst for sym, _label, inst in q.BINANCE_SYMBOLS}
        unknown = [s for s in self.symbols if s not in known]
        if unknown:
            raise ValueError(f"símbolos fora da lista de referência: {', '.join(unknown)}")
        if not self.symbols:
            raise ValueError("FX_BINANCE_WS_SYMBOLS vazio")
        if settings.binance_ws_interval not in INTERVALS:
            raise ValueError(f"intervalo não suportado: {settings.binance_ws_interval}")
        self.instruments = {s: known[s] for s in self.symbols}
        self.interval = settings.binance_ws_interval
        self.url = build_url(url or settings.binance_ws_url, self.symbols, self.interval)
        self.rotate_after = rotate_after or timedelta(seconds=settings.binance_ws_rotate_s)
        if self.rotate_after > MAX_CONNECTION_AGE:
            raise ValueError("renovação precisa ocorrer antes de 24 h (use até 23 h 50 min)")
        self.overlap_s = settings.binance_ws_overlap_s if overlap_s is None else overlap_s
        self.flush_s = settings.binance_ws_flush_s if flush_s is None else flush_s
        self.ping_s = settings.binance_ws_ping_s if ping_s is None else ping_s
        self.tick_s = tick_s
        self.backoff_base_s = backoff_base_s
        self.limiter = limiter or ConnectionRateLimiter()
        self._connect: ConnectFn = connect_fn or self._default_connect
        self.buffer = PendingBuffer()
        self.disabled_reason: str | None = None
        self.connections = 0
        self.messages = 0
        self.malformed = 0
        self._links: list[_Link] = []

    async def _default_connect(self, url: str, **kwargs: Any) -> ClientConnection:
        return await connect(url, open_timeout=15, **kwargs)

    # ------------------------------------------------------------------ ciclo principal
    async def run(self, stop: asyncio.Event) -> None:
        if self.settings.data_mode != "real":
            log.info("binance ws: desligado em data_mode=%s (só roda em real)", self.settings.data_mode)
            return
        flusher = asyncio.create_task(self._flush_loop(stop))
        attempt = 0
        try:
            while not stop.is_set():
                started = self.clock()
                try:
                    await self._session(stop)
                except _Stopped:
                    break
                except RegionBlockedError as exc:
                    self.disabled_reason = str(exc)
                    log.error("binance ws desligada: %s", exc)
                    return
                except RateLimitedError as exc:
                    log.warning("binance ws: %s; cooldown de %d s", exc, BLOCKED_COOLDOWN_S)
                    try:
                        await self._pause(stop, BLOCKED_COOLDOWN_S)
                    except _Stopped:
                        break
                except Exception as exc:  # queda de conexão, timeout, erro de handshake: recuo e reconecta
                    if (self.clock() - started).total_seconds() >= STABLE_AFTER_S:
                        attempt = 0
                    attempt += 1
                    delay = backoff_delay(attempt, self.backoff_base_s)
                    log.warning("binance ws caiu (%s); nova tentativa em %.1f s", exc, delay)
                    try:
                        await self._pause(stop, delay)
                    except _Stopped:
                        break
        finally:
            flusher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await flusher
            await self._close_all()
            self._flush_now()

    async def _session(self, stop: asyncio.Event) -> None:
        """Uma sessão: abre, lê, renova antes de 24 h. Retorna só quando `stop` for acionado."""
        link = await self._open(stop)
        try:
            while not stop.is_set():
                if (self.clock() - link.opened_at) >= self.rotate_after:
                    log.info("binance ws: renovando a conexão antes das 24 h")
                    fresh = await self._open(stop)  # abre a nova primeiro
                    await self._pause(stop, self.overlap_s)  # as duas escutam; duplicadas são descartadas na gravação
                    await self._close(link)
                    link = fresh
                    continue
                if link.reader.done():
                    exc = None if link.reader.cancelled() else link.reader.exception()
                    raise ConnectionLostError(str(exc) or "conexão fechada pelo servidor") from exc
                await self._pause(stop, self.tick_s)
        finally:
            await self._close(link)

    async def _open(self, stop: asyncio.Event) -> _Link:
        while True:
            delay = self.limiter.delay_s(self.clock())
            if delay <= 0:
                break
            log.info("binance ws: limite de 300 conexões em 5 min; aguardando %.1f s", delay)
            await self._pause(stop, delay)
        self.limiter.record(self.clock())
        try:
            ws = await self._connect(self.url, ping_interval=self.ping_s, ping_timeout=self.ping_s)
        except InvalidStatus as exc:
            code = exc.response.status_code
            if code == 451:
                raise RegionBlockedError("HTTP 451 (bloqueio regional da Binance)") from exc
            if code in (418, 429):
                raise RateLimitedError(f"HTTP {code} no handshake") from exc
            raise
        self.connections += 1
        link = _Link(ws=ws, opened_at=self.clock(), reader=asyncio.create_task(self._read(ws)))
        self._links.append(link)
        return link

    async def _read(self, ws: ClientConnection) -> None:
        async for raw in ws:
            self.messages += 1
            self._on_message(raw)

    def _on_message(self, raw: str | bytes) -> None:
        try:
            event = parse_message(raw)
        except q.FeedFormatError:
            self.malformed += 1
            return
        if isinstance(event, KlineEvent):
            instrument = self.instruments.get(event.symbol)
            if instrument is not None and event.interval == self.interval:
                self.buffer.add_candle(instrument, event.interval, event.candle)
        elif isinstance(event, BookEvent):
            instrument = self.instruments.get(event.symbol)
            if instrument is not None:
                self.buffer.set_book(instrument, event)

    async def _close(self, link: _Link) -> None:
        if link in self._links:
            self._links.remove(link)
        with contextlib.suppress(Exception):
            await link.ws.close()
        if not link.reader.done():
            link.reader.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await link.reader

    async def _close_all(self) -> None:
        for link in list(self._links):
            await self._close(link)

    # ------------------------------------------------------------------ gravação
    async def _flush_loop(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await self._pause(stop, self.flush_s)
            except _Stopped:
                return
            self._flush_now()

    def _flush_now(self) -> FlushResult | None:
        if not len(self.buffer):
            return None
        try:
            return flush_buffer(self.buffer, self.factory, self.settings.data_mode, self.clock())
        except Exception:
            log.exception("binance ws: falha ao gravar o lote; itens mantidos para a próxima tentativa")
            return None

    async def _pause(self, stop: asyncio.Event, seconds: float) -> None:
        """Espera `seconds`; acorda antes se `stop` for acionado (aí levanta `_Stopped`)."""
        if stop.is_set():
            raise _Stopped()
        if seconds > 0:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=seconds)
        if stop.is_set():
            raise _Stopped()
