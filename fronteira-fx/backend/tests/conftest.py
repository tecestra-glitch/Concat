"""Shared fixtures: in-memory SQLite app in `real` mode, plus helpers to seed quotes."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from fronteira_fx.adapters.base import Fee, QuoteDraft
from fronteira_fx.config import Settings
from fronteira_fx.main import create_app
from fronteira_fx.models import Branch, Source
from fronteira_fx.services.collector import Collector
from fronteira_fx.services.opportunities import recompute_opportunities
from fronteira_fx.services.quotes import store_quote_draft

D = Decimal
NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


def make_settings(**overrides) -> Settings:
    base = dict(
        database_url="sqlite://",
        auto_create_schema=True,
        data_mode="real",
        seed_demo=False,
        api_key=None,
        stream_max_duration_s=1.0,
        stream_heartbeat_s=0.2,
        stream_poll_s=0.02,
        event_retention=1000,
        event_retention_s=86400,
        quotes_lookback_s=10 * 365 * 86400,
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def app(settings: Settings):
    application = create_app(settings)
    # tests never talk to real providers: empty adapter registry
    application.state.collector = Collector(application.state.session_factory, settings, adapters={})
    return application


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def session_factory(app, client) -> sessionmaker[Session]:
    return app.state.session_factory


@pytest.fixture
def db(session_factory) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
        session.commit()
    finally:
        session.close()


def add_source(
    session: Session,
    source_id: str,
    *,
    data_mode: str = "real",
    method: str = "html",
    kind: str = "exchange_house",
    cities: list[str] | None = None,
    branches: list[tuple[str, str]] = (),
) -> Source:
    src = Source(
        id=source_id,
        name=source_id.title(),
        kind=kind,
        method=method,
        url=f"https://{source_id}.example",
        health="ok",
        capabilities=["buy_sell"],
        limitations=[],
        coverage_cities=cities or [],
        coverage_currencies=["USD", "BRL", "PYG"],
        poll_interval_s=300,
        data_mode=data_mode,
    )
    session.add(src)
    for bid, city in branches:
        session.add(Branch(id=bid, source_id=source_id, name=bid, city=city, data_mode=data_mode))
    session.flush()
    return src


def draft(
    source_id: str,
    base: str,
    quote: str,
    buy,
    sell,
    *,
    modality="cash",
    kind="indicative",
    channel="physical",
    city=None,
    branch_id=None,
    amount_base=None,
    context=None,
    fees=(),
    declared=None,
) -> QuoteDraft:
    return QuoteDraft(
        source_id=source_id,
        base=base,
        quote=quote,
        buy=D(str(buy)) if buy is not None else None,
        sell=D(str(sell)) if sell is not None else None,
        unit_note=f"{quote} por 1 {base}",
        modality=modality,
        kind=kind,
        channel=channel,
        city=city,
        branch_id=branch_id,
        amount_base=D(str(amount_base)) if amount_base is not None else None,
        context=context,
        fees=[Fee(*f) if isinstance(f, tuple) else f for f in fees],
        declared_updated_at=declared,
    )


def seed_market(session: Session, *, data_mode: str = "real", now: datetime = NOW) -> None:
    """A small but complete market: WU digital BRL->PYG (amount dependent), ueno USD/PYG, nomad USD/BRL,
    chaco CDE cash, plus a BCP reference. Designed so a digital cycle has a tiny positive gain."""
    add_source(session, "wu", data_mode=data_mode, method="browser", kind="remittance")
    add_source(session, "ueno", data_mode=data_mode, method="browser", kind="bank")
    add_source(session, "nomad", data_mode=data_mode, method="html", kind="fintech")
    add_source(
        session,
        "chaco",
        data_mode=data_mode,
        cities=["CDE", "ASU"],
        branches=[("chaco-cde-centro", "CDE"), ("chaco-asu-centro", "ASU")],
    )
    add_source(session, "bcp", data_mode=data_mode, method="official_api", kind="central_bank")
    ctx = {"payment": "pix", "receive": "bank_account", "bank": "ueno"}
    drafts = [
        draft(
            "wu",
            "BRL",
            "PYG",
            "1366.5",
            None,
            modality="transfer",
            kind="executable",
            channel="digital",
            amount_base=5000,
            context=ctx,
            fees=[("tarifa", D("9.90"), "BRL")],
        ),
        draft(
            "wu",
            "BRL",
            "PYG",
            "1371.2",
            None,
            modality="transfer",
            kind="executable",
            channel="digital",
            amount_base=10000,
            context=ctx,
            fees=[("tarifa", D("9.90"), "BRL")],
        ),
        draft(
            "wu",
            "BRL",
            "PYG",
            "1389.4",
            None,
            modality="transfer",
            kind="executable",
            channel="digital",
            amount_base=25000,
            context={**ctx, "promo": "fee_100_off"},
            fees=[("tarifa", D("0"), "BRL")],
        ),
        draft(
            "wu",
            "BRL",
            "PYG",
            "1380",
            None,
            modality="transfer",
            kind="executable",
            channel="digital",
            amount_base=50000,
            context=ctx,
            fees=[("tarifa", D("0"), "BRL")],
        ),
        draft("ueno", "USD", "PYG", "7270", "7395", modality="account", channel="digital"),
        draft("nomad", "USD", "BRL", "5.372", "5.418", modality="account", channel="digital"),
        draft("chaco", "USD", "PYG", "7290", "7360", city="CDE", branch_id="chaco-cde-centro"),
        draft("chaco", "BRL", "PYG", "1360", "1384", city="CDE", branch_id="chaco-cde-centro"),
        draft("chaco", "USD", "PYG", "7300", "7350", city="ASU", branch_id="chaco-asu-centro"),
        draft("bcp", "USD", "PYG", "7325", "7325", modality="transfer", kind="market_reference", channel="digital"),
    ]
    for i, d in enumerate(drafts):
        store_quote_draft(session, d, evidence_id=None, data_mode=data_mode, captured_at=now - timedelta(seconds=i))
    recompute_opportunities(session, data_mode=data_mode, now=now)
    session.commit()
