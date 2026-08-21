from decimal import Decimal

import pytest

from ncaaf_engine.ledger import LedgerLine, validate_double_entry


def test_balanced_ledger_passes():
    validate_double_entry([
        LedgerLine("participant", debit=Decimal("10")),
        LedgerLine("market", credit=Decimal("10")),
    ])


def test_unbalanced_ledger_rejected():
    with pytest.raises(ValueError, match="unbalanced"):
        validate_double_entry([
            LedgerLine("participant", debit=Decimal("10")),
            LedgerLine("market", credit=Decimal("9")),
        ])
