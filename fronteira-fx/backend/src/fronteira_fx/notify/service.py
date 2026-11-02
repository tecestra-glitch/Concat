"""Serviço de alertas: avalia as regras a cada evento do stream, entrega e registra o histórico.

O core chama `handle(event_type, payload)` para cada evento de `quote.updated`, `opportunity.updated`,
`source.health`, `source.change` e `cycle.found`. O retorno são os disparos (com `delivered`/`error`);
o core publica cada um no stream como `alert.fired`.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from . import messages
from .channels import Channel, ChannelError
from .rules import (
    KIND_EVENTS,
    AlertEvent,
    AlertRule,
    AlertRuleIn,
    AlertRulePatch,
    AlertState,
    dedupe_key,
    evaluate,
    merge_rule,
)
from .store import AlertStore

log = logging.getLogger("fronteira_fx.notify")


class AlertService:
    """Orquestra regras (`AlertStore`), avaliação (`evaluate`) e entrega (`Channel`).

    `state` guarda observações e cooldowns em memória. Ao iniciar, os cooldowns são restaurados do
    histórico persistido (`store.last_fired()`), para um reinício não repetir alertas recentes.
    """

    def __init__(
        self,
        store: AlertStore,
        channels: Mapping[str, Channel],
        *,
        state: AlertState | None = None,
        restore_cooldowns: bool = True,
    ) -> None:
        self._store = store
        self._channels: dict[str, Channel] = dict(channels)
        self._state = state if state is not None else AlertState()
        self._lock = threading.RLock()
        if restore_cooldowns:
            for slot, fired_at in store.last_fired().items():
                self._state.fired.setdefault(slot, fired_at)

    @property
    def store(self) -> AlertStore:
        return self._store

    # --- regras e histórico (usados pelo router) ---

    def list_rules(self) -> list[AlertRule]:
        return self._store.list_rules()

    def get_rule(self, rule_id: str) -> AlertRule | None:
        return self._store.get_rule(rule_id)

    def create_rule(self, data: AlertRuleIn) -> AlertRule:
        return self._store.create_rule(data)

    def patch_rule(self, rule_id: str, patch: AlertRulePatch) -> AlertRule | None:
        """Aplica o PATCH. Levanta `pydantic.ValidationError` se a regra resultante for inválida."""
        current = self._store.get_rule(rule_id)
        if current is None:
            return None
        return self._store.update_rule(merge_rule(current, patch))

    def delete_rule(self, rule_id: str) -> bool:
        removed = self._store.delete_rule(rule_id)
        if removed:
            with self._lock:
                self._state.forget_rule(rule_id)
        return removed

    def list_events(
        self, *, rule_id: str | None = None, since: datetime | None = None, limit: int = 200
    ) -> list[AlertEvent]:
        return self._store.list_events(rule_id=rule_id, since=since, limit=limit)

    def test_rule(self, rule_id: str, *, now: datetime | None = None) -> AlertEvent | None:
        """Envia uma mensagem de teste pelo canal da regra (mesmo se a regra estiver desabilitada)."""
        rule = self._store.get_rule(rule_id)
        if rule is None:
            return None
        event = AlertEvent(
            id=str(uuid.uuid4()),
            rule_id=rule.id,
            ts=now or datetime.now(UTC),
            message=messages.delivery_check_text(rule_name=rule.name, channel=rule.channel),
            payload={"test": True},
            channel=rule.channel,
        )
        delivered, error = self._deliver(rule, event)
        final = event.model_copy(update={"delivered": delivered, "error": error})
        self._store.add_event(final, dedupe_key=None)
        return final

    # --- caminho quente: chamado pelo core para cada evento do stream ---

    def handle(self, event_type: str, payload: Mapping[str, Any], *, now: datetime | None = None) -> list[AlertEvent]:
        """Avalia todas as regras habilitadas para `event_type`, entrega e registra. Devolve os disparos."""
        moment = now or datetime.now(UTC)
        pending: list[tuple[AlertRule, AlertEvent, str]] = []
        with self._lock:
            for rule in self._store.list_rules(enabled_only=True):
                if event_type not in KIND_EVENTS.get(rule.kind, frozenset()):
                    continue
                try:
                    event = evaluate(rule, event_type, payload, self._state, now=moment)
                    key = dedupe_key(rule, event_type, payload) if event is not None else None
                except Exception:  # uma regra malformada não pode derrubar as demais
                    log.exception("regra %s falhou ao avaliar %s", rule.id, event_type)
                    continue
                if event is not None and key is not None:
                    pending.append((rule, event, key))

        fired: list[AlertEvent] = []
        for rule, event, key in pending:
            delivered, error = self._deliver(rule, event)
            final = event.model_copy(update={"delivered": delivered, "error": error})
            self._store.add_event(final, dedupe_key=key)
            fired.append(final)
        return fired

    def _deliver(self, rule: AlertRule, event: AlertEvent) -> tuple[bool, str | None]:
        channel = self._channels.get(rule.channel)
        if channel is None:
            return False, f"canal {rule.channel} não configurado"
        try:
            channel.send(rule, event)
        except ChannelError as exc:  # a mensagem já vem sanitizada pelo canal
            error = str(exc)[:300]
            log.warning("alerta %s não entregue pelo canal %s: %s", rule.id, rule.channel, error)
            return False, error
        except Exception as exc:  # canal de terceiros: só o nome da classe, sem conteúdo que possa ter segredo
            error = f"erro inesperado no canal ({type(exc).__name__})"
            log.warning("alerta %s não entregue pelo canal %s: %s", rule.id, rule.channel, error)
            return False, error
        return True, None
