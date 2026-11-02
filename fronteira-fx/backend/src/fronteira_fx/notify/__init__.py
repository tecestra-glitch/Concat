"""Alertas e notificações (módulo `notify`): regras, avaliação, canais, store, serviço e rotas `/v1/alerts`.

Uso pelo core: ver `docs/alertas.md`.
"""

from .channels import (
    Channel,
    ChannelError,
    EmailChannel,
    NotifySettings,
    TelegramChannel,
    UiChannel,
    WebhookChannel,
    build_channels,
    verify_webhook_signature,
)
from .router import get_service, router
from .rules import AlertEvent, AlertRule, AlertRuleIn, AlertRulePatch, AlertState, evaluate
from .service import AlertService
from .store import (
    AlertStore,
    InMemoryAlertStore,
    NotifyBase,
    SqlAlchemyAlertStore,
    create_notify_tables,
)

__all__ = [
    "AlertEvent",
    "AlertRule",
    "AlertRuleIn",
    "AlertRulePatch",
    "AlertService",
    "AlertState",
    "AlertStore",
    "Channel",
    "ChannelError",
    "EmailChannel",
    "InMemoryAlertStore",
    "NotifyBase",
    "NotifySettings",
    "SqlAlchemyAlertStore",
    "TelegramChannel",
    "UiChannel",
    "WebhookChannel",
    "build_channels",
    "create_notify_tables",
    "evaluate",
    "get_service",
    "router",
    "verify_webhook_signature",
]
