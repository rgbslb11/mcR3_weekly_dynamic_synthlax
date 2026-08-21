"""The one exact linear solver the witness models share.

Both governed witnesses reduce to a small dense linear system, and both are
deliberately solved *exactly* rather than iterated to a tolerance. The reason is
the same in each case and is worth stating once: an iteration that stops at a
max-iteration ceiling returns its last oscillation as though it were a solution,
and a plausible-but-wrong ordering is precisely the failure a witness exists to
catch. Keeping one solver means the two witnesses cannot drift into disagreeing
about arithmetic while appearing to disagree about football.

The routine is Gauss-Jordan elimination with partial pivoting, in fixed order,
so the result is deterministic to the bit for a given input ordering.
"""

from __future__ import annotations

from .errors import InputValidationError

#: Below this a pivot is treated as zero rather than divided by.
DEFAULT_PIVOT_EPSILON = 1e-12


def solve_exact(
    matrix: list[list[float]],
    rhs: list[float],
    *,
    singular_message: str,
    pivot_epsilon: float = DEFAULT_PIVOT_EPSILON,
) -> list[float]:
    """Solve ``matrix @ x = rhs`` exactly, or refuse.

    ``singular_message`` is the caller's own account of what a singular system
    means for its model — the two witnesses reach singularity for different
    reasons and a shared generic message would hide that.
    """
    n = len(rhs)
    aug = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < pivot_epsilon:
            raise InputValidationError(singular_message)
        if pivot != col:
            aug[col], aug[pivot] = aug[pivot], aug[col]
        scale = aug[col][col]
        aug[col] = [v / scale for v in aug[col]]
        for row in range(n):
            if row == col:
                continue
            factor = aug[row][col]
            if factor:
                aug[row] = [v - factor * w for v, w in zip(aug[row], aug[col])]
    return [aug[i][n] for i in range(n)]
