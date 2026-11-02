"""Test doubles shared by service and API tests: an in-memory adapter and a controllable clock."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from fronteira_fx.adapters.base import AdapterInfo, AdapterResult, AdapterStatus, EvidenceDraft, Fee, QuoteDraft
from tests.conftest import NOW

D = Decimal


class FakeAdapter:
    def __init__(
        self, source_id="chaco", *, status=AdapterStatus.OK, sha="abc", method="html", quotes=None, raise_exc=False
    ):
        self.info = AdapterInfo(
            id=source_id,
            name=source_id.title(),
            kind="exchange_house",
            method=method,
            url=f"https://{source_id}.example",
            capabilities=["buy_sell"],
            limitations=[],
            cities=["CDE"],
            currencies=["USD", "PYG"],
            poll_interval_s=300,
        )
        self.status = status
        self.sha = sha
        self.calls = 0
        self.raise_exc = raise_exc
        self.quotes = quotes

    def _quotes(self):
        if self.quotes is not None:
            return self.quotes
        return [
            QuoteDraft(
                source_id=self.info.id,
                base="USD",
                quote="PYG",
                buy=D("7300"),
                sell=D("7350"),
                unit_note="PYG por 1 USD",
                modality="cash",
                kind="indicative",
                channel="physical",
                city="CDE",
                branch_id=f"{self.info.id}-cde",
                fees=[Fee("tarifa", D("0"), "PYG")],
                declared_updated_at=datetime(2026, 11, 2, 11, 0, tzinfo=UTC),
            )
        ]

    async def fetch(self, **params):
        self.calls += 1
        if self.raise_exc:
            raise RuntimeError("boom")
        if self.status in (AdapterStatus.BLOCKED, AdapterStatus.ERROR):
            return AdapterResult(status=self.status, quotes=[], evidence=None, message="403 anti-bot")
        ev = EvidenceDraft(
            source_id=self.info.id,
            kind="html",
            url=self.info.url,
            captured_at=NOW,
            sha256=self.sha,
            excerpt="<table>...</table>",
            rules=["parser v1"],
        )
        return AdapterResult(status=self.status, quotes=self._quotes(), evidence=ev)

    def parse(self, raw, *, captured_at, url, **params):
        raise NotImplementedError


class Clock:
    def __init__(self, t=NOW):
        self.t = t

    def __call__(self):
        return self.t
