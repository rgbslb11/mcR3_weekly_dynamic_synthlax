"""SYTHALAX_DYNAMIC_WEEKLY_MC_V3_EXPERIMENTAL.

V2.1 remains the static-rating control. V3 is fail-closed until all experimental
rerating coefficients/policies and governed data dependencies are explicitly supplied.
"""

from .config import V3Config
from .engine import DynamicWeeklyMCV3

__all__ = ["DynamicWeeklyMCV3", "V3Config"]
