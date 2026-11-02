"""Persistência de regras e histórico de disparos.

Duas implementações do protocolo `AlertStore`:
- `InMemoryAlertStore`: testes e desenvolvimento sem banco (tudo some ao reiniciar);
- `SqlAlchemyAlertStore`: tabelas `notify_alert_rules` e `notify_alert_events`, no metadata próprio `NotifyBase`.

`NotifyBase` é isolado de `models.py` de propósito, e os nomes levam o prefixo `notify_` para nunca colidir com
`alert_rules`/`alert_events` do core (B11). O core deve incluir `NotifyBase.metadata` no Alembic
(migração própria do módulo notify). Até lá, `create_notify_tables(engine)` cria as tabelas.
Os limiares são guardados como texto para preservar o `Decimal` exato (SQLite não tem Decimal).
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

from sqlalchemy import JSON, Boolean, DateTime, Index, Integer, String, Text, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from .rules import AlertEvent, AlertRule, AlertRuleIn


class AlertStore(Protocol):
    def list_rules(self, *, enabled_only: bool = False) -> list[AlertRule]: ...

    def get_rule(self, rule_id: str) -> AlertRule | None: ...

    def create_rule(self, data: AlertRuleIn) -> AlertRule: ...

    def update_rule(self, rule: AlertRule) -> AlertRule | None:
        """Substitui a regra com o mesmo id. Devolve None se não existir."""
        ...

    def delete_rule(self, rule_id: str) -> bool: ...

    def add_event(self, event: AlertEvent, *, dedupe_key: str | None = None) -> None: ...

    def list_events(
        self, *, rule_id: str | None = None, since: datetime | None = None, limit: int = 200
    ) -> list[AlertEvent]:
        """Mais recentes primeiro."""
        ...

    def last_fired(self) -> dict[tuple[str, str], datetime]:
        """Último disparo por (rule_id, dedupe_key). Usado para restaurar o cooldown após reinício."""
        ...


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class InMemoryAlertStore:
    """Store em memória, thread-safe. Retorna cópias para o chamador não mexer no estado."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._rules: dict[str, AlertRule] = {}
        self._events: list[tuple[AlertEvent, str | None]] = []

    def list_rules(self, *, enabled_only: bool = False) -> list[AlertRule]:
        with self._lock:
            rules = [r.model_copy() for r in self._rules.values()]
        return [r for r in rules if r.enabled] if enabled_only else rules

    def get_rule(self, rule_id: str) -> AlertRule | None:
        with self._lock:
            rule = self._rules.get(rule_id)
            return rule.model_copy() if rule is not None else None

    def create_rule(self, data: AlertRuleIn) -> AlertRule:
        rule = AlertRule(id=str(uuid.uuid4()), **data.model_dump())
        with self._lock:
            self._rules[rule.id] = rule
        return rule.model_copy()

    def update_rule(self, rule: AlertRule) -> AlertRule | None:
        with self._lock:
            if rule.id not in self._rules:
                return None
            self._rules[rule.id] = rule.model_copy()
        return rule.model_copy()

    def delete_rule(self, rule_id: str) -> bool:
        with self._lock:
            return self._rules.pop(rule_id, None) is not None

    def add_event(self, event: AlertEvent, *, dedupe_key: str | None = None) -> None:
        with self._lock:
            self._events.append((event.model_copy(), dedupe_key))

    def list_events(
        self, *, rule_id: str | None = None, since: datetime | None = None, limit: int = 200
    ) -> list[AlertEvent]:
        floor = _utc(since) if since is not None else None
        out: list[AlertEvent] = []
        with self._lock:
            for event, _key in reversed(self._events):
                if rule_id is not None and event.rule_id != rule_id:
                    continue
                if floor is not None and _utc(event.ts) < floor:
                    continue
                out.append(event.model_copy())
                if len(out) >= limit:
                    break
        return out

    def last_fired(self) -> dict[tuple[str, str], datetime]:
        latest: dict[tuple[str, str], datetime] = {}
        with self._lock:
            for event, key in self._events:
                if key is None:
                    continue
                slot = (event.rule_id, key)
                ts = _utc(event.ts)
                if slot not in latest or ts > latest[slot]:
                    latest[slot] = ts
        return latest


class NotifyBase(DeclarativeBase):
    """Base declarativa isolada do módulo notify (metadata próprio, separado de `models.py`)."""


class AlertRuleRow(NotifyBase):
    __tablename__ = "notify_alert_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    threshold: Mapped[str] = mapped_column(String(64), nullable=False)
    params: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    target: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cooldown_s: Mapped[int] = mapped_column(Integer, nullable=False, default=600)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AlertEventRow(NotifyBase):
    __tablename__ = "notify_alert_events"
    __table_args__ = (Index("ix_notify_alert_events_rule_dedupe", "rule_id", "dedupe_key"),)

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    rule_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    delivered: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(300), nullable=True)


def create_notify_tables(engine: Engine) -> None:
    """Cria as tabelas do módulo (útil em dev e testes; em produção use a migração do Alembic)."""
    NotifyBase.metadata.create_all(engine, checkfirst=True)


def _rule_from_row(row: AlertRuleRow) -> AlertRule:
    return AlertRule(
        id=row.id,
        name=row.name,
        kind=row.kind,
        threshold=Decimal(row.threshold),
        params=dict(row.params) if row.params is not None else None,
        channel=row.channel,
        target=row.target,
        cooldown_s=row.cooldown_s,
        enabled=row.enabled,
    )


def _apply_rule(row: AlertRuleRow, rule: AlertRule) -> None:
    row.name = rule.name
    row.kind = rule.kind
    row.threshold = str(rule.threshold)
    row.params = dict(rule.params) if rule.params is not None else None
    row.channel = rule.channel
    row.target = rule.target
    row.cooldown_s = rule.cooldown_s
    row.enabled = rule.enabled


def _event_from_row(row: AlertEventRow) -> AlertEvent:
    return AlertEvent(
        id=row.id,
        rule_id=row.rule_id,
        ts=_utc(row.ts),
        message=row.message,
        payload=dict(row.payload or {}),
        channel=row.channel,
        delivered=row.delivered,
        error=row.error,
    )


class SqlAlchemyAlertStore:
    """Store SQLAlchemy síncrono. Cada operação abre e fecha sua própria sessão."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session = session_factory

    def list_rules(self, *, enabled_only: bool = False) -> list[AlertRule]:
        stmt = select(AlertRuleRow).order_by(AlertRuleRow.created_at, AlertRuleRow.id)
        if enabled_only:
            stmt = stmt.where(AlertRuleRow.enabled.is_(True))
        with self._session() as session:
            return [_rule_from_row(row) for row in session.scalars(stmt)]

    def get_rule(self, rule_id: str) -> AlertRule | None:
        with self._session() as session:
            row = session.get(AlertRuleRow, rule_id)
            return _rule_from_row(row) if row is not None else None

    def create_rule(self, data: AlertRuleIn) -> AlertRule:
        rule = AlertRule(id=str(uuid.uuid4()), **data.model_dump())
        row = AlertRuleRow(id=rule.id, created_at=datetime.now(UTC))
        _apply_rule(row, rule)
        with self._session() as session, session.begin():
            session.add(row)
        return rule

    def update_rule(self, rule: AlertRule) -> AlertRule | None:
        with self._session() as session, session.begin():
            row = session.get(AlertRuleRow, rule.id)
            if row is None:
                return None
            _apply_rule(row, rule)
        return rule

    def delete_rule(self, rule_id: str) -> bool:
        with self._session() as session, session.begin():
            row = session.get(AlertRuleRow, rule_id)
            if row is None:
                return False
            session.delete(row)  # o histórico (notify_alert_events) fica: é registro do que foi enviado
            return True

    def add_event(self, event: AlertEvent, *, dedupe_key: str | None = None) -> None:
        row = AlertEventRow(
            id=event.id,
            rule_id=event.rule_id,
            ts=_utc(event.ts),
            message=event.message,
            payload=dict(event.payload),
            channel=event.channel,
            delivered=event.delivered,
            error=event.error,
            dedupe_key=dedupe_key,
        )
        with self._session() as session, session.begin():
            session.add(row)

    def list_events(
        self, *, rule_id: str | None = None, since: datetime | None = None, limit: int = 200
    ) -> list[AlertEvent]:
        stmt = select(AlertEventRow).order_by(AlertEventRow.seq.desc()).limit(limit)
        if rule_id is not None:
            stmt = stmt.where(AlertEventRow.rule_id == rule_id)
        if since is not None:
            stmt = stmt.where(AlertEventRow.ts >= _utc(since))
        with self._session() as session:
            return [_event_from_row(row) for row in session.scalars(stmt)]

    def last_fired(self) -> dict[tuple[str, str], datetime]:
        stmt = (
            select(AlertEventRow.rule_id, AlertEventRow.dedupe_key, func.max(AlertEventRow.ts))
            .where(AlertEventRow.dedupe_key.is_not(None))
            .group_by(AlertEventRow.rule_id, AlertEventRow.dedupe_key)
        )
        with self._session() as session:
            return {(rid, key): _utc(ts) for rid, key, ts in session.execute(stmt)}
