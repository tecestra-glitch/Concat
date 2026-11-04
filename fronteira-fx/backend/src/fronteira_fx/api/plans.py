"""Planos de execução (fase A). Nenhuma rota aqui movimenta dinheiro: aprovar grava a decisão e cada passo
grava o que o dono informou. Escritas exigem a API key, como as demais."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from ..models import ExecutionPlan, utcnow
from ..schemas import PlanCreateIn, PlanOut, PlanStepOut, StepDoneIn
from ..services.cycles import find_cycles_for
from ..services.plans import PlanError, approve, create_plan, mark_step_done, refresh_status, reject
from .deps import ApiKey, DataModeDep, DbDep, SettingsDep

router = APIRouter(prefix="/plans", tags=["plans"])


def _out(plan: ExecutionPlan, now) -> PlanOut:
    refresh_status(plan, now=now)
    return PlanOut(
        id=plan.id,
        status=plan.status,  # type: ignore[arg-type]
        start=plan.start,
        path=list(plan.path),
        currency=plan.currency,  # type: ignore[arg-type]
        amount_in=plan.amount_in,
        amount_out_expected=plan.amount_out_expected,
        gain_expected=plan.gain_expected,
        gain_by_currency=_money(plan.gain_by_currency),
        confidence=plan.confidence,  # type: ignore[arg-type]
        minutes=plan.minutes,
        requires_declaration=plan.requires_declaration,
        quotes_as_of=plan.quotes_as_of,
        quote_max_age_s=plan.quote_max_age_s,
        created_at=plan.created_at,
        decided_at=plan.decided_at,
        completed_at=plan.completed_at,
        data_mode=plan.data_mode,  # type: ignore[arg-type]
        steps=[
            PlanStepOut(
                n=s.n,
                kind=s.kind,  # type: ignore[arg-type]
                channel=s.channel,  # type: ignore[arg-type]
                text=s.text,
                from_=s.node_from,
                to=s.node_to,
                amount_in=s.amount_in,
                amount_out_expected=s.amount_out_expected,
                minutes=s.minutes,
                status=s.status,  # type: ignore[arg-type]
                actual_out=s.actual_out,
                note=s.note,
                done_at=s.done_at,
            )
            for s in plan.steps
        ],
    )


def _money(values: dict | None) -> dict | None:
    if values is None:
        return None
    return {k: (Decimal(str(v)) if v is not None else None) for k, v in values.items()}


def _get(db, plan_id: str, data_mode: str) -> ExecutionPlan:
    plan = db.get(ExecutionPlan, plan_id)
    if plan is None or plan.data_mode != data_mode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plano não encontrado")
    return plan


def _raise(err: PlanError) -> None:
    raise HTTPException(status_code=err.status, detail=err.detail)


@router.post(
    "",
    operation_id="create_plan",
    status_code=status.HTTP_201_CREATED,
    summary="Plano de execução a partir de um ciclo atual (nada é executado)",
    dependencies=[ApiKey],
)
def create(body: PlanCreateIn, db: DbDep, data_mode: DataModeDep, settings: SettingsDep) -> PlanOut:
    cycles = find_cycles_for(
        db,
        data_mode=data_mode,
        max_len=len(body.path) - 1,
        start=body.start,
        limit=500,
        lookback_s=settings.quotes_lookback_s,
    )
    now = utcnow()
    try:
        plan = create_plan(
            db,
            cycles=cycles,
            start=body.start,
            path=body.path,
            data_mode=data_mode,
            now=now,
            max_age_s=settings.plan_quote_max_age_s,
        )
    except PlanError as err:
        _raise(err)
    return _out(plan, now)


@router.get("", operation_id="list_plans", summary="Planos deste modo, do mais recente para o mais antigo")
def list_plans(
    db: DbDep,
    data_mode: DataModeDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[PlanOut]:
    rows = db.scalars(
        select(ExecutionPlan)
        .where(ExecutionPlan.data_mode == data_mode)
        .order_by(ExecutionPlan.created_at.desc())
        .limit(limit)
    ).all()
    now = utcnow()
    return [_out(p, now) for p in rows]


@router.get("/{plan_id}", operation_id="get_plan", summary="Um plano, com os passos")
def get_plan(plan_id: str, db: DbDep, data_mode: DataModeDep) -> PlanOut:
    return _out(_get(db, plan_id, data_mode), utcnow())


@router.post(
    "/{plan_id}/approve",
    operation_id="approve_plan",
    summary="Aprova: só grava a decisão",
    dependencies=[ApiKey],
)
def approve_plan(plan_id: str, db: DbDep, data_mode: DataModeDep) -> PlanOut:
    now = utcnow()
    plan = _get(db, plan_id, data_mode)
    try:
        approve(db, plan, now=now)
    except PlanError as err:
        _raise(err)
    return _out(plan, now)


@router.post("/{plan_id}/reject", operation_id="reject_plan", summary="Recusa o plano", dependencies=[ApiKey])
def reject_plan(plan_id: str, db: DbDep, data_mode: DataModeDep) -> PlanOut:
    now = utcnow()
    plan = _get(db, plan_id, data_mode)
    try:
        reject(db, plan, now=now)
    except PlanError as err:
        _raise(err)
    return _out(plan, now)


@router.post(
    "/{plan_id}/steps/{n}/done",
    operation_id="complete_plan_step",
    summary="Marca um passo como feito, com o valor realizado",
    dependencies=[ApiKey],
)
def complete_step(plan_id: str, n: int, body: StepDoneIn, db: DbDep, data_mode: DataModeDep) -> PlanOut:
    now = utcnow()
    plan = _get(db, plan_id, data_mode)
    try:
        mark_step_done(db, plan, n, actual_out=Decimal(body.actual_out), note=body.note, now=now)
    except PlanError as err:
        _raise(err)
    return _out(plan, now)
