from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class LedgerLine:
    account_id: str
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")

    def __post_init__(self):
        if self.debit < 0 or self.credit < 0:
            raise ValueError("ledger debit/credit cannot be negative")
        if self.debit and self.credit:
            raise ValueError("a ledger line cannot contain both debit and credit")


def validate_double_entry(lines: list[LedgerLine]) -> None:
    if not lines:
        raise ValueError("ledger transaction must contain entries")
    debits = sum((line.debit for line in lines), Decimal("0"))
    credits = sum((line.credit for line in lines), Decimal("0"))
    if debits != credits:
        raise ValueError(f"unbalanced ledger transaction: debits={debits} credits={credits}")
