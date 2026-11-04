"""Sondagem do módulo `market`, rodada pelo worker a cada tick (nunca pela API).

Uma única fila de agendamento (`watch.scheduler.Scheduler`) com piso de 60 s por fonte: o worker chama
`run_once()` a cada tick e só as fontes vencidas são consultadas. Erro ou bloqueio (HTTP 418/429) recua
com backoff. Só roda em `data_mode = real`; `demo` tem dados semeados e `simulation` não consulta nada.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from ..config import Settings
from ..db import session_scope
from ..models import MarketCandle, MarketQuote
from ..services import events as events_svc
from ..watch.fetcher import DEFAULT_TIMEOUT_S, conditional_get, default_headers
from ..watch.scheduler import Scheduler, SchedulerConfig
from . import macro, vol
from . import news as news_mod
from . import quotes as q
from . import reference as ref
from . import sentiment as sentiment_mod
from .throttle import BlockedError, SlidingWindowLimiter

log = logging.getLogger("fronteira_fx.market")

EVENT_VOLATILITY_ALERT = "market.volatility_alert"
EVENT_REFERENCE_DEVIATION = "market.reference_deviation"
BINANCE_SOURCES = ("binance-ticker", "binance-candles")
FX_SOURCE = "frankfurter"
BCB_SOURCE = "bcb-sgs"
KEEP_5M_DAYS = 3
KEEP_1D_DAYS = 60
BINANCE_LIMIT_5M = 300  # 288 velas fechadas + a aberta (descartada pelo parser)
BINANCE_LIMIT_1D = 21  # 20 fechadas + a aberta


@dataclass(frozen=True, slots=True)
class PollResult:
    source_id: str
    ok: bool
    changed: bool
    error: str | None = None


def build_scheduler(
    clock: Callable[[], datetime] | None = None, *, oxr_enabled: bool = False, fred_enabled: bool = False
) -> Scheduler:
    """Piso 60 s; mercado de cripto e de câmbio não têm horário comercial, então sem fator fora do expediente.

    Open Exchange Rates entra só com chave (`OXR_APP_ID`), de hora em hora (teto de 1.000 por mês no contador).
    A fonte FRED só entra com `fred_enabled` (há `FRED_API_KEY`). brapi e yfinance nunca entram aqui.
    """
    config = SchedulerConfig(
        min_interval_s=60,
        max_interval_s=900,
        business_hours=(0, 24),
        business_days=frozenset(range(7)),
        off_hours_factor=1.0,
    )
    scheduler = Scheduler(config, clock=clock) if clock else Scheduler(config)
    for feed in news_mod.FEEDS:
        scheduler.add_source(feed.feed_id, feed.poll_interval_s)
    # Fear & Greed: o índice é diário, então o teto é 1 h (o agendador limita a 900 s por padrão).
    scheduler.add_source(sentiment_mod.FNG_SOURCE, sentiment_mod.FNG_POLL_INTERVAL_S, max_interval_s=3600)
    scheduler.add_source(FX_SOURCE, 900)
    scheduler.add_source(BCB_SOURCE, 900)
    scheduler.add_source("binance-ticker", 60)
    scheduler.add_source("binance-candles", 300)
    if oxr_enabled:
        scheduler.add_source(ref.OXR_SOURCE, ref.OXR_POLL_INTERVAL_S, max_interval_s=ref.OXR_POLL_INTERVAL_S)
    if fred_enabled:
        scheduler.add_source(macro.FRED_SOURCE, macro.FRED_POLL_INTERVAL_S, max_interval_s=21600)
    return scheduler


class MarketPoller:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        settings: Settings,
        *,
        client: httpx.AsyncClient | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.factory = session_factory
        self.settings = settings
        self.clock = clock or (lambda: datetime.now(tz=UTC))
        self._fred_key = settings.fred_api_key.get_secret_value() if settings.fred_api_key else None
        self.scheduler = build_scheduler(
            self.clock, oxr_enabled=bool(settings.oxr_app_id), fred_enabled=bool(self._fred_key)
        )
        self._fred_limiter = SlidingWindowLimiter(macro.FRED_MAX_PER_MINUTE)
        self._client = client
        self._owns_client = client is None
        self._validators: dict[str, tuple[str | None, str | None]] = {}
        self._alert_state: dict[str, bool] = {}
        self._deviation_state: dict[tuple[str, str, str], bool] = {}

    @property
    def enabled(self) -> bool:
        return self.settings.data_mode == "real"

    def http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT_S, follow_redirects=True)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    async def run_once(self) -> list[PollResult]:
        """Consulta só as fontes vencidas. Nunca mais de uma vez por fonte dentro do piso."""
        if not self.enabled:
            return []
        now = self.clock()
        results: list[PollResult] = []
        for source_id in self.scheduler.due(now):
            self.scheduler.mark_started(source_id, now)
            try:
                changed = await self._dispatch(source_id, now)
            except BlockedError as exc:
                self.scheduler.record_result(source_id, changed=False, blocked=True, now=self.clock())
                results.append(PollResult(source_id, ok=False, changed=False, error=str(exc)))
                log.warning("market %s blocked: %s", source_id, exc)
            except Exception as exc:  # one failing source never stops the others
                self.scheduler.record_result(source_id, changed=False, error=True, now=self.clock())
                results.append(PollResult(source_id, ok=False, changed=False, error=str(exc)[:300]))
                log.warning("market %s failed: %s", source_id, exc)
            else:
                self.scheduler.record_result(source_id, changed=changed, now=self.clock())
                results.append(PollResult(source_id, ok=True, changed=changed))
        return results

    async def _dispatch(self, source_id: str, now: datetime) -> bool:
        feed = news_mod.FEEDS_BY_ID.get(source_id)
        if feed is not None:
            return await self._poll_feed(feed, now)
        if source_id == sentiment_mod.FNG_SOURCE:
            return await self._poll_fng(now)
        if source_id == FX_SOURCE:
            return await self._poll_frankfurter(now)
        if source_id == macro.FRED_SOURCE:
            return await self._poll_fred(now)
        if source_id == BCB_SOURCE:
            return await self._poll_bcb(now)
        if source_id == "binance-ticker":
            return await self._poll_binance_ticker(now)
        if source_id == "binance-candles":
            return await self._poll_binance_candles(now)
        if source_id == ref.OXR_SOURCE:
            return await self._poll_oxr(now)
        raise KeyError(f"fonte de mercado desconhecida: {source_id}")

    async def _get_json(self, url: str, params: dict[str, str] | None = None) -> Any:
        resp = await self.http().get(url, params=params, headers=default_headers())
        if resp.status_code in (418, 429):
            raise BlockedError(f"HTTP {resp.status_code} de {url.split('/')[2]}")
        resp.raise_for_status()
        return q.loads_exact(resp.text)

    # ----------------------------------------------------------------- notícias
    async def _poll_feed(self, feed: news_mod.FeedSpec, now: datetime) -> bool:
        etag, last_modified = self._validators.get(feed.feed_id, (None, None))
        out = await conditional_get(feed.url, etag=etag, last_modified=last_modified, client=self.http())
        if out.blocked:
            raise BlockedError(out.error or "bloqueado")
        if out.error:
            raise RuntimeError(out.error)
        self._validators[feed.feed_id] = (out.etag, out.last_modified)
        if out.not_modified or not out.content:
            return False  # 304: nada mudou, nada a ler
        entries = news_mod.parse_feed(out.content, keep_excerpt=feed.keep_excerpt)  # sem itens: lista vazia
        with session_scope(self.factory) as session:
            new = news_mod.ingest(session, feed, entries, captured_at=now, data_mode=self.settings.data_mode)
            return bool(new)

    # ----------------------------------------------------------------- sentimento
    async def _poll_fng(self, now: datetime) -> bool:
        data = await self._get_json(sentiment_mod.FNG_URL, sentiment_mod.FNG_PARAMS)
        try:
            draft = sentiment_mod.parse_fng(data)
        except sentiment_mod.SentimentFormatError as exc:
            raise RuntimeError(f"Fear & Greed: {exc}") from exc
        with session_scope(self.factory) as session:
            return sentiment_mod.ingest_fng(session, draft, captured_at=now, data_mode=self.settings.data_mode)

    # ----------------------------------------------------------------- referência
    def _upsert_quotes(self, session: Session, drafts: list[q.QuoteDraft], now: datetime) -> bool:
        changed = False
        for d in drafts:
            row = session.get(MarketQuote, d.instrument)
            if row is None:
                session.add(
                    MarketQuote(
                        instrument=d.instrument,
                        label=d.label,
                        kind=d.kind,
                        source=d.source,
                        price=d.price,
                        change_pct=d.change_pct,
                        observed_at=d.observed_at,
                        captured_at=now,
                        data_mode=self.settings.data_mode,
                    )
                )
                changed = True
                continue
            if row.price != d.price or row.observed_at != d.observed_at:
                changed = True
            row.label, row.kind, row.source = d.label, d.kind, d.source
            row.price, row.change_pct, row.observed_at, row.captured_at = d.price, d.change_pct, d.observed_at, now
        session.flush()
        return changed

    async def _poll_frankfurter(self, now: datetime) -> bool:
        data = await self._get_json(
            q.FRANKFURTER_URL, {"base": "USD", "quotes": ",".join(c for c, _ in q.FRANKFURTER_QUOTES)}
        )
        drafts = q.parse_frankfurter(data)
        with session_scope(self.factory) as session:
            changed = self._upsert_quotes(session, drafts, now)
            self._store_references(session, ref.from_frankfurter_drafts(drafts, collected_at=now), now)
            return changed

    async def _poll_bcb(self, now: datetime) -> bool:
        today = now.astimezone(q.BRT).date()
        drafts: list[q.QuoteDraft] = []
        for code, instrument, label in q.BCB_SERIES:
            start = today - timedelta(days=q.SGS_LOOKBACK_DAYS[code])
            url, params = q.sgs_request(code, start, today)  # datas obrigatórias, janela ≤ 10 anos
            data = await self._get_json(url, params)
            drafts.append(q.parse_bcb_series(data, instrument, label))
        with session_scope(self.factory) as session:
            changed = self._upsert_quotes(session, drafts, now)
            self._store_references(session, ref.from_bcb_drafts(drafts, collected_at=now), now)
            return changed

    # ----------------------------------------------------------------- referências de câmbio (U03)
    def _store_references(self, session: Session, quotes: list[ref.ReferenceQuote], now: datetime) -> None:
        """Grava as referências e compara as fontes. Nada aqui é executável."""
        ref.upsert_reference_quotes(session, quotes, data_mode=self.settings.data_mode)
        self._check_reference_deviations(session, now)

    def _check_reference_deviations(self, session: Session, now: datetime) -> None:
        """Alerta só na transição para acima do limite configurado (não repete a cada sondagem)."""
        threshold = self.settings.fx_reference_deviation_alert_pct
        latest = ref.latest_by_source(ref.recent_references(session, now=now, data_mode=self.settings.data_mode))
        for dev in ref.compare(latest, threshold):
            key = (dev.instrument, dev.source_a, dev.source_b)
            was = self._deviation_state.get(key, False)
            self._deviation_state[key] = dev.over
            if not dev.over or was:
                continue
            events_svc.append_event(
                session,
                EVENT_REFERENCE_DEVIATION,
                ref.deviation_event_payload(dev, threshold_pct=threshold),
                data_mode=self.settings.data_mode,
                ts=now,
            )

    async def _poll_oxr(self, now: datetime) -> bool:
        """Open Exchange Rates (base USD). A chave vai só na query da requisição e nunca em mensagem de erro."""
        key = self.settings.oxr_app_id
        if not key:
            raise RuntimeError("Open Exchange Rates sem OXR_APP_ID")
        ceiling = ref.effective_ceiling(ref.OXR_SOURCE, self.settings.oxr_monthly_cap)
        # reserva commitada ANTES da requisição: uma falha de rede também conta no teto
        with session_scope(self.factory) as session:
            if not ref.reserve_call(session, ref.OXR_SOURCE, now, ceiling):
                log.warning("OXR: teto mensal de %d chamadas atingido; sem consulta até o próximo mês", ceiling)
                return False
        try:
            resp = await self.http().get(
                ref.OXR_URL,
                params={"app_id": key, "symbols": ",".join(ref.OXR_SYMBOLS)},
                headers=default_headers(),
            )
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Open Exchange Rates: erro de rede ({type(exc).__name__})") from None
        if resp.status_code in (418, 429):
            raise BlockedError(f"HTTP {resp.status_code} de Open Exchange Rates")
        if resp.status_code >= 400:
            raise RuntimeError(f"Open Exchange Rates: HTTP {resp.status_code}")
        quotes = ref.parse_oxr_latest(q.loads_exact(resp.text), collected_at=now)
        with session_scope(self.factory) as session:
            added = ref.upsert_reference_quotes(session, quotes, data_mode=self.settings.data_mode)
            self._check_reference_deviations(session, now)
        return added > 0

    async def _poll_fred(self, now: datetime) -> bool:
        if not self._fred_key:  # sem chave a fonte fica desligada: nada é consultado
            return False
        data = await macro.fred_observations(
            self.http(),
            self._fred_key,
            today=now.astimezone(q.BRT).date(),
            limiter=self._fred_limiter,
            clock=time.monotonic,
        )
        draft = macro.parse_fred_observations(data)
        with session_scope(self.factory) as session:
            return self._upsert_quotes(session, [draft], now)

    # ----------------------------------------------------------------- cripto
    async def _poll_binance_ticker(self, now: datetime) -> bool:
        symbols = json.dumps([sym for sym, _, _ in q.BINANCE_SYMBOLS], separators=(",", ":"))
        data = await self._get_json(f"{q.BINANCE_BASE}/api/v3/ticker/24hr", {"symbols": symbols})
        drafts = q.parse_ticker_24h(data)
        with session_scope(self.factory) as session:
            return self._upsert_quotes(session, drafts, now)

    async def _poll_binance_candles(self, now: datetime) -> bool:
        errors: list[str] = []
        changed = False
        for symbol, _label, instrument in q.BINANCE_SYMBOLS:
            try:
                k5 = await self._get_json(
                    f"{q.BINANCE_BASE}/api/v3/klines",
                    {"symbol": symbol, "interval": "5m", "limit": str(BINANCE_LIMIT_5M)},
                )
                k1 = await self._get_json(
                    f"{q.BINANCE_BASE}/api/v3/klines",
                    {"symbol": symbol, "interval": "1d", "limit": str(BINANCE_LIMIT_1D)},
                )
                c5 = q.parse_klines(k5, "5m", now=now)
                c1 = q.parse_klines(k1, "1d", now=now)
            except BlockedError:
                raise
            except Exception as exc:
                errors.append(f"{instrument}: {exc}"[:200])
                continue
            with session_scope(self.factory) as session:
                changed |= self._store_candles(session, instrument, "5m", c5, now)
                changed |= self._store_candles(session, instrument, "1d", c1, now)
                self._prune_candles(session, instrument, now)
                snap = self._snapshot(session, instrument, now)
                self._maybe_alert(session, snap, now)
        if errors and len(errors) == len(q.BINANCE_SYMBOLS):
            raise RuntimeError("; ".join(errors))
        return changed

    def _store_candles(
        self, session: Session, instrument: str, interval: str, candles: list[vol.Candle], now: datetime
    ) -> bool:
        if not candles:
            return False
        existing = set(
            session.scalars(
                select(MarketCandle.open_time).where(
                    MarketCandle.instrument == instrument,
                    MarketCandle.interval == interval,
                    MarketCandle.data_mode == self.settings.data_mode,
                    MarketCandle.open_time.in_([c.open_time for c in candles]),
                )
            )
        )
        added = 0
        for c in candles:
            if c.open_time in existing:
                continue
            session.add(
                MarketCandle(
                    instrument=instrument,
                    interval=interval,
                    open_time=c.open_time,
                    close_time=c.close_time,
                    open=c.open,
                    high=c.high,
                    low=c.low,
                    close=c.close,
                    captured_at=now,
                    data_mode=self.settings.data_mode,
                )
            )
            added += 1
        session.flush()
        return added > 0

    def _prune_candles(self, session: Session, instrument: str, now: datetime) -> None:
        for interval, days in (("5m", KEEP_5M_DAYS), ("1d", KEEP_1D_DAYS)):
            session.execute(
                delete(MarketCandle).where(
                    MarketCandle.instrument == instrument,
                    MarketCandle.interval == interval,
                    MarketCandle.open_time < now - timedelta(days=days),
                )
            )

    def _snapshot(self, session: Session, instrument: str, now: datetime) -> vol.VolatilitySnapshot:
        return vol.snapshot(instrument, *load_candles(session, instrument, self.settings.data_mode), now=now)

    def _maybe_alert(self, session: Session, snap: vol.VolatilitySnapshot, now: datetime) -> None:
        was = self._alert_state.get(snap.instrument, False)
        self._alert_state[snap.instrument] = snap.alert
        if not snap.alert or was:
            return  # só na transição para alerta: sem repetir a cada sondagem
        events_svc.append_event(
            session,
            EVENT_VOLATILITY_ALERT,
            volatility_payload(snap),
            data_mode=self.settings.data_mode,
            ts=now,
        )


def load_candles(session: Session, instrument: str, data_mode: str) -> tuple[list[vol.Candle], list[vol.Candle]]:
    """(velas de 5 min das últimas 24 h, velas diárias dos últimos 20 dias), em ordem cronológica."""

    def fetch(interval: str, limit: int) -> list[vol.Candle]:
        rows = session.scalars(
            select(MarketCandle)
            .where(
                MarketCandle.instrument == instrument,
                MarketCandle.interval == interval,
                MarketCandle.data_mode == data_mode,
            )
            .order_by(MarketCandle.open_time.desc())
            .limit(limit)
        ).all()
        return [vol.Candle(r.open_time, r.close_time, r.open, r.high, r.low, r.close) for r in reversed(rows)]

    return fetch("5m", vol.SHORT_5M_PER_DAY), fetch("1d", vol.LONG_DAYS)


def volatility_payload(snap: vol.VolatilitySnapshot) -> dict[str, Any]:
    """Forma pública de um estado de volatilidade (strings decimais, nada de float)."""

    def s(x: Decimal | None) -> str | None:
        return None if x is None else format(x.normalize() if x != 0 else Decimal(0), "f")

    return {
        "instrument": snap.instrument,
        "status": snap.status,
        "as_of": snap.as_of.isoformat() if snap.as_of else None,
        "last_close": s(snap.last_close),
        "last_move_pct": s(snap.last_move_pct),
        "ewma_pct_5m": s(snap.ewma_pct_5m),
        "parkinson_1d_pct": s(snap.parkinson_1d_pct),
        "parkinson_20d_pct": s(snap.parkinson_20d_pct),
        "ratio_1d_20d": s(snap.ratio_1d_20d),
        "atr_14_5m": s(snap.atr_14_5m),
        "regime": snap.regime,
        "alert": snap.alert,
        "reasons": list(snap.reasons),
    }
