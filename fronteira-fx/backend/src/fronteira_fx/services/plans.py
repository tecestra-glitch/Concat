"""Planos de execução (fase A): organizam os passos de um ciclo para o dono seguir. NADA aqui executa movimentação
financeira. Aprovar só grava a decisão; cada passo concluído só grava o que o dono informou.

Estados: proposed → approved → in_progress → done; ou rejected; ou expired (a cotação mais velha do plano passou de
`quote_max_age_s` antes de a execução começar). Ao concluir todos os passos, o resultado (esperado × realizado) vai
para o diário existente (`JournalEntry`, kind `result`).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..adapters.registry import ADAPTERS
from ..decimal_utils import fmt
from ..engine.graph import node_currency
from ..models import Evidence, ExecutionPlan, ExecutionStep, JournalEntry

ACTIVE_BEFORE_START = ("proposed", "approved")
# força relativa para a convenção do balcão: a cotação é "1 <moeda forte> = quanto da fraca" (1 USD = 5,40 BRL)
CURRENCY_STRENGTH = {"USD": 3, "BRL": 2, "PYG": 1}
# nomes de contas e instituições sem adaptador, em português simples
INSTITUTION_NAMES = {
    "nubank": "Nubank",
    "itau": "Itaú",
    "bradesco": "Bradesco",
    "caixa": "Caixa",
    "brbank": "banco brasileiro",
    "banco_py": "banco paraguaio",
    "revolut": "Revolut",
    "nomad": "Nomad",
}


class PlanError(Exception):
    """Erro de regra do plano; `status` é o código HTTP que a rota devolve."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


def money_text(value: Decimal, currency: str) -> str:
    """'1.234,50 USD', '1.000 USD', '7.300.000 PYG' (pt-BR; sem centavos quando o valor é inteiro ou é guarani).
    Arredondar só aqui, na exibição."""
    places = 0 if currency == "PYG" or value == value.to_integral_value() else 2
    q = value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_EVEN)
    sign = "-" if q < 0 else ""
    body = f"{abs(q):,.{places}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{sign}{body} {currency}"


def place_name(venue: str) -> str:
    """Nome para o usuário: 'Cambios Chaco (CDE)', 'dinheiro vivo em CDE', 'Revolut', 'Nubank'."""
    if venue.startswith("cash:"):
        return f"dinheiro vivo em {venue.split(':', 1)[1]}"
    if ":" in venue:
        source, city = venue.split(":", 1)
        adapter = ADAPTERS.get(source)
        return f"{adapter.info.name if adapter else INSTITUTION_NAMES.get(source, source)} ({city})"
    adapter = ADAPTERS.get(venue)
    if adapter is not None:
        return adapter.info.name
    return INSTITUTION_NAMES.get(venue, venue)


def rate_text(a_in: Decimal, a_out: Decimal, src_ccy: str, dst_ccy: str) -> str:
    """Cotação na convenção do balcão: 1 unidade da moeda mais forte = quanto da mais fraca.
    Ex.: '1 USD = 5,40 BRL', '1 BRL = 1.300 PYG'. Nunca arredonda o preço para zero."""
    if not a_in or not a_out:
        return "cotação não informada"
    if CURRENCY_STRENGTH.get(src_ccy, 0) > CURRENCY_STRENGTH.get(dst_ccy, 0):
        strong, weak, per_strong = src_ccy, dst_ccy, a_out / a_in
    else:
        strong, weak, per_strong = dst_ccy, src_ccy, a_in / a_out
    return f"1 {strong} = {money_text(per_strong, weak)}"


def _split(node_id: str) -> tuple[str, str]:
    venue = node_id.split("@", 1)[1] if "@" in node_id else ""
    return node_currency(node_id), venue


def _city_of(venue: str) -> str:
    return venue.split(":", 1)[1] if ":" in venue else venue


def leg_text(leg: dict[str, Any]) -> str:
    """Frase de um passo, em português simples. Ex.: 'Leve o dinheiro de CDE para FOZ (≈ 40 min)'."""
    src_ccy, src_venue = _split(leg["from"])
    dst_ccy, dst_venue = _split(leg["to"])
    a_in = Decimal(str(leg["amount_in"]))
    a_out = Decimal(str(leg["amount_out"]))
    minutes = int(leg.get("minutes") or 0)
    kind = leg["kind"]
    if kind == "travel":
        return f"Leve o dinheiro de {_city_of(src_venue)} para {_city_of(dst_venue)} (≈ {minutes} min)"
    if kind == "exchange":
        return (
            f"Compre {money_text(a_out, dst_ccy)} na {place_name(src_venue)} pagando {money_text(a_in, src_ccy)} "
            f"(cotação: {rate_text(a_in, a_out, src_ccy, dst_ccy)})"
        )
    if kind == "transfer" and src_ccy != dst_ccy:
        # transferência que converte: diz o que sai (na moeda de origem) e o que chega (aproximado)
        return (
            f"Envie {money_text(a_in, src_ccy)} de {place_name(src_venue)} e receba ≈ {money_text(a_out, dst_ccy)} "
            f"em {place_name(dst_venue)} (≈ {minutes} min)"
        )
    if kind == "transfer":
        return (
            f"Transfira {money_text(a_out, dst_ccy)} de {place_name(src_venue)} para {place_name(dst_venue)} "
            f"(≈ {minutes} min)"
        )
    if kind == "withdraw":
        return f"Retire {money_text(a_out, dst_ccy)} de {place_name(src_venue)}"
    if kind == "deposit":
        return f"Deposite {money_text(a_in, src_ccy)} em {place_name(dst_venue)}"
    return f"Mova {money_text(a_out, dst_ccy)} de {place_name(src_venue)} para {place_name(dst_venue)}"


def build_steps(cycle: dict[str, Any]) -> list[dict[str, Any]]:
    """Passos pendentes, na ordem das pernas do ciclo (snapshot dos montantes esperados)."""
    steps: list[dict[str, Any]] = []
    for n, leg in enumerate(cycle.get("legs") or [], start=1):
        steps.append(
            {
                "n": n,
                "kind": leg["kind"],
                "channel": leg["channel"],
                "text": leg_text(leg),
                "node_from": leg["from"],
                "node_to": leg["to"],
                "amount_in": Decimal(str(leg["amount_in"])),
                "amount_out_expected": Decimal(str(leg["amount_out"])),
                "minutes": int(leg.get("minutes") or 0),
                "status": "pending",
            }
        )
    return steps


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _oldest_quote(session: Session, cycle: dict[str, Any]) -> datetime | None:
    ids = [e["evidence_id"] for e in cycle.get("edges") or [] if e.get("evidence_id")]
    if not ids:
        return None
    return session.scalar(select(Evidence.captured_at).where(Evidence.id.in_(ids)).order_by(Evidence.captured_at))


def _quotes_snapshot(cycle: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"evidence_id": e["evidence_id"], "via": e["via"], "rate": e["rate"]}
        for e in cycle.get("edges") or []
        if e.get("evidence_id")
    ]


def create_plan(
    session: Session,
    *,
    cycles: Iterable[dict[str, Any]],
    start: str,
    path: list[str],
    data_mode: str,
    now: datetime,
    max_age_s: int,
) -> ExecutionPlan:
    """Plano a partir de um ciclo calculado agora (mesmo `start` e mesmo `path`). Sem ciclo igual, 404."""
    match = next((c for c in cycles if c.get("start") == start and list(c.get("path") or []) == path), None)
    if match is None:
        raise PlanError(404, "ciclo não encontrado com as cotações e saldos atuais; calcule os ciclos de novo")
    if Decimal(str(match["gain"])) <= 0:
        # um plano só organiza uma rota que ganha dinheiro; ciclo sem ganho líquido positivo não vira plano
        raise PlanError(422, "só ciclo com ganho líquido positivo vira plano")
    quotes_as_of = _oldest_quote(session, match) or now
    plan = ExecutionPlan(
        status="proposed",
        start=start,
        path=list(path),
        currency=node_currency(start),
        amount_in=Decimal(str(match["amount_in"])),
        amount_out_expected=Decimal(str(match["amount_out"])),
        gain_expected=Decimal(str(match["gain"])),
        gain_by_currency=match.get("gain_by_currency"),
        confidence=match["confidence"],
        minutes=int(match.get("minutes") or 0),
        requires_declaration=bool(match.get("requires_declaration")),
        snapshot={
            "edges": match.get("edges") or [],
            "legs": match.get("legs") or [],
            "costs": match.get("costs"),
            "quotes": _quotes_snapshot(match),
        },
        quotes_as_of=quotes_as_of,
        quote_max_age_s=max_age_s,
        created_at=now,
        data_mode=data_mode,
        steps=[ExecutionStep(data_mode=data_mode, **step) for step in build_steps(match)],
    )
    session.add(plan)
    session.flush()
    return plan


def refresh_status(plan: ExecutionPlan, *, now: datetime) -> str:
    """Aplica a expiração: só planos ainda não iniciados expiram (proposed/approved)."""
    if plan.status in ACTIVE_BEFORE_START and plan.quotes_as_of is not None:
        age = now - _aware(plan.quotes_as_of)
        if age > timedelta(seconds=plan.quote_max_age_s):
            plan.status = "expired"
    return plan.status


def approve(session: Session, plan: ExecutionPlan, *, now: datetime) -> ExecutionPlan:
    status = refresh_status(plan, now=now)
    if status == "expired":
        raise PlanError(409, "plano expirado: a cotação mais velha passou do limite; calcule um plano novo")
    if status != "proposed":
        raise PlanError(409, "só um plano proposto pode ser aprovado")
    plan.status = "approved"
    plan.decided_at = now
    session.flush()
    return plan


def reject(session: Session, plan: ExecutionPlan, *, now: datetime) -> ExecutionPlan:
    status = refresh_status(plan, now=now)
    if status not in ACTIVE_BEFORE_START:
        raise PlanError(409, "só um plano proposto ou aprovado pode ser recusado")
    plan.status = "rejected"
    plan.decided_at = now
    session.flush()
    return plan


def mark_step_done(
    session: Session,
    plan: ExecutionPlan,
    n: int,
    *,
    actual_out: Decimal,
    note: str | None,
    now: datetime,
) -> ExecutionPlan:
    """Registra o que o dono fez no passo `n` (valor realizado e nota). Passos em ordem, um de cada vez."""
    status = refresh_status(plan, now=now)
    if status == "expired":
        raise PlanError(409, "plano expirado: calcule um plano novo antes de executar")
    if status not in ("approved", "in_progress"):
        raise PlanError(409, "o plano precisa estar aprovado antes de registrar passos")
    step = next((s for s in plan.steps if s.n == n), None)
    if step is None:
        raise PlanError(404, f"passo {n} não existe neste plano")
    if step.status == "done":
        raise PlanError(409, f"o passo {n} já está concluído")
    if any(s.n < n and s.status != "done" for s in plan.steps):
        raise PlanError(409, "conclua os passos anteriores antes deste")
    step.status = "done"
    step.actual_out = actual_out
    step.note = note
    step.done_at = now
    plan.status = "in_progress"
    if all(s.status == "done" for s in plan.steps):
        plan.status = "done"
        plan.completed_at = now
        _record_result(session, plan, now)
    session.flush()
    return plan


def _record_result(session: Session, plan: ExecutionPlan, now: datetime) -> None:
    """Resultado do plano no diário: esperado × realizado, na moeda de partida."""
    expected = plan.amount_out_expected
    realized = plan.steps[-1].actual_out if plan.steps and plan.steps[-1].actual_out is not None else expected
    diff = realized - expected
    ccy = plan.currency
    text = (
        f"Plano {plan.id[:8]} concluído: esperado {money_text(expected, ccy)}, "
        f"realizado {money_text(realized, ccy)} (diferença {money_text(diff, ccy)})"
    )
    session.add(
        JournalEntry(
            ts=now,
            kind="result",
            text=text,
            amounts=[
                {"label": "esperado", "amount": fmt(expected, None), "currency": ccy},
                {"label": "realizado", "amount": fmt(realized, None), "currency": ccy},
            ],
            account_ids=[],
            data_mode=plan.data_mode,
        )
    )
