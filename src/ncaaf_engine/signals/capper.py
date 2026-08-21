from __future__ import annotations

from dataclasses import dataclass

from ..enums import Direction, SkillTier


@dataclass(frozen=True)
class WeightedPick:
    handle: str
    direction: Direction
    weight: float
    skill_tier: SkillTier


def sharp_consensus(picks: list[WeightedPick]) -> float | None:
    eligible = [
        p
        for p in picks
        if p.weight > 0 and p.skill_tier != SkillTier.NO_POSITIVE_WEIGHT
    ]
    if not eligible:
        return None
    numerator = sum(p.weight * (1 if p.direction == Direction.YES else -1) for p in eligible)
    denominator = sum(p.weight for p in eligible)
    return numerator / denominator
