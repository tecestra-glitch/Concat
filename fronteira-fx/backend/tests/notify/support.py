"""Builders de payload e dublês compartilhados pelos testes do notify."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fronteira_fx.notify.channels import ChannelError
from fronteira_fx.notify.rules import AlertEvent, AlertRule

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
D = Decimal


def make_rule(**overrides: Any) -> AlertRule:
    data: dict[str, Any] = {
        "id": "r1",
        "name": "regra de teste",
        "kind": "cycle_roi",
        "threshold": D("0.001"),
        "params": None,
        "channel": "ui",
        "target": None,
        "cooldown_s": 600,
        "enabled": True,
    }
    data.update(overrides)
    return AlertRule(**data)


def cycle_payload(
    roi: float = 0.001648,
    *,
    gain: float = 41.2,
    path: list[str] | None = None,
    minutes: int = 4320,
    confidence: str = "estimated",
) -> dict[str, Any]:
    """Cycle do contrato (números, como o engine devolve)."""
    nodes = path or ["BRL@brbank", "PYG@ueno", "USD@ueno", "BRL@brbank"]
    return {
        "start": nodes[0],
        "path": nodes,
        "edges": [],
        "amountIn": 25000,
        "amountOut": 25041.2,
        "gain": gain,
        "roi": roi,
        "minutes": minutes,
        "confidence": confidence,
    }


def quote_payload(
    buy: str | None = "1000",
    sell: str | None = "1000",
    *,
    city: str | None = "CDE",
    source: str = "chaco",
    base: str = "USD",
    quote: str = "PYG",
    kind: str = "indicative",
    modality: str = "cash",
    branch: str | None = None,
) -> dict[str, Any]:
    return {
        "id": f"q-{source}-{city}-{buy}-{sell}",
        "source_id": source,
        "branch_id": branch,
        "city": city,
        "base": base,
        "quote": quote,
        "buy": buy,
        "sell": sell,
        "modality": modality,
        "kind": kind,
        "channel": "physical",
        "data_mode": "real",
    }


def opportunity_payload(
    *,
    opp_id: str = "opp-1",
    in_main: bool = True,
    roi: str = "0.00842",
    channel: str = "digital",
    city: str | None = None,
    title: str = "Ciclo BRL→USD→BRL",
) -> dict[str, Any]:
    return {
        "id": opp_id,
        "title": title,
        "kind": "cycle",
        "channel": channel,
        "city": city,
        "capital_brl": "5000",
        "net_gain_brl": "42.10",
        "roi": roi,
        "in_main_ranking": in_main,
        "data_mode": "real",
    }


def source_payload(
    source_id: str = "chaco",
    health: str = "ok",
    *,
    last_error: str | None = None,
    name: str | None = "Cambios Chaco",
) -> dict[str, Any]:
    return {"id": source_id, "name": name, "health": health, "last_error": last_error}


def change_payload(source_id: str = "chaco", status: str = "error", summary: str = "status ok → error") -> dict:
    return {
        "id": "chg-1",
        "source_id": source_id,
        "ts": NOW.isoformat(),
        "kind": "status_change",
        "summary": summary,
        "before": {"status": "ok"},
        "after": {"status": status, "last_error": "timeout"},
        "evidence_id": None,
    }


class FakeChannel:
    """Canal de teste: registra os envios e pode falhar de forma controlada."""

    def __init__(self, name: str, *, error: str | None = None, exc: Exception | None = None) -> None:
        self.name = name
        self.error = error
        self.exc = exc
        self.sent: list[AlertEvent] = []

    def send(self, rule: AlertRule, event: AlertEvent) -> None:
        self.sent.append(event)
        if self.exc is not None:
            raise self.exc
        if self.error is not None:
            raise ChannelError(self.error)


def make_event(channel: str = "ui", message: str = "Ciclo BRL@a → BRL@a: +R$ 1,00 (0,100 %) em 0 min") -> AlertEvent:
    return AlertEvent(id="e-1", rule_id="r1", ts=NOW, message=message, payload={"x": 1}, channel=channel)
