class V3Error(Exception):
    """Base error for the V3 experimental Monte Carlo harness."""


class GovernanceBlock(V3Error):
    """Raised when required governed evidence or an approved configuration is missing."""


class InputValidationError(V3Error):
    """Raised when a mounted input fails deterministic validation."""
