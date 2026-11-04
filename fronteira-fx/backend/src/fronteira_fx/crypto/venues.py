"""Adaptadores de exchange somente leitura: Kraken, Foxbit, OKX e Binance (host data-api.binance.vision).

Cada adaptador só conhece caminhos públicos de dados (allowlist regex), sem chave. Taxas são guardadas por
exchange (`VenueFee`); valor `None` significa não confirmado pela fonte. HTTP 451 desliga a fonte naquela região
(`RegionalGate`) e não há tentativa de contorno. 429 faz backoff com Retry-After; 418 (IP banido temporariamente)
interrompe a fonte até o fim do prazo informado.
"""

from __future__ import annotations

import asyncio
import re
import time
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar

import httpx

from .guard import RateLimited, ReadOnlyClient, RegionalBlocked, RegionalGate, VenueError
from .limits import Clock, Sleep, WindowLimiter, backoff_delay, parse_retry_after
from .types import Level, OrderBook, Side, Ticker, VenueFee, VwapFill, utc_now
from .vwap import vwap_for_target

SYMBOL_RE = re.compile(r"[A-Za-z0-9-]{3,20}")
MAX_RETRIES_429 = 3
BAN_418_DEFAULT_S = 120.0


def _dec(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise VenueError(f"número inválido na resposta: {value!r}") from exc


def _opt_dec(value: Any) -> Decimal | None:
    return None if value in (None, "") else _dec(value)


def _first(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return None


def _levels(raw: Any) -> tuple[Level, ...]:
    """Aceita [preço, quantidade, ...] ou {price/px, quantity/qty/amount}. Ignora níveis com quantidade zero."""
    out: list[Level] = []
    for item in raw or []:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            price, qty = item[0], item[1]
        elif isinstance(item, dict):
            price = _first(item, "price", "px")
            qty = _first(item, "quantity", "qty", "amount", "size")
        else:
            raise VenueError(f"nível de livro em formato inesperado: {item!r}")
        level = Level(price=_dec(price), qty=_dec(qty))
        if level.qty > 0:
            out.append(level)
    return tuple(out)


class CryptoVenue:
    name: ClassVar[str]
    base_url: ClassVar[str]
    allowed_paths: ClassVar[tuple[re.Pattern[str], ...]]
    default_fee: ClassVar[VenueFee]

    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        gate: RegionalGate | None = None,
        clock: Clock = time.monotonic,
        sleep: Sleep | None = None,
        fee: VenueFee | None = None,
    ) -> None:
        self.gate = gate if gate is not None else RegionalGate()
        self.fee = fee if fee is not None else self.default_fee
        self._clock = clock
        self._sleep: Sleep = sleep if sleep is not None else asyncio.sleep
        self._banned_until: float | None = None
        self._pause_until: float | None = None
        self._limiters: dict[str, WindowLimiter] = {}
        self._make_limiters()
        self.client = ReadOnlyClient(self.base_url, self.allowed_paths, transport=transport)

    # ------------------------------------------------------------------ hooks por exchange
    def _make_limiters(self) -> None:
        """Preenche `self._limiters` (um balde por grupo de endpoints)."""

    def _bucket(self, path: str) -> str:  # noqa: ARG002
        return "default"

    def _cost(self, path: str, params: dict[str, Any]) -> float:  # noqa: ARG002
        return 1.0

    def _observe(self, response: httpx.Response) -> None:  # noqa: ARG002
        """Lê cabeçalhos de uso (ex.: peso da Binance)."""

    def _check_envelope(self, data: Any) -> Any:
        return data

    # ------------------------------------------------------------------ núcleo de requisição
    def _parse_symbol(self, symbol: str) -> str:
        if not SYMBOL_RE.fullmatch(symbol):
            raise VenueError(f"símbolo inválido: {symbol!r}")
        return symbol

    async def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        params = params or {}
        blocked = self.gate.is_blocked(self.name)
        if blocked is not None:
            raise RegionalBlocked(self.name, f"fonte desligada nesta região (HTTP {blocked.status_code})")
        now = self._clock()
        if self._banned_until is not None and now < self._banned_until:
            raise RateLimited(self.name, self._banned_until, "IP em bloqueio temporário (418)")
        attempt = 0
        while True:
            if self._pause_until is not None and self._clock() < self._pause_until:
                await self._sleep(self._pause_until - self._clock())
            await self._limiter(path).acquire(self._cost(path, params))
            try:
                response = await self.client.get(path, params)
            except httpx.HTTPError as exc:
                raise VenueError(f"{self.name}: falha de transporte ({type(exc).__name__})") from exc
            self._observe(response)
            code = response.status_code
            if code == 451:
                self.gate.block(self.name, 451, "HTTP 451: bloqueio regional; fonte desligada, sem contorno")
                raise RegionalBlocked(self.name, "HTTP 451: bloqueio regional")
            if code == 418:
                wait = parse_retry_after(response.headers.get("Retry-After")) or BAN_418_DEFAULT_S
                self._banned_until = self._clock() + wait
                raise RateLimited(self.name, self._banned_until, "HTTP 418: IP bloqueado temporariamente")
            if code == 429:
                attempt += 1
                if attempt > MAX_RETRIES_429:
                    raise RateLimited(self.name, None, "HTTP 429 após tentativas de backoff")
                wait = parse_retry_after(response.headers.get("Retry-After")) or backoff_delay(attempt)
                await self._sleep(wait)
                continue
            if code >= 400:
                raise VenueError(f"{self.name}: HTTP {code}")
            try:
                data = response.json()
            except ValueError as exc:
                raise VenueError(f"{self.name}: resposta não é JSON") from exc
            return self._check_envelope(data)

    def _limiter(self, path: str) -> WindowLimiter:
        return self._limiters[self._bucket(path)]

    # ------------------------------------------------------------------ API pública do adaptador
    async def fetch_ticker(self, symbol: str) -> Ticker:
        raise NotImplementedError

    async def fetch_order_book(self, symbol: str, depth: int = 20) -> OrderBook:
        raise NotImplementedError

    async def vwap(self, symbol: str, side: Side, target: Decimal, depth: int = 50) -> VwapFill:
        book = await self.fetch_order_book(symbol, depth)
        return vwap_for_target(book, side, target, self.fee)

    async def aclose(self) -> None:
        await self.client.aclose()


# ---------------------------------------------------------------------- Kraken
class KrakenVenue(CryptoVenue):
    name = "kraken"
    base_url = "https://api.kraken.com"
    allowed_paths = (re.compile(r"/0/public/Ticker"), re.compile(r"/0/public/Depth"))
    # Taxas da plano triangulador (taker 0,80%; maker 0,40%). Conferir a tabela vigente antes de usar em cálculo.
    default_fee = VenueFee(
        venue="kraken", maker=Decimal("0.0040"), taker=Decimal("0.0080"),
        source="plano triangulador (0,40/0,80); conferir tabela vigente",
    )

    def _make_limiters(self) -> None:
        # Não há limite público documentado na página lida; 1 requisição por segundo é a folga adotada.
        self._limiters["default"] = WindowLimiter(1, 1.0, clock=self._clock, sleep=self._sleep)

    def _check_envelope(self, data: Any) -> Any:
        if not isinstance(data, dict):
            raise VenueError("kraken: envelope inesperado")
        errors = data.get("error") or []
        if errors:
            raise VenueError(f"kraken: {errors[0]}")
        return data.get("result") or {}

    @staticmethod
    def _single(result: dict[str, Any]) -> dict[str, Any]:
        if len(result) != 1:
            raise VenueError("kraken: par não encontrado ou ambíguo")
        entry = next(iter(result.values()))
        if not isinstance(entry, dict):
            raise VenueError("kraken: entrada inesperada")
        return entry

    async def fetch_ticker(self, symbol: str) -> Ticker:
        symbol = self._parse_symbol(symbol)
        entry = self._single(await self._get_json("/0/public/Ticker", {"pair": symbol}))
        return Ticker(
            venue=self.name, symbol=symbol,
            last=_opt_dec(entry["c"][0]), bid=_opt_dec(entry["b"][0]), ask=_opt_dec(entry["a"][0]),
            fetched_at=utc_now(),
        )

    async def fetch_order_book(self, symbol: str, depth: int = 20) -> OrderBook:
        symbol = self._parse_symbol(symbol)
        entry = self._single(await self._get_json("/0/public/Depth", {"pair": symbol, "count": depth}))
        bids = sorted(_levels(entry.get("bids")), key=lambda lvl: lvl.price, reverse=True)
        asks = sorted(_levels(entry.get("asks")), key=lambda lvl: lvl.price)
        return OrderBook(venue=self.name, symbol=symbol, bids=tuple(bids), asks=tuple(asks), fetched_at=utc_now())


# ---------------------------------------------------------------------- Foxbit
class FoxbitVenue(CryptoVenue):
    name = "foxbit"
    base_url = "https://api.foxbit.com.br/rest/v3"
    allowed_paths = (
        re.compile(r"/markets/[a-z0-9]{3,20}/orderbook"),
        re.compile(r"/markets/[a-z0-9]{3,20}/ticker/24hr"),
    )
    # Taxa não confirmada: None. Nunca assumir zero.
    default_fee = VenueFee(venue="foxbit", maker=None, taker=None, source="nao confirmada na fonte lida")

    def _make_limiters(self) -> None:
        # Documentação Foxbit: livro 10 req/2 s; ticker 12 req/2 s; limite por IP.
        self._limiters["orderbook"] = WindowLimiter(10, 2.0, clock=self._clock, sleep=self._sleep)
        self._limiters["ticker"] = WindowLimiter(12, 2.0, clock=self._clock, sleep=self._sleep)

    def _bucket(self, path: str) -> str:
        return "orderbook" if path.endswith("/orderbook") else "ticker"

    @staticmethod
    def _market(symbol: str) -> str:
        return symbol.lower()

    async def fetch_ticker(self, symbol: str) -> Ticker:
        market = self._market(self._parse_symbol(symbol))
        data = await self._get_json(f"/markets/{market}/ticker/24hr")
        if not isinstance(data, dict):
            raise VenueError("foxbit: ticker em formato inesperado")
        return Ticker(
            venue=self.name, symbol=market,
            last=_opt_dec(_first(data, "last_price", "last")),
            bid=_opt_dec(_first(data, "best_bid", "bid")),
            ask=_opt_dec(_first(data, "best_ask", "ask")),
            fetched_at=utc_now(),
        )

    async def fetch_order_book(self, symbol: str, depth: int = 20) -> OrderBook:
        market = self._market(self._parse_symbol(symbol))
        data = await self._get_json(f"/markets/{market}/orderbook", {"depth": depth})
        if not isinstance(data, dict):
            raise VenueError("foxbit: livro em formato inesperado")
        bids = sorted(_levels(data.get("bids")), key=lambda lvl: lvl.price, reverse=True)
        asks = sorted(_levels(data.get("asks")), key=lambda lvl: lvl.price)
        return OrderBook(venue=self.name, symbol=market, bids=tuple(bids), asks=tuple(asks), fetched_at=utc_now())


# ---------------------------------------------------------------------- OKX
class OkxVenue(CryptoVenue):
    name = "okx"
    base_url = "https://www.okx.com"
    allowed_paths = (re.compile(r"/api/v5/market/books"), re.compile(r"/api/v5/market/ticker"))
    default_fee = VenueFee(venue="okx", maker=None, taker=None, source="nao confirmada na fonte lida")

    def _make_limiters(self) -> None:
        # Limite público por IP; valor adotado de forma conservadora (confirmar na página de limites).
        self._limiters["default"] = WindowLimiter(20, 2.0, clock=self._clock, sleep=self._sleep)

    def _check_envelope(self, data: Any) -> Any:
        if not isinstance(data, dict):
            raise VenueError("okx: envelope inesperado")
        if str(data.get("code", "")) != "0":
            raise VenueError(f"okx: code {data.get('code')}: {data.get('msg', '')}".rstrip())
        rows = data.get("data") or []
        if not rows or not isinstance(rows[0], dict):
            raise VenueError("okx: sem dados para o instrumento")
        return rows[0]

    async def fetch_ticker(self, symbol: str) -> Ticker:
        inst = self._parse_symbol(symbol)
        row = await self._get_json("/api/v5/market/ticker", {"instId": inst})
        return Ticker(
            venue=self.name, symbol=inst,
            last=_opt_dec(row.get("last")), bid=_opt_dec(row.get("bidPx")), ask=_opt_dec(row.get("askPx")),
            fetched_at=utc_now(),
        )

    async def fetch_order_book(self, symbol: str, depth: int = 20) -> OrderBook:
        inst = self._parse_symbol(symbol)
        row = await self._get_json("/api/v5/market/books", {"instId": inst, "sz": depth})
        bids = sorted(_levels(row.get("bids")), key=lambda lvl: lvl.price, reverse=True)
        asks = sorted(_levels(row.get("asks")), key=lambda lvl: lvl.price)
        return OrderBook(venue=self.name, symbol=inst, bids=tuple(bids), asks=tuple(asks), fetched_at=utc_now())


# ---------------------------------------------------------------------- Binance (data-api.binance.vision)
def binance_depth_weight(limit: int) -> float:
    if limit <= 100:
        return 5.0
    if limit <= 500:
        return 25.0
    if limit <= 1000:
        return 50.0
    return 250.0


class BinanceVenue(CryptoVenue):
    name = "binance"
    base_url = "https://data-api.binance.vision"
    allowed_paths = (
        re.compile(r"/api/v3/depth"),
        re.compile(r"/api/v3/ticker/price"),
        re.compile(r"/api/v3/ticker/bookTicker"),
    )
    # Plano triangulador: 0,10% por lado (maker e taker) no spot.
    default_fee = VenueFee(
        venue="binance", maker=Decimal("0.0010"), taker=Decimal("0.0010"),
        source="plano triangulador (0,10% por lado spot); conferir tabela vigente",
    )
    WEIGHT_LIMIT_1M = 6000
    USED_WEIGHT_HEADER = "X-MBX-USED-WEIGHT-1M"

    def _make_limiters(self) -> None:
        # Usa 80% do teto de peso por minuto, deixando folga para outros processos do mesmo IP.
        self._limiters["weight"] = WindowLimiter(self.WEIGHT_LIMIT_1M * 0.8, 60.0, clock=self._clock, sleep=self._sleep)

    def _bucket(self, path: str) -> str:  # noqa: ARG002
        return "weight"

    def _cost(self, path: str, params: dict[str, Any]) -> float:
        if path == "/api/v3/depth":
            return binance_depth_weight(int(params.get("limit", 100)))
        if path == "/api/v3/ticker/price" and "symbol" not in params:
            return 4.0
        return 2.0

    def _observe(self, response: httpx.Response) -> None:
        raw = response.headers.get(self.USED_WEIGHT_HEADER)
        if raw is None:
            return
        try:
            used = int(raw)
        except ValueError:
            return
        if used >= self.WEIGHT_LIMIT_1M * 0.9:
            # Pausa até a próxima janela de 1 minuto antes de qualquer nova chamada.
            self._pause_until = self._clock() + 60.0

    async def fetch_ticker(self, symbol: str) -> Ticker:
        sym = self._parse_symbol(symbol).upper()
        price = await self._get_json("/api/v3/ticker/price", {"symbol": sym})
        book = await self._get_json("/api/v3/ticker/bookTicker", {"symbol": sym})
        return Ticker(
            venue=self.name, symbol=sym,
            last=_opt_dec(price.get("price")) if isinstance(price, dict) else None,
            bid=_opt_dec(book.get("bidPrice")), ask=_opt_dec(book.get("askPrice")),
            fetched_at=utc_now(),
        )

    async def fetch_order_book(self, symbol: str, depth: int = 20) -> OrderBook:
        sym = self._parse_symbol(symbol).upper()
        data = await self._get_json("/api/v3/depth", {"symbol": sym, "limit": depth})
        bids = sorted(_levels(data.get("bids")), key=lambda lvl: lvl.price, reverse=True)
        asks = sorted(_levels(data.get("asks")), key=lambda lvl: lvl.price)
        return OrderBook(venue=self.name, symbol=sym, bids=tuple(bids), asks=tuple(asks), fetched_at=utc_now())


VENUES: dict[str, type[CryptoVenue]] = {
    "kraken": KrakenVenue,
    "foxbit": FoxbitVenue,
    "okx": OkxVenue,
    "binance": BinanceVenue,
}
