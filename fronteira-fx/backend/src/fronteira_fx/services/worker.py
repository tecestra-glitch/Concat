"""Worker entrypoint: `python -m fronteira_fx.services.worker` (or `fronteira-fx-worker`).

Loop: run all due adapters (per-source backoff), process queued on-demand tasks, prune the event
stream, sleep one tick. Browser adapters run here (Playwright is installed in the worker image).
"""

from __future__ import annotations

import asyncio
import logging
import signal

from ..config import Settings, get_settings
from ..db import create_schema, make_engine, make_session_factory
from ..market.binance_ws import BinanceStream
from ..market.service import MarketPoller
from .collector import Collector
from .demo import ensure_demo_seeded

log = logging.getLogger("fronteira_fx.worker")


async def run_loop(settings: Settings | None = None, *, iterations: int | None = None) -> None:
    settings = settings or get_settings()
    engine = make_engine(settings.database_url)
    if settings.auto_create_schema:
        create_schema(engine)
    session_factory = make_session_factory(engine)
    ensure_demo_seeded(session_factory, settings)
    collector = Collector(session_factory, settings, inline_browser=True)
    collector.ensure_sources()
    market = MarketPoller(session_factory, settings)  # módulo market: piso de 60 s por fonte, só em real
    # stream da Binance (websocket): só com FX_BINANCE_WS=1; roda como tarefa e para junto com o worker
    binance = BinanceStream(session_factory, settings) if settings.binance_ws else None

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):  # pragma: no cover - platform dependent
            pass

    binance_task = asyncio.create_task(binance.run(stop)) if binance is not None else None
    n = 0
    while not stop.is_set():
        try:
            outcomes = await collector.run_once()
            processed = await collector.process_tasks()
            pruned = collector.prune_events()
            market_results = await market.run_once()
            if market_results:
                log.info("market: %d polled, %d failed", len(market_results), sum(not r.ok for r in market_results))
            log.info(
                "tick: %d sources (%d skipped), %d tasks, %d events pruned",
                len(outcomes),
                sum(1 for o in outcomes if o.skipped),
                processed,
                pruned,
            )
        except Exception:  # keep the loop alive
            log.exception("worker tick failed")
        n += 1
        if iterations is not None and n >= iterations:
            break
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.worker_tick_s)
        except TimeoutError:
            pass
    stop.set()
    if binance_task is not None:
        await binance_task
    await market.aclose()
    engine.dispose()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(run_loop())


if __name__ == "__main__":
    main()
