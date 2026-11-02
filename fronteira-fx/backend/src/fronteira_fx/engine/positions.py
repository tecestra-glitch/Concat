"""Positions: where money sits (currency, institution/account, location, modality)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from ..decimal_utils import ZERO, fmt


@dataclass(frozen=True, slots=True)
class Position:
    currency: str
    institution: str | None = None  # "ueno", "wu", "chaco", ... (None = cash in hand)
    account_id: str | None = None
    location: str = "digital"  # "digital" | "CDE" | "ASU" | "PJC"
    modality: str = "account"  # cash | transfer | account | card_debit | card_credit | card_virtual

    def label(self) -> str:
        who = self.institution or ("dinheiro" if self.modality == "cash" else "conta")
        return f"{self.currency} {who} ({self.location}, {self.modality})"

    def to_dict(self, amount: Decimal | None = None) -> dict[str, Any]:
        return {
            "currency": self.currency,
            "account_id": self.account_id,
            "institution": self.institution,
            "location": self.location,
            "modality": self.modality,
            "amount": fmt(amount) if amount is not None else None,
        }


@dataclass(frozen=True, slots=True)
class Balance:
    """Balances of one position. `available` is what can be deployed right now."""

    free: Decimal = ZERO
    reserved: Decimal = ZERO
    in_transit: Decimal = ZERO

    @property
    def available(self) -> Decimal:
        return self.free - self.reserved

    @property
    def total(self) -> Decimal:
        return self.free + self.in_transit

    def reserve(self, amount: Decimal) -> Balance:
        if amount < 0 or amount > self.available:
            raise ValueError("reserve exceeds available balance")
        return Balance(self.free, self.reserved + amount, self.in_transit)

    def debit(self, amount: Decimal, *, from_reserved: bool = False) -> Balance:
        if amount < 0:
            raise ValueError("negative debit")
        if from_reserved:
            if amount > self.reserved:
                raise ValueError("debit exceeds reserved")
            return Balance(self.free - amount, self.reserved - amount, self.in_transit)
        if amount > self.available:
            raise ValueError("debit exceeds available")
        return Balance(self.free - amount, self.reserved, self.in_transit)

    def send(self, amount: Decimal) -> Balance:
        """Money leaves `free` and is tracked as in transit until settled elsewhere."""
        if amount < 0 or amount > self.available:
            raise ValueError("send exceeds available")
        return Balance(self.free - amount, self.reserved, self.in_transit + amount)

    def settle(self, amount: Decimal) -> Balance:
        if amount < 0 or amount > self.in_transit:
            raise ValueError("settle exceeds in_transit")
        return Balance(self.free + amount, self.reserved, self.in_transit - amount)


@dataclass(frozen=True, slots=True)
class Holding:
    position: Position
    balance: Balance = field(default_factory=Balance)
