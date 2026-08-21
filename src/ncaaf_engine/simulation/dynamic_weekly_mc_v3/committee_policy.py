"""Weekly committee product and the general committee ranking tiebreak.

Ruling R2-COMMITTEE-TB replaces a framing, not just a value. The old
configuration field ``committee_tiebreak_strength_source`` asked which *hidden
strength number* breaks a committee tie — ``PRESEASON_STRENGTH`` or
``FINAL_WEEKLY_FOOTBALL_STRENGTH``. Both answers presume the board ranks on a
number it never publishes. The ruling retires the question and puts a
deterministic chain in its place::

    COMMITTEE-TB1  head-to-head
    COMMITTEE-TB2  performance against common opponents (ruling R2-COMMON-OPP)
    COMMITTEE-TB3  strength of schedule (ruling R2-SOS)
    COMMITTEE-TB4  previous week's committee board

This chain is namespaced separately from the CCG *participant* tiebreak in
:mod:`ccg`. They are different chains resolving different questions and must
never be substituted for one another.

What may be published
---------------------
From Nov 1 through the board following the seven CCGs: a Top 25 ordering and the
current playoff bracket. Never a raw strength number, committee score, or hidden
numeric power value. :func:`weekly_committee_product` enforces that by
construction — it has no field to leak one through.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from .sos import criterion_resolves
from .errors import GovernanceBlock, InputValidationError
from .rulings import R2_COMMITTEE_TIEBREAK

#: The retired framing. Accepted only as ``None``; any value is refused.
RETIRED_STRENGTH_SOURCE_VALUES = ("PRESEASON_STRENGTH", "FINAL_WEEKLY_FOOTBALL_STRENGTH")

#: The structured policy token that replaces it in the V3 configuration.
COMMITTEE_TIEBREAK_POLICY = "DETERMINISTIC_COMMITTEE_TIEBREAK_CHAIN_R2"

COMMITTEE_TIEBREAK_CHAIN = (
    "COMMITTEE-TB1_HEAD_TO_HEAD",
    "COMMITTEE-TB2_COMMON_OPPONENT_PERFORMANCE",
    "COMMITTEE-TB3_STRENGTH_OF_SCHEDULE",
    "COMMITTEE-TB4_PREVIOUS_WEEK_BOARD",
)

#: FACT — Playoff Calendar: conference championships Sat Dec 5, 2026.
WEEKLY_PRODUCT_FIRST_PUBLICATION = "2026-11-01"
WEEKLY_PRODUCT_TOP_N = 25

#: Fields a published weekly product may never carry.
FORBIDDEN_PUBLICATION_FIELDS = (
    "strength",
    "strength_points",
    "committee_score",
    "power",
    "power_index",
    "rating",
    "elo",
    "sos",
    "score",
)

FIRST_BOARD_TB4_BLOCKER = "governance.COMMITTEE_TB4_FIRST_NOVEMBER_BOARD_FALLBACK_AUTHORITY_ABSENT"


def reject_retired_strength_source(value: str | None) -> None:
    """Refuse any attempt to repopulate the retired obsolete concept."""
    if value is None:
        return
    raise GovernanceBlock(
        f"committee_tiebreak_strength_source={value!r} is a retired concept. Ruling "
        f"{R2_COMMITTEE_TIEBREAK.convergence_id} replaced "
        f"{RETIRED_STRENGTH_SOURCE_VALUES} with the structured chain "
        f"{COMMITTEE_TIEBREAK_POLICY}. Leave the obsolete field null."
    )


def require_committee_tiebreak_policy(policy: str | None) -> str:
    """Fail closed unless the structured deterministic chain is configured."""
    if not policy:
        raise GovernanceBlock(
            "V3 committee tiebreak policy is not configured. Ruling "
            f"{R2_COMMITTEE_TIEBREAK.convergence_id} sets it to {COMMITTEE_TIEBREAK_POLICY}."
        )
    if policy in RETIRED_STRENGTH_SOURCE_VALUES:
        raise GovernanceBlock(
            f"{policy!r} is a retired committee tiebreak framing, not a policy. "
            f"Use {COMMITTEE_TIEBREAK_POLICY}."
        )
    if policy != COMMITTEE_TIEBREAK_POLICY:
        raise GovernanceBlock(
            f"Unknown committee tiebreak policy {policy!r}; expected {COMMITTEE_TIEBREAK_POLICY}."
        )
    return policy


@dataclass(frozen=True)
class WeeklyCommitteeProduct:
    """What the committee publishes. Deliberately carries no numbers."""

    as_of_week: int
    published_on: str
    top_25: tuple[str, ...]
    bracket: tuple[tuple[str, str | tuple[str, str]], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "as_of_week": self.as_of_week,
            "published_on": self.published_on,
            "top_25": list(self.top_25),
            "bracket": [[slot, value if isinstance(value, str) else list(value)]
                        for slot, value in self.bracket],
        }


def weekly_committee_product(
    *,
    as_of_week: int,
    published_on: str,
    ordering: Sequence[str],
    bracket: dict[str, object],
) -> WeeklyCommitteeProduct:
    """Build the publishable weekly product, refusing any numeric leak."""
    if published_on < WEEKLY_PRODUCT_FIRST_PUBLICATION:
        raise GovernanceBlock(
            f"Weekly committee product begins {WEEKLY_PRODUCT_FIRST_PUBLICATION}; "
            f"{published_on} is earlier."
        )
    if len(ordering) < WEEKLY_PRODUCT_TOP_N:
        raise InputValidationError(
            f"Committee ordering has {len(ordering)} teams; a Top {WEEKLY_PRODUCT_TOP_N} "
            "cannot be published from it"
        )
    for slot, value in bracket.items():
        if not isinstance(value, (str, tuple, list)):
            raise GovernanceBlock(
                f"Bracket slot {slot!r} carries a non-participant value {value!r}; the weekly "
                "product publishes teams and pairings only."
            )
    return WeeklyCommitteeProduct(
        as_of_week=as_of_week,
        published_on=published_on,
        top_25=tuple(ordering[:WEEKLY_PRODUCT_TOP_N]),
        bracket=tuple(
            (slot, tuple(value) if isinstance(value, (tuple, list)) else value)
            for slot, value in sorted(bracket.items())
        ),
    )


def assert_no_hidden_numbers(payload: dict[str, object]) -> None:
    """Refuse a payload that carries a raw strength/score/power value."""
    offending = sorted(
        k for k in payload
        if any(bad in k.lower() for bad in FORBIDDEN_PUBLICATION_FIELDS)
    )
    if offending:
        raise GovernanceBlock(
            f"Weekly committee publication may not expose raw numeric fields: {offending}. "
            f"Ruling {R2_COMMITTEE_TIEBREAK.convergence_id} permits a Top 25 ordering and the "
            "current bracket only."
        )


@dataclass(frozen=True)
class CommitteeTiebreakInputs:
    """Everything the chain may consult, and nothing else."""

    head_to_head: Callable[[str, str], str | None]
    #: May return ``None`` for either side when a required governed component is
    #: UNAVAILABLE under ruling R3-SOS-OWP-OOWP-SEMANTICS.
    common_opponent_score: Callable[[str, str], tuple[float | None, float | None]]
    strength_of_schedule: Callable[[str], float | None]
    previous_board: tuple[str, ...] | None


def break_committee_tie(
    team_a: str,
    team_b: str,
    inputs: CommitteeTiebreakInputs,
    *,
    is_first_november_board: bool = False,
) -> tuple[str, str]:
    """Return ``(winner, step)`` for one pairwise committee tie.

    A stage that cannot be evaluated because a required governed component is
    UNAVAILABLE does not resolve the tie — processing advances to the next
    already-governed stage. That is ruling R3-SOS-OWP-OOWP-SEMANTICS, and it is
    deliberately different from the two sides being equal, which also advances.

    TB4 consults the previous week's board. On the very first November board no
    previous board exists. The repository contains no authority for what stands
    in — Board I-K is the Board of Record but nothing designates it as the TB4
    fallback — so that one edge case, and only that one, fails closed.
    """
    winner = inputs.head_to_head(team_a, team_b)
    if winner is not None:
        if winner not in (team_a, team_b):
            raise InputValidationError(
                f"Head-to-head returned {winner!r}, which is neither {team_a} nor {team_b}"
            )
        return winner, COMMITTEE_TIEBREAK_CHAIN[0]

    # A criterion whose required governed component is UNAVAILABLE does not
    # resolve the tie: ruling R3-SOS-OWP-OOWP-SEMANTICS sends processing on to
    # the next already-governed stage rather than letting an absent value decide.
    score_a, score_b = inputs.common_opponent_score(team_a, team_b)
    if criterion_resolves(score_a, score_b):
        return (team_a if score_a > score_b else team_b), COMMITTEE_TIEBREAK_CHAIN[1]

    sos_a, sos_b = inputs.strength_of_schedule(team_a), inputs.strength_of_schedule(team_b)
    if criterion_resolves(sos_a, sos_b):
        return (team_a if sos_a > sos_b else team_b), COMMITTEE_TIEBREAK_CHAIN[2]

    if inputs.previous_board is None:
        if is_first_november_board:
            raise GovernanceBlock(
                f"{FIRST_BOARD_TB4_BLOCKER}: COMMITTEE-TB4 requires the previous week's "
                f"board and {team_a}/{team_b} are tied through TB1-TB3 on the first November "
                "board, where no previous board exists. No governed authority designates a "
                "fallback. Issue one; do not substitute another board by inference."
            )
        raise GovernanceBlock(
            f"COMMITTEE-TB4 requires the previous week's committee board to separate "
            f"{team_a} and {team_b}, and none was supplied."
        )
    order = {t: i for i, t in enumerate(inputs.previous_board)}
    missing = [t for t in (team_a, team_b) if t not in order]
    if missing:
        raise GovernanceBlock(
            f"COMMITTEE-TB4 cannot rank {missing} — absent from the previous week's board."
        )
    return (team_a if order[team_a] < order[team_b] else team_b), COMMITTEE_TIEBREAK_CHAIN[3]


def policy_as_dict() -> dict[str, object]:
    return {
        "ruling": R2_COMMITTEE_TIEBREAK.convergence_id,
        "policy": COMMITTEE_TIEBREAK_POLICY,
        "chain": list(COMMITTEE_TIEBREAK_CHAIN),
        "retired_framing": list(RETIRED_STRENGTH_SOURCE_VALUES),
        "publication_window_opens": WEEKLY_PRODUCT_FIRST_PUBLICATION,
        "publishes": ["top_25_ordering", "current_playoff_bracket"],
        "never_publishes": list(FORBIDDEN_PUBLICATION_FIELDS),
        "first_november_board_tb4_fallback": None,
        "first_november_board_tb4_blocker": FIRST_BOARD_TB4_BLOCKER,
    }
