from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import select

from ..models import AlertEvent, AlertRule, utcnow
from ..schemas import AlertEventOut, AlertRuleCreate, AlertRuleOut, AlertRulePatch
from ..services import alerts as alerts_svc
from .deps import ApiKey, DataModeDep, DbDep, SettingsDep

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/rules", operation_id="list_alert_rules")
def list_rules(db: DbDep, data_mode: DataModeDep) -> list[AlertRuleOut]:
    rows = db.scalars(select(AlertRule).where(AlertRule.data_mode == data_mode).order_by(AlertRule.created_at))
    return [AlertRuleOut.model_validate(r) for r in rows]


@router.post("/rules", operation_id="create_alert_rule", status_code=status.HTTP_201_CREATED, dependencies=[ApiKey])
def create_rule(body: AlertRuleCreate, db: DbDep, data_mode: DataModeDep) -> AlertRuleOut:
    row = AlertRule(**body.model_dump(), data_mode=data_mode, created_at=utcnow())
    db.add(row)
    db.flush()
    return AlertRuleOut.model_validate(row)


def _get_rule(db, rule_id: str, data_mode: str) -> AlertRule:
    row = db.get(AlertRule, rule_id)
    if row is None or row.data_mode != data_mode:
        raise HTTPException(status_code=404, detail="regra não encontrada")
    return row


@router.patch("/rules/{rule_id}", operation_id="update_alert_rule", dependencies=[ApiKey])
def update_rule(rule_id: str, body: AlertRulePatch, db: DbDep, data_mode: DataModeDep) -> AlertRuleOut:
    row = _get_rule(db, rule_id, data_mode)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    db.flush()
    return AlertRuleOut.model_validate(row)


@router.delete(
    "/rules/{rule_id}", operation_id="delete_alert_rule", status_code=status.HTTP_204_NO_CONTENT, dependencies=[ApiKey]
)
def delete_rule(rule_id: str, db: DbDep, data_mode: DataModeDep) -> None:
    db.delete(_get_rule(db, rule_id, data_mode))
    db.flush()


@router.get("/events", operation_id="list_alert_events")
def list_events(
    db: DbDep,
    data_mode: DataModeDep,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    rule: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[AlertEventOut]:
    stmt = select(AlertEvent).where(AlertEvent.data_mode == data_mode)
    if from_:
        stmt = stmt.where(AlertEvent.ts >= from_)
    if rule:
        stmt = stmt.where(AlertEvent.rule_id == rule)
    rows = db.scalars(stmt.order_by(AlertEvent.ts.desc()).limit(limit))
    return [alerts_svc.event_to_out(r) for r in rows]


@router.post(
    "/test/{rule_id}",
    operation_id="test_alert_rule",
    dependencies=[ApiKey],
    summary="Send a test message through the rule's channel",
)
async def test_rule(rule_id: str, request: Request, settings: SettingsDep, data_mode: DataModeDep) -> AlertEventOut:
    ev = await alerts_svc.fire_test(request.app.state.session_factory, rule_id, settings, data_mode=data_mode)
    if ev is None:
        raise HTTPException(status_code=404, detail="regra não encontrada")
    return alerts_svc.event_to_out(ev)
