"""Rotas `/v1/alerts` (contrato `docs/api-contract.md`, seção "Alertas / notificações — módulo notify").

O serviço entra por `get_service()`. O core troca a implementação com
`app.dependency_overrides[get_service] = lambda: service`. Sem override, usa um serviço em memória
com canais lidos do ambiente (adequado a dev; alertas e histórico somem ao reiniciar).
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError

from .channels import build_channels
from .rules import AlertEvent, AlertRule, AlertRuleIn, AlertRulePatch
from .service import AlertService
from .store import InMemoryAlertStore

router = APIRouter(prefix="/v1/alerts", tags=["alerts"])

_default_service: AlertService | None = None
_default_lock = threading.Lock()


def get_service() -> AlertService:
    """Fábrica do serviço. O core sobrescreve esta dependência com o store SQLAlchemy e os canais reais."""
    global _default_service
    with _default_lock:
        if _default_service is None:
            _default_service = AlertService(InMemoryAlertStore(), build_channels())
        return _default_service


ServiceDep = Annotated[AlertService, Depends(get_service)]


@router.get("/rules", operation_id="list_alert_rules")
def list_alert_rules(service: ServiceDep) -> list[AlertRule]:
    return service.list_rules()


@router.post("/rules", status_code=201, operation_id="create_alert_rule")
def create_alert_rule(body: AlertRuleIn, service: ServiceDep) -> AlertRule:
    return service.create_rule(body)


@router.patch("/rules/{rule_id}", operation_id="update_alert_rule")
def update_alert_rule(rule_id: str, body: AlertRulePatch, service: ServiceDep) -> AlertRule:
    try:
        updated = service.patch_rule(rule_id, body)
    except ValidationError as exc:
        detail = jsonable_encoder(exc.errors(include_url=False, include_context=False))
        raise HTTPException(status_code=422, detail=detail) from None
    if updated is None:
        raise HTTPException(status_code=404, detail="regra não encontrada")
    return updated


@router.delete("/rules/{rule_id}", status_code=204, operation_id="delete_alert_rule")
def delete_alert_rule(rule_id: str, service: ServiceDep) -> None:
    if not service.delete_rule(rule_id):
        raise HTTPException(status_code=404, detail="regra não encontrada")


@router.get("/events", operation_id="list_alert_events")
def list_alert_events(
    service: ServiceDep,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    rule: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[AlertEvent]:
    return service.list_events(rule_id=rule, since=from_, limit=limit)


@router.post("/test/{rule_id}", operation_id="test_alert_rule")
def test_alert_rule(rule_id: str, service: ServiceDep) -> AlertEvent:
    event = service.test_rule(rule_id)
    if event is None:
        raise HTTPException(status_code=404, detail="regra não encontrada")
    return event
