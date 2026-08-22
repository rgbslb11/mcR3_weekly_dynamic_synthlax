"""Governed path-count tiers for V3 execution.

V3 was written to accept exactly 10,000 independent paths, which made the
publish configuration the only configuration that could preflight at all. A
development run and an analysis run then had nowhere to go: the only ways to
obtain one were to edit the governed check or to weaken it to ``paths > 0``,
and both make the publish guarantee unenforceable.

This module names the three tiers instead. Each is an exact path count, and
nothing between them is accepted — 9,999 is not a slightly smaller publish run,
it is an ungoverned one, and it is refused with the same firmness as zero.

What a tier selects is the number of independent paths and nothing else. The
draw for a given game on a given path is keyed by semantic coordinates through
:mod:`.rng`, never by iteration order or by how many paths accompany it, so
path 17 of a DEV run is bit-identical to path 17 of a PUBLISH run. Tier
therefore changes how much of the same distribution is drawn, never what the
distribution is: no football mathematics, no rerating mathematics, no
governance, no bracket rule and no canonical parameter reads this module.

Only PUBLISH may be published or frozen. That is not a convention here — it is
:func:`require_publish_freeze_tier`, which a DEV or ANALYSIS run cannot pass,
and it is recorded in the preflight report and the input manifest so a smaller
run cannot be mistaken for a publish result after the fact.
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import GovernanceBlock


@dataclass(frozen=True)
class RunTier:
    """One approved execution tier.

    Frozen, and every instance is a module constant. A tier is derived from a
    configuration's path count on demand rather than stored anywhere mutable,
    so no run can leave a tier behind for the next one to inherit.
    """

    name: str
    paths: int
    publish_freeze: bool
    purpose: str

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "paths": self.paths,
            "publish_freeze": self.publish_freeze,
            "purpose": self.purpose,
        }


#: Smoke and development. Cheap enough to run often, and never publishable.
DEV = RunTier(
    name="DEV",
    paths=500,
    publish_freeze=False,
    purpose="Development and smoke execution. Never a publishable result.",
)

#: Interpretation and comparison. Still not a result of record.
ANALYSIS = RunTier(
    name="ANALYSIS",
    paths=2_000,
    publish_freeze=False,
    purpose="Analysis execution. Informative only; never a publishable result.",
)

#: The only tier that may be published or frozen.
PUBLISH = RunTier(
    name="PUBLISH",
    paths=10_000,
    publish_freeze=True,
    purpose="The governed publish and freeze tier. The only result of record.",
)

#: Every approved tier, in ascending path order.
GOVERNED_TIERS: tuple[RunTier, ...] = (DEV, ANALYSIS, PUBLISH)

#: The exact path counts V3 accepts. Membership is the whole test — there is no
#: range, minimum or rounding anywhere in this module.
APPROVED_PATH_COUNTS: tuple[int, ...] = tuple(t.paths for t in GOVERNED_TIERS)

_BY_PATHS: dict[int, RunTier] = {t.paths: t for t in GOVERNED_TIERS}


def tier_for_paths(paths: int) -> RunTier:
    """Return the governed tier for ``paths``, or refuse.

    Refuses anything that is not one of the three approved counts, and says
    which counts exist rather than only that this one is wrong — a run
    configured for 9,999 needs to know it must choose, not that it was close.
    """
    try:
        return _BY_PATHS[paths]
    except (KeyError, TypeError):
        approved = ", ".join(f"{t.paths:,} ({t.name})" for t in GOVERNED_TIERS)
        raise ValueError(
            f"{paths!r} is not a governed V3 path count. V3 executes at exactly "
            f"one of: {approved}."
        ) from None


def is_publish_freeze_tier(paths: int) -> bool:
    """Whether ``paths`` is the publish/freeze tier. Refuses ungoverned counts."""
    return tier_for_paths(paths).publish_freeze


def require_publish_freeze_tier(paths: int) -> RunTier:
    """Assert that ``paths`` may be published or frozen, or block.

    A :class:`GovernanceBlock` rather than a :class:`ValueError`: 500 paths is a
    legitimate configuration that is not entitled to this claim, which is a
    governance refusal, not a malformed input.
    """
    tier = tier_for_paths(paths)
    if not tier.publish_freeze:
        raise GovernanceBlock(
            f"{tier.name} ({tier.paths:,} paths) may not be published or frozen. "
            f"Publish and freeze require the {PUBLISH.name} tier "
            f"({PUBLISH.paths:,} paths)."
        )
    return tier


def as_dict() -> dict[str, object]:
    """The tier register, for manifests and reports."""
    return {
        "governed_tiers": [t.as_dict() for t in GOVERNED_TIERS],
        "approved_path_counts": list(APPROVED_PATH_COUNTS),
        "publish_freeze_tier": PUBLISH.name,
    }
