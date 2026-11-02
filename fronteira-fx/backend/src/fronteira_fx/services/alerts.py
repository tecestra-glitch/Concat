"""Alert rules evaluation and delivery (module `notify`). Secrets only via environment (Settings)."""

from __future__ import annotations

import asyncio
import logging
import smtplib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from email.message import EmailMessage
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..config import Settings
from ..db import session_scope
from ..decimal_utils import fmt
from ..models import AlertEvent, AlertRule, Change, Opportunity, utcnow
from ..schemas import AlertEventOut
from . import events as events_svc

log = logging.getLogger("fronteira_fx.alerts")
DOWN_STATUSES = {"blocked", "error", "needs_session"}


@dataclass(slots=True)
class AlertContext:
    now: datetime
    source_id: str | None = None
    health: str | None = None
    previous_health: str | None = None
    changes: list[Change] = field(default_factory=list)
    opportunities: list[Opportunity] = field(default_factory=list)
    new_opportunity_ids: set[str] = field(default_factory=set)


def _in_cooldown(rule: AlertRule, now: datetime) -> bool:
    return rule.last_fired_at is not None and now < rule.last_fired_at + timedelta(seconds=rule.cooldown_s or 0)


def _pct(value: Decimal) -> str:
    return f"{fmt(value * 100, 3)}%"


def _match_cycle_roi(rule: AlertRule, ctx: AlertContext) -> tuple[str, dict[str, Any]] | None:
    params = rule.params or {}
    best: Opportunity | None = None
    for o in ctx.opportunities:
        if o.kind != "cycle" or not o.in_main_ranking or o.confidence == "incomplete":
            continue
        if params.get("capital") is not None and o.capital_brl != Decimal(str(params["capital"])):
            continue
        if params.get("channel") and o.channel != params["channel"]:
            continue
        if best is None or o.roi > best.roi:
            best = o
    if best is None or rule.threshold is None or best.roi < rule.threshold:
        return None
    msg = f"Ciclo acima de {_pct(rule.threshold)}: {best.title} — roi {_pct(best.roi)} com {fmt(best.capital_brl)} BRL"
    return msg, {
        "opportunity_id": best.id,
        "roi": fmt(best.roi),
        "capital_brl": fmt(best.capital_brl),
        "title": best.title,
    }


DIGITAL_CITY = "digital"  # rule param for «Digital (sem cidade)»: only quotes without a city (Q-04)


def _is_reference(snapshot: dict[str, Any]) -> bool:
    """Third-party reference numbers (dolarPy) are comparison only: never an alert on a price move."""
    return snapshot.get("modality") == "reference" or snapshot.get("channel") == "aggregator"


def _change_matches(ch: Change, *, pair: str | None, city: str | None) -> bool:
    """Compare the rule against the structured `pair`/`city` recorded in `Change.after` (B18). Rows written
    before those fields existed fall back to the label prefix of the summary. `city="digital"` matches only
    quotes without a city; no city matches any city."""
    after = ch.after or {}
    if _is_reference(after):
        return False
    if "pair" in after:
        if pair and after.get("pair") != pair:
            return False
        if city == DIGITAL_CITY:
            return after.get("city") is None
        return not city or after.get("city") == city
    head = ch.summary.split(":")[0]
    if pair and not head.startswith(pair):
        return False
    if city == DIGITAL_CITY:
        return not any(f" {c}" in head for c in ("CDE", "ASU", "PJC"))
    return not city or f" {city}" in head


def _match_quote_move(rule: AlertRule, ctx: AlertContext) -> tuple[str, dict[str, Any]] | None:
    params = rule.params or {}
    pair = params.get("pair")
    city = params.get("city")
    for ch in ctx.changes:
        if ch.kind != "quote_change" or not ch.before:
            continue
        if not _change_matches(ch, pair=pair, city=city):
            continue
        for side in ("sell", "buy"):
            b, a = ch.before.get(side), ch.after.get(side)
            if b and a and Decimal(b) > 0:
                move = abs(Decimal(a) - Decimal(b)) / Decimal(b)
                if rule.threshold is not None and move >= rule.threshold:
                    return (
                        f"Movimento {_pct(move)} em {ch.summary}",
                        {"change_id": ch.id, "move": fmt(move), "side": side, "source_id": ch.source_id},
                    )
    return None


def _match_source_down(rule: AlertRule, ctx: AlertContext) -> tuple[str, dict[str, Any]] | None:
    params = rule.params or {}
    if ctx.source_id is None or ctx.health not in DOWN_STATUSES:
        return None
    if params.get("source") and params["source"] != ctx.source_id:
        return None
    if ctx.previous_health == ctx.health:
        return None  # already down; cooldown + status change handle repeats
    return f"Fonte {ctx.source_id} indisponível: {ctx.health}", {"source_id": ctx.source_id, "health": ctx.health}


def _match_opportunity_new(rule: AlertRule, ctx: AlertContext) -> tuple[str, dict[str, Any]] | None:
    fresh = [o for o in ctx.opportunities if o.id in ctx.new_opportunity_ids and o.in_main_ranking]
    if rule.threshold is not None:
        fresh = [o for o in fresh if o.roi >= rule.threshold]
    if not fresh:
        return None
    fresh.sort(key=lambda o: -o.roi)
    o = fresh[0]
    return (
        f"Nova oportunidade no ranking principal: {o.title} (roi {_pct(o.roi)})",
        {"opportunity_id": o.id, "roi": fmt(o.roi), "count": len(fresh)},
    )


MATCHERS = {
    "cycle_roi": _match_cycle_roi,
    "quote_move": _match_quote_move,
    "source_down": _match_source_down,
    "opportunity_new": _match_opportunity_new,
}


def evaluate_rules(session: Session, ctx: AlertContext, *, data_mode: str) -> list[AlertEvent]:
    """Create (undelivered) AlertEvents for every enabled rule that matches and is out of cooldown."""
    rules = list(
        session.scalars(select(AlertRule).where(AlertRule.enabled.is_(True), AlertRule.data_mode == data_mode))
    )
    created: list[AlertEvent] = []
    for rule in rules:
        matcher = MATCHERS.get(rule.kind)
        if matcher is None or _in_cooldown(rule, ctx.now):
            continue
        hit = matcher(rule, ctx)
        if hit is None:
            continue
        message, payload = hit
        ev = AlertEvent(
            rule_id=rule.id,
            ts=ctx.now,
            message=message,
            payload=payload,
            channel=rule.channel,
            delivered=False,
            data_mode=data_mode,
        )
        session.add(ev)
        rule.last_fired_at = ctx.now
        created.append(ev)
    session.flush()
    return created


def event_to_out(ev: AlertEvent) -> AlertEventOut:
    return AlertEventOut.model_validate(ev)


async def _send(
    rule_channel: str, target: str | None, message: str, payload: dict[str, Any], settings: Settings
) -> None:
    if rule_channel == "ui":
        return
    if rule_channel == "webhook":
        if not target:
            raise ValueError("webhook sem URL de destino")
        async with httpx.AsyncClient(timeout=settings.alert_http_timeout_s) as client:
            r = await client.post(target, json={"message": message, "payload": payload})
            r.raise_for_status()
        return
    if rule_channel == "telegram":
        if not settings.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN não configurado")
        if not target:
            raise ValueError("telegram sem chat_id")
        async with httpx.AsyncClient(timeout=settings.alert_http_timeout_s) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                json={"chat_id": target, "text": message},
            )
            r.raise_for_status()
        return
    if rule_channel == "email":
        if not settings.smtp_host:
            raise ValueError("SMTP_HOST não configurado")
        if not target:
            raise ValueError("email sem destinatário")

        def send_mail() -> None:
            msg = EmailMessage()
            msg["Subject"] = f"[Fronteira FX] {message[:80]}"
            msg["From"] = settings.smtp_from or settings.smtp_user or "fronteira-fx@localhost"
            msg["To"] = target
            msg.set_content(message)
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.alert_http_timeout_s) as smtp:
                if settings.smtp_starttls:
                    smtp.starttls()
                if settings.smtp_user:
                    smtp.login(settings.smtp_user, settings.smtp_password or "")
                smtp.send_message(msg)

        await asyncio.to_thread(send_mail)
        return
    raise ValueError(f"canal desconhecido: {rule_channel}")


async def deliver_events(session_factory: sessionmaker[Session], event_ids: list[str], settings: Settings) -> None:
    """Deliver pending events, record delivered/error, emit `alert.fired` on the stream."""
    for event_id in event_ids:
        with session_scope(session_factory) as session:
            ev = session.get(AlertEvent, event_id)
            if ev is None:
                continue
            rule = session.get(AlertRule, ev.rule_id)
            channel, target, message, payload = (
                ev.channel,
                rule.target if rule else None,
                ev.message,
                dict(ev.payload or {}),
            )
            data_mode = ev.data_mode
        error: str | None = None
        try:
            await _send(channel, target, message, payload, settings)
        except Exception as exc:  # delivery failures are recorded, never raised
            error = f"{type(exc).__name__}: {exc}"
            log.warning("alert delivery failed (%s): %s", channel, error)
        with session_scope(session_factory) as session:
            ev = session.get(AlertEvent, event_id)
            if ev is None:
                continue
            ev.delivered = error is None
            ev.error = error
            session.flush()
            events_svc.append_event(
                session, "alert.fired", event_to_out(ev).model_dump(mode="json"), data_mode=data_mode, ts=utcnow()
            )


async def fire_test(
    session_factory: sessionmaker[Session], rule_id: str, settings: Settings, *, data_mode: str
) -> AlertEvent | None:
    with session_scope(session_factory) as session:
        rule = session.get(AlertRule, rule_id)
        if rule is None or rule.data_mode != data_mode:
            return None
        ev = AlertEvent(
            rule_id=rule.id,
            ts=utcnow(),
            message=f"[teste] regra '{rule.name}' ({rule.kind}) — Fronteira FX",
            payload={"test": True},
            channel=rule.channel,
            delivered=False,
            data_mode=data_mode,
        )
        session.add(ev)
        session.flush()
        event_id = ev.id
    await deliver_events(session_factory, [event_id], settings)
    with session_scope(session_factory) as session:
        ev = session.get(AlertEvent, event_id)
        session.expunge(ev)
        return ev
