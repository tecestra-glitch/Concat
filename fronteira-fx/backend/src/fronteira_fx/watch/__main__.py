"""Standalone runner: `uv run python -m fronteira_fx.watch [--db URL] [--concurrency N] [--once] [--source ID ...]`."""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
from typing import Any

from .runner import run_forever
from .service import WatchService
from .store import InMemoryWatchStore
from .store_sql import SqlWatchStore

log = logging.getLogger("fronteira_fx.watch.main")


def _log_emit(type_: str, payload: dict[str, Any]) -> None:
    log.info("event %s: %s", type_, payload.get("summary") or payload)


def build_service(db_url: str | None) -> WatchService:
    store = SqlWatchStore.from_url(db_url) if db_url else InMemoryWatchStore()
    return WatchService(store=store, emit=_log_emit)


async def _run_once(service: WatchService, only: list[str]) -> int:
    service.register_sources()
    ids = only or sorted(service.adapters())
    failures = 0
    for source_id in ids:
        outcome = await service.poll(source_id)
        status = outcome.status
        print(f"{source_id:14} {status.status:14} hash={str(status.content_hash)[:12]} changes={len(outcome.changes)}"
              f"{'  ' + status.last_error if status.last_error else ''}")
        for change in outcome.changes:
            print(f"    - [{change.kind}] {change.summary}")
        failures += status.status in ("error", "blocked", "needs_session")
    return 1 if failures and failures == len(ids) else 0


async def _run_forever(service: WatchService, concurrency: int, only: list[str]) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):  # pragma: no cover - non-POSIX
            pass
    if only:
        service.register_sources()
        for source_id in list(service.adapters()):
            if source_id not in only:
                service.scheduler.override(source_id, enabled=False)
    await run_forever(service, concurrency=concurrency, stop=stop)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m fronteira_fx.watch", description=__doc__)
    parser.add_argument("--db", default=os.environ.get("WATCH_DATABASE_URL") or os.environ.get("DATABASE_URL"),
                        help="SQLAlchemy URL for watch_status/watch_changes (default: env, else in-memory)")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--once", action="store_true", help="poll every source once, print, exit")
    parser.add_argument("--source", action="append", default=[], help="restrict to these source ids")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    service = build_service(args.db)
    if args.once:
        return asyncio.run(_run_once(service, args.source))
    asyncio.run(_run_forever(service, args.concurrency, args.source))
    return 0


if __name__ == "__main__":
    sys.exit(main())
