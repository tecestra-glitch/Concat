"""Demo data: clearly labelled, deterministic, illustrative only (`data_mode="demo"` on every row).

Rates are plausible-looking placeholders, NOT market data. Seeded when DATA_MODE=demo, or when the
database is empty and FX_SEED_DEMO=1. Real queries never see these rows: every list endpoint filters
by the server's data_mode.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from ..adapters.base import Fee, QuoteDraft
from ..config import Settings
from ..db import session_scope
from ..models import Account, Branch, Evidence, JournalEntry, Quote, Source, utcnow
from . import events as events_svc
from .opportunities import opportunity_payload, recompute_opportunities
from .quotes import latest_quotes, quote_to_out, store_quote_draft

DEMO = "demo"
D = Decimal

SOURCES: list[dict[str, Any]] = [
    dict(
        id="chaco",
        name="Cambios Chaco (demo)",
        kind="exchange_house",
        method="html",
        url="https://www.cambioschaco.com.py/",
        capabilities=["branch_table", "buy_sell", "usd_pyg", "brl_pyg"],
        limitations=["sem API oficial", "cotação por filial requer navegador"],
        coverage_cities=["CDE", "ASU"],
        coverage_currencies=["USD", "BRL", "PYG"],
    ),
    dict(
        id="maxicambios",
        name="MaxiCambios (demo)",
        kind="exchange_house",
        method="html",
        url="https://www.maxicambios.com.py/",
        capabilities=["buy_sell", "usd_pyg", "brl_pyg"],
        limitations=["sem API oficial"],
        coverage_cities=["ASU", "CDE"],
        coverage_currencies=["USD", "BRL", "PYG"],
    ),
    dict(
        id="amambay-pjc",
        name="Casa de Câmbio PJC (demo)",
        kind="exchange_house",
        method="manual",
        url="",
        capabilities=["buy_sell", "usd_pyg", "brl_pyg", "usd_brl"],
        limitations=["cotação informada manualmente"],
        coverage_cities=["PJC"],
        coverage_currencies=["USD", "BRL", "PYG"],
    ),
    dict(
        id="wu",
        name="Western Union (demo)",
        kind="remittance",
        method="browser",
        url="https://www.westernunion.com/br/pt/",
        capabilities=["brl_pyg", "amount_dependent", "promo"],
        limitations=["cotação depende do valor e do meio de pagamento", "anti-bot: requer navegador"],
        coverage_cities=[],
        coverage_currencies=["BRL", "PYG", "USD"],
    ),
    dict(
        id="ueno",
        name="ueno bank (demo)",
        kind="bank",
        method="browser",
        url="https://www.ueno.com.py/",
        capabilities=["usd_pyg", "account", "card"],
        limitations=["requer sessão autenticada"],
        coverage_cities=[],
        coverage_currencies=["USD", "PYG"],
    ),
    dict(
        id="nomad",
        name="Nomad (demo)",
        kind="fintech",
        method="html",
        url="https://www.nomadglobal.com/",
        capabilities=["usd_brl", "account"],
        limitations=["spread varia por horário"],
        coverage_cities=[],
        coverage_currencies=["USD", "BRL"],
    ),
    dict(
        id="revolut",
        name="Revolut (demo)",
        kind="fintech",
        method="html",
        url="https://www.revolut.com/",
        capabilities=["usd_brl", "account"],
        limitations=["tarifa de fim de semana"],
        coverage_cities=[],
        coverage_currencies=["USD", "BRL"],
    ),
    dict(
        id="bcp",
        name="BCP – Banco Central del Paraguay (demo)",
        kind="central_bank",
        method="official_api",
        url="https://www.bcp.gov.py/",
        capabilities=["usd_pyg", "market_reference"],
        limitations=["referência diária, não executável"],
        coverage_cities=[],
        coverage_currencies=["USD", "PYG"],
    ),
]

BRANCHES: list[dict[str, Any]] = [
    dict(
        id="chaco-cde-centro",
        source_id="chaco",
        name="Chaco – CDE Centro (demo)",
        city="CDE",
        address="Av. San Blas, CDE",
    ),
    dict(
        id="chaco-asu-villa-morra", source_id="chaco", name="Chaco – Villa Morra (demo)", city="ASU", address="Asunción"
    ),
    dict(
        id="maxicambios-asu-shopping",
        source_id="maxicambios",
        name="MaxiCambios – Shopping (demo)",
        city="ASU",
        address=None,
    ),
    dict(id="maxicambios-cde-km4", source_id="maxicambios", name="MaxiCambios – Km 4 (demo)", city="CDE", address=None),
    dict(id="amambay-pjc-centro", source_id="amambay-pjc", name="Câmbio PJC – Centro (demo)", city="PJC", address=None),
]

# (source, branch, city, base, quote, buy, sell, modality, kind, channel, context, fees, amount_base)
QUOTE_SPECS: list[dict[str, Any]] = [
    dict(
        source_id="chaco",
        branch_id="chaco-cde-centro",
        city="CDE",
        base="USD",
        quote="PYG",
        buy=D("7290"),
        sell=D("7360"),
        modality="cash",
        kind="indicative",
        channel="physical",
    ),
    dict(
        source_id="chaco",
        branch_id="chaco-cde-centro",
        city="CDE",
        base="BRL",
        quote="PYG",
        buy=D("1360"),
        sell=D("1384"),
        modality="cash",
        kind="indicative",
        channel="physical",
    ),
    dict(
        source_id="chaco",
        branch_id="chaco-asu-villa-morra",
        city="ASU",
        base="USD",
        quote="PYG",
        buy=D("7300"),
        sell=D("7350"),
        modality="cash",
        kind="indicative",
        channel="physical",
    ),
    dict(
        source_id="chaco",
        branch_id="chaco-asu-villa-morra",
        city="ASU",
        base="BRL",
        quote="PYG",
        buy=D("1352"),
        sell=D("1390"),
        modality="cash",
        kind="indicative",
        channel="physical",
    ),
    dict(
        source_id="maxicambios",
        branch_id="maxicambios-asu-shopping",
        city="ASU",
        base="USD",
        quote="PYG",
        buy=D("7295"),
        sell=D("7345"),
        modality="cash",
        kind="indicative",
        channel="physical",
    ),
    dict(
        source_id="maxicambios",
        branch_id="maxicambios-cde-km4",
        city="CDE",
        base="USD",
        quote="PYG",
        buy=D("7285"),
        sell=D("7365"),
        modality="cash",
        kind="indicative",
        channel="physical",
    ),
    dict(
        source_id="maxicambios",
        branch_id="maxicambios-cde-km4",
        city="CDE",
        base="BRL",
        quote="PYG",
        buy=D("1358"),
        sell=D("1386"),
        modality="cash",
        kind="indicative",
        channel="physical",
    ),
    dict(
        source_id="amambay-pjc",
        branch_id="amambay-pjc-centro",
        city="PJC",
        base="USD",
        quote="PYG",
        buy=D("7280"),
        sell=D("7370"),
        modality="cash",
        kind="indicative",
        channel="physical",
    ),
    dict(
        source_id="amambay-pjc",
        branch_id="amambay-pjc-centro",
        city="PJC",
        base="BRL",
        quote="PYG",
        buy=D("1355"),
        sell=D("1388"),
        modality="cash",
        kind="indicative",
        channel="physical",
    ),
    dict(
        source_id="amambay-pjc",
        branch_id="amambay-pjc-centro",
        city="PJC",
        base="USD",
        quote="BRL",
        buy=D("5.33"),
        sell=D("5.42"),
        modality="cash",
        kind="indicative",
        channel="physical",
    ),
    # Western Union: BRL -> PYG into a ueno account, amount dependent, promo at 25k
    dict(
        source_id="wu",
        city=None,
        base="BRL",
        quote="PYG",
        buy=D("1366.5"),
        sell=None,
        modality="transfer",
        kind="executable",
        channel="digital",
        amount_base=D("5000"),
        context={"payment": "pix", "receive": "bank_account", "bank": "ueno", "promo": None},
        fees=[Fee("tarifa", D("9.90"), "BRL")],
    ),
    dict(
        source_id="wu",
        city=None,
        base="BRL",
        quote="PYG",
        buy=D("1371.2"),
        sell=None,
        modality="transfer",
        kind="executable",
        channel="digital",
        amount_base=D("10000"),
        context={"payment": "pix", "receive": "bank_account", "bank": "ueno", "promo": None},
        fees=[Fee("tarifa", D("9.90"), "BRL")],
    ),
    dict(
        source_id="wu",
        city=None,
        base="BRL",
        quote="PYG",
        buy=D("1389.4"),
        sell=None,
        modality="transfer",
        kind="executable",
        channel="digital",
        amount_base=D("25000"),
        context={"payment": "pix", "receive": "bank_account", "bank": "ueno", "promo": "fee_100_off"},
        fees=[Fee("tarifa", D("0"), "BRL")],
    ),
    dict(
        source_id="wu",
        city=None,
        base="BRL",
        quote="PYG",
        buy=D("1380.0"),
        sell=None,
        modality="transfer",
        kind="executable",
        channel="digital",
        amount_base=D("50000"),
        context={"payment": "pix", "receive": "bank_account", "bank": "ueno", "promo": None},
        fees=[Fee("tarifa", D("0"), "BRL")],
    ),
    # ueno: USD/PYG account conversion
    dict(
        source_id="ueno",
        city=None,
        base="USD",
        quote="PYG",
        buy=D("7270"),
        sell=D("7395"),
        modality="account",
        kind="indicative",
        channel="digital",
        context={"product": "conta"},
    ),
    # Nomad / Revolut: USD/BRL account
    dict(
        source_id="nomad",
        city=None,
        base="USD",
        quote="BRL",
        buy=D("5.372"),
        sell=D("5.418"),
        modality="account",
        kind="indicative",
        channel="digital",
        context={"payment": "pix"},
        fees=[Fee("spread", D("0"), "BRL")],
    ),
    dict(
        source_id="revolut",
        city=None,
        base="USD",
        quote="BRL",
        buy=D("5.381"),
        sell=D("5.409"),
        modality="account",
        kind="indicative",
        channel="digital",
        context={"plan": "standard"},
        fees=[Fee("tarifa fim de semana", None, "BRL")],
    ),
    # BCP reference
    dict(
        source_id="bcp",
        city=None,
        base="USD",
        quote="PYG",
        buy=D("7325"),
        sell=D("7325"),
        modality="transfer",
        kind="market_reference",
        channel="digital",
    ),
]

ACCOUNTS: list[dict[str, Any]] = [
    dict(
        institution="ueno",
        label="ueno conta PYG (demo)",
        currency="PYG",
        kind="bank",
        location="digital",
        balance_free=D("2500000"),
        balance_reserved=D("0"),
        balance_in_transit=D("0"),
    ),
    dict(
        institution="ueno",
        label="ueno conta USD (demo)",
        currency="USD",
        kind="bank",
        location="digital",
        balance_free=D("320"),
        balance_reserved=D("0"),
        balance_in_transit=D("0"),
    ),
    dict(
        institution="ueno",
        label="ueno cartão de crédito (demo)",
        currency="PYG",
        kind="card_credit",
        location="digital",
        balance_free=D("0"),
        balance_reserved=D("0"),
        balance_in_transit=D("0"),
    ),
    dict(
        institution="nomad",
        label="Nomad USD (demo)",
        currency="USD",
        kind="fintech",
        location="digital",
        balance_free=D("1200"),
        balance_reserved=D("0"),
        balance_in_transit=D("150"),
    ),
    dict(
        institution="revolut",
        label="Revolut USD (demo)",
        currency="USD",
        kind="fintech",
        location="digital",
        balance_free=D("480.5"),
        balance_reserved=D("0"),
        balance_in_transit=D("0"),
    ),
    dict(
        institution="carteira",
        label="Dinheiro USD em CDE (demo)",
        currency="USD",
        kind="cash",
        location="CDE",
        balance_free=D("200"),
        balance_reserved=D("0"),
        balance_in_transit=D("0"),
    ),
]

# Demo ids are prefixed so they can never collide with real sources/branches in the same database.
DEMO_PREFIX = "demo-"
for _s in SOURCES:
    _s["id"] = DEMO_PREFIX + _s["id"]
for _b in BRANCHES:
    _b["id"] = DEMO_PREFIX + _b["id"]
    _b["source_id"] = DEMO_PREFIX + _b["source_id"]
for _q in QUOTE_SPECS:
    _q["source_id"] = DEMO_PREFIX + _q["source_id"]
    if _q.get("branch_id"):
        _q["branch_id"] = DEMO_PREFIX + _q["branch_id"]

# deterministic wobble in basis points applied to the mid every 5 minutes
WOBBLE_BP = (0, 3, -2, 5, 1, -4, 2, 6, -1, -3, 4, 0, -5, 2, 3, -2, 1, 4, -6, 0, 2, -1, 3, -2)


def demo_present(session: Session) -> bool:
    return bool(session.scalar(select(func.count(Source.id)).where(Source.data_mode == DEMO)))


def db_empty(session: Session) -> bool:
    return not session.scalar(select(func.count(Source.id)))


def _wobble(value: Decimal, i: int, salt: str) -> Decimal:
    offset = int(hashlib.sha256(salt.encode()).hexdigest(), 16) % len(WOBBLE_BP)
    bp = WOBBLE_BP[(i + offset) % len(WOBBLE_BP)]
    return value * (D(10000) + D(bp)) / D(10000)


def seed_demo(session: Session, *, now: datetime | None = None, history_hours: int = 2) -> dict[str, int]:
    now = now or utcnow()
    counts = {"sources": 0, "branches": 0, "quotes": 0, "accounts": 0, "evidence": 0, "events": 0, "opportunities": 0}
    if demo_present(session):
        return counts

    for spec in SOURCES:
        session.add(
            Source(
                **spec,
                health="ok",
                last_success_at=now,
                poll_interval_s=300,
                data_mode=DEMO,
                next_poll_at=now + timedelta(seconds=300),
                updated_at=now,
            )
        )
        counts["sources"] += 1
    for spec in BRANCHES:
        session.add(Branch(**spec, data_mode=DEMO))
        counts["branches"] += 1
    session.flush()

    evidence_ids: dict[str, str] = {}
    for spec in SOURCES:
        ev = Evidence(
            source_id=spec["id"],
            kind="manual",
            url=spec["url"] or "demo://seed",
            captured_at=now,
            sha256=hashlib.sha256(f"demo:{spec['id']}".encode()).hexdigest(),
            excerpt=f"DEMO – dados ilustrativos gerados pelo seed para {spec['name']}. Não são cotações reais.",
            rules=["demo seed v1"],
            data_mode=DEMO,
        )
        session.add(ev)
        session.flush()
        evidence_ids[spec["id"]] = ev.id
        counts["evidence"] += 1

    steps = history_hours * 12
    for spec in QUOTE_SPECS:
        salt = f"{spec['source_id']}:{spec.get('branch_id')}:{spec['base']}{spec['quote']}:{spec.get('amount_base')}"
        for i in range(steps + 1):
            ts = now - timedelta(minutes=5 * (steps - i))
            buy = _wobble(spec["buy"], i, salt) if spec.get("buy") is not None else None
            sell = _wobble(spec["sell"], i, salt + "s") if spec.get("sell") is not None else None
            if spec["kind"] == "market_reference":
                buy = sell = spec["buy"]  # reference stays flat (one declared value)
            draft = QuoteDraft(
                source_id=spec["source_id"],
                base=spec["base"],
                quote=spec["quote"],
                buy=buy,
                sell=sell,
                unit_note=f"{spec['quote']} por 1 {spec['base']}",
                modality=spec["modality"],
                kind=spec["kind"],
                channel=spec["channel"],
                city=spec.get("city"),
                branch_id=spec.get("branch_id"),
                amount_base=spec.get("amount_base"),
                context=spec.get("context"),
                fees=list(spec.get("fees", [])),
                declared_updated_at=ts if spec["kind"] != "market_reference" else now - timedelta(hours=history_hours),
            )
            store_quote_draft(
                session, draft, evidence_id=evidence_ids[spec["source_id"]], data_mode=DEMO, captured_at=ts
            )
            counts["quotes"] += 1

    for spec in ACCOUNTS:
        session.add(Account(**spec, updated_at=now, data_mode=DEMO))
        counts["accounts"] += 1
    session.add(
        JournalEntry(
            ts=now,
            kind="note",
            data_mode=DEMO,
            text="DEMO – diário de exemplo. Saldos e cotações deste modo são ilustrativos.",
            amounts=[{"label": "exemplo", "amount": "0", "currency": "BRL"}],
            account_ids=[],
        )
    )
    session.flush()

    rows = recompute_opportunities(session, data_mode=DEMO, now=now)
    counts["opportunities"] = len(rows)

    for q in latest_quotes(session, data_mode=DEMO, lookback_s=None):
        events_svc.append_event(
            session, "quote.updated", quote_to_out(q).model_dump(mode="json"), data_mode=DEMO, ts=now
        )
        counts["events"] += 1
    for spec in SOURCES:
        events_svc.append_event(
            session,
            "source.health",
            {"source_id": spec["id"], "health": "ok", "last_error": None, "consecutive_failures": 0},
            data_mode=DEMO,
            ts=now,
        )
        counts["events"] += 1
    events_svc.append_event(session, "opportunity.updated", opportunity_payload(rows), data_mode=DEMO, ts=now)
    counts["events"] += 1
    session.flush()
    return counts


def ensure_demo_seeded(session_factory: sessionmaker[Session], settings: Settings) -> dict[str, int] | None:
    """Seed when DATA_MODE=demo, or when FX_SEED_DEMO=1 and the database is empty."""
    with session_scope(session_factory) as session:
        if settings.data_mode == DEMO or (settings.seed_demo and db_empty(session)):
            if not demo_present(session):
                return seed_demo(session)
    return None


def demo_quote_count(session: Session) -> int:
    return int(session.scalar(select(func.count(Quote.id)).where(Quote.data_mode == DEMO)) or 0)
