from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from ..config import PublicCrowdingConfig


@dataclass(frozen=True)
class PublicMoneyRaw:
    key: str
    season_money: Decimal
    recent_money: Decimal


@dataclass(frozen=True)
class PublicMoneyDerived:
    key: str
    recent_money_ratio: float | None
    season_percentile: float
    recent_percentile: float
    recent_ratio_percentile: float | None
    crowding_score: float | None


def recent_money_ratio(season_money: Decimal, recent_money: Decimal) -> float | None:
    if season_money < 0 or recent_money < 0:
        raise ValueError("money values must be nonnegative")
    if season_money == 0:
        return None
    return float(recent_money / season_money)


def empirical_percentiles(values: list[float]) -> list[float]:
    """Return deterministic midrank percentiles in [0, 1]."""
    if not values:
        return []
    n = len(values)
    if n == 1:
        return [0.5]
    result: list[float] = []
    for value in values:
        less = sum(v < value for v in values)
        equal = sum(v == value for v in values)
        midrank_zero_based = less + (equal - 1) / 2
        result.append(midrank_zero_based / (n - 1))
    return result


def crowding_score(
    season_percentile: float,
    recent_percentile: float,
    recent_ratio_percentile: float,
    config: PublicCrowdingConfig,
) -> float:
    for value in (season_percentile, recent_percentile, recent_ratio_percentile):
        if not 0 <= value <= 1:
            raise ValueError("percentiles must be in [0, 1]")
    return (
        config.season_weight * season_percentile
        + config.recent_weight * recent_percentile
        + config.concentration_weight * recent_ratio_percentile
    )


def derive_public_money(
    rows: Iterable[PublicMoneyRaw], config: PublicCrowdingConfig
) -> list[PublicMoneyDerived]:
    rows = list(rows)
    season = [float(r.season_money) for r in rows]
    recent = [float(r.recent_money) for r in rows]
    ratios = [recent_money_ratio(r.season_money, r.recent_money) for r in rows]
    season_pct = empirical_percentiles(season)
    recent_pct = empirical_percentiles(recent)

    ratio_values = [r for r in ratios if r is not None]
    ratio_pcts_nonnull = empirical_percentiles(ratio_values)
    ratio_pct_iter = iter(ratio_pcts_nonnull)

    derived: list[PublicMoneyDerived] = []
    for row, ratio, s_pct, r_pct in zip(rows, ratios, season_pct, recent_pct, strict=True):
        ratio_pct = next(ratio_pct_iter) if ratio is not None else None
        score = (
            crowding_score(s_pct, r_pct, ratio_pct, config)
            if ratio_pct is not None
            else None
        )
        derived.append(
            PublicMoneyDerived(
                key=row.key,
                recent_money_ratio=ratio,
                season_percentile=s_pct,
                recent_percentile=r_pct,
                recent_ratio_percentile=ratio_pct,
                crowding_score=score,
            )
        )
    return derived


def relative_crowding(team_a: float, team_b: float) -> float:
    for value in (team_a, team_b):
        if not 0 <= value <= 1:
            raise ValueError("crowding score must be in [0, 1]")
    return team_a - team_b
