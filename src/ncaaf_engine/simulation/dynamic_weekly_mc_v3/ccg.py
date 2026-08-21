"""Conference championship games: count, participants, and the CCG tiebreak chain.

Ruling R2-CCG-SEVEN fixes seven CCGs and how their seats are filled. Two things
in it are easy to get wrong and are therefore enforced rather than assumed:

*Conference* win percentage, never overall
    R-CCG-01 and the ACC's own published policy both select on conference wins.
    Substituting overall win percentage would quietly re-rank every race.

A chain that fills *both* seats
    A tie can sit across the first seat, the second seat, or both. The chain is
    applied at whatever standings band is contested, as many times as needed,
    rather than once at the top.

The chain namespace is distinct from the general committee ranking tiebreak in
:mod:`committee_policy`. Same word, different rules, different question::

    CCG-TB1  head-to-head
    CCG-TB2  mini round-robin among the tied teams
    CCG-TB3  last committee board published before Championship Saturday

The AAC is a carve-out: R-CCG-05 makes its participants the American Division
winner versus the Athletic Division winner. Within each division the same
conference win percentage and the same chain apply.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

from .errors import GovernanceBlock, InputValidationError
from .rulings import R2_SEVEN_CCGS

#: FACT — seven W15 CCG template rows in schedule v5; Certification ccg_count
#: reads "7 — SEC, Big Ten, Big 12, ACC, Pac-12, Mountain West, American.
#: NONE for Atlantic-8, ECL, Independent."
CCG_CONFERENCES: tuple[str, ...] = (
    "ACC",
    "American",
    "Big 12",
    "Big Ten",
    "Mountain West",
    "Pac-12",
    "SEC",
)
EXPECTED_CCG_COUNT = 7

#: Standings-only conferences. R-CCG-08: champion decided on conference play.
NO_CCG_CONFERENCES: tuple[str, ...] = ("Atlantic-8", "ECL")

#: The AAC division carve-out (R-CCG-05).
AAC_CONFERENCE = "American"
AAC_DIVISIONS: tuple[str, ...] = ("American", "Athletic")

CCG_TIEBREAK_CHAIN = (
    "CCG-TB1_HEAD_TO_HEAD",
    "CCG-TB2_MINI_ROUND_ROBIN",
    "CCG-TB3_LAST_BOARD_BEFORE_CHAMPIONSHIP_SATURDAY",
)


@dataclass(frozen=True)
class ConferenceRecord:
    """A team's conference-play record. Overall record is deliberately absent."""

    schedule_id: str
    conference_wins: int
    conference_losses: int
    division: str | None = None

    @property
    def conference_win_pct(self) -> float:
        played = self.conference_wins + self.conference_losses
        return self.conference_wins / played if played else 0.0


@dataclass(frozen=True)
class CcgTiebreakInputs:
    head_to_head: Callable[[str, str], str | None]
    mini_round_robin: Callable[[Sequence[str]], Sequence[str]]
    #: The last committee board published before Championship Saturday.
    last_board_before_championship_saturday: tuple[str, ...] | None


@dataclass(frozen=True)
class CcgSelection:
    conference: str
    seat_1: str
    seat_2: str
    steps: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "ruling": R2_SEVEN_CCGS.convergence_id,
            "conference": self.conference,
            "participants": [self.seat_1, self.seat_2],
            "tiebreak_steps": list(self.steps),
        }


def verify_seven_ccgs(schedule: Sequence) -> dict[str, object]:
    """Confirm the mounted schedule carries exactly the seven governed CCGs."""
    ccg_rows = [g for g in schedule if g.game_type == "CCG"]
    if len(ccg_rows) != EXPECTED_CCG_COUNT:
        raise InputValidationError(
            f"Schedule carries {len(ccg_rows)} CCG rows, expected {EXPECTED_CCG_COUNT}"
        )
    conferences = sorted({str(g.home_conf) for g in ccg_rows})
    if tuple(conferences) != CCG_CONFERENCES:
        raise InputValidationError(
            f"CCG conferences {conferences} do not match the governed set {list(CCG_CONFERENCES)}"
        )
    forbidden = sorted(set(conferences) & set(NO_CCG_CONFERENCES))
    if forbidden:
        raise InputValidationError(
            f"{forbidden} play no conference championship game (R-CCG-08) but carry CCG rows"
        )
    return {
        "ruling": R2_SEVEN_CCGS.convergence_id,
        "ccg_count": len(ccg_rows),
        "conferences": conferences,
        "no_ccg_conferences": list(NO_CCG_CONFERENCES),
        "game_ids": sorted(g.game_id for g in ccg_rows),
    }


def _band(records: Sequence[ConferenceRecord], exclude: set[str]) -> list[ConferenceRecord]:
    """The tied band with the best conference win percentage, minus taken seats."""
    pool = [r for r in records if r.schedule_id not in exclude]
    if not pool:
        raise GovernanceBlock("No remaining teams to fill a CCG seat")
    best = max(r.conference_win_pct for r in pool)
    return sorted(
        (r for r in pool if r.conference_win_pct == best), key=lambda r: r.schedule_id
    )


def _resolve_band(
    band: list[ConferenceRecord], inputs: CcgTiebreakInputs, label: str
) -> tuple[str, str]:
    """Pick one team out of a tied band via CCG-TB1 -> TB2 -> TB3."""
    if len(band) == 1:
        return band[0].schedule_id, "NO_TIE"

    ids = [r.schedule_id for r in band]

    if len(ids) == 2:
        winner = inputs.head_to_head(ids[0], ids[1])
        if winner is not None:
            if winner not in ids:
                raise InputValidationError(f"Head-to-head returned {winner!r}, not in {ids}")
            return winner, CCG_TIEBREAK_CHAIN[0]

    survivors = list(inputs.mini_round_robin(ids))
    unknown = [t for t in survivors if t not in ids]
    if unknown:
        raise InputValidationError(f"Mini round-robin returned teams outside the band: {unknown}")
    if len(survivors) == 1:
        return survivors[0], CCG_TIEBREAK_CHAIN[1]
    if not survivors:
        survivors = ids

    board = inputs.last_board_before_championship_saturday
    if board is None:
        raise GovernanceBlock(
            f"CCG-TB3 for {label} requires the last committee board published before "
            "Championship Saturday, and none was supplied. Refusing to fill a CCG seat "
            "by inference."
        )
    order = {t: i for i, t in enumerate(board)}
    missing = sorted(t for t in survivors if t not in order)
    if missing:
        raise GovernanceBlock(
            f"CCG-TB3 for {label} cannot rank {missing} — absent from the pre-Championship "
            "Saturday board."
        )
    return min(survivors, key=lambda t: order[t]), CCG_TIEBREAK_CHAIN[2]


def select_ccg_participants(
    conference: str,
    records: Sequence[ConferenceRecord],
    inputs: CcgTiebreakInputs,
) -> CcgSelection:
    """Fill both CCG seats for a non-AAC conference on conference win percentage."""
    if conference == AAC_CONFERENCE:
        raise GovernanceBlock(
            "The AAC is a division carve-out under R-CCG-05; use select_aac_ccg_participants."
        )
    if conference not in CCG_CONFERENCES:
        if conference in NO_CCG_CONFERENCES:
            raise GovernanceBlock(
                f"{conference} plays no conference championship game (R-CCG-08)."
            )
        raise GovernanceBlock(f"{conference} is not one of the seven CCG conferences.")
    if len(records) < 2:
        raise InputValidationError(f"{conference} needs at least two teams to fill a CCG")

    steps: list[str] = []
    taken: set[str] = set()

    seat_1, step_1 = _resolve_band(_band(records, taken), inputs, f"{conference} seat 1")
    steps.append(f"seat_1:{step_1}")
    taken.add(seat_1)

    seat_2, step_2 = _resolve_band(_band(records, taken), inputs, f"{conference} seat 2")
    steps.append(f"seat_2:{step_2}")

    return CcgSelection(conference=conference, seat_1=seat_1, seat_2=seat_2, steps=tuple(steps))


def select_aac_ccg_participants(
    records: Sequence[ConferenceRecord],
    inputs: CcgTiebreakInputs,
    division_of: Mapping[str, str],
) -> CcgSelection:
    """AAC carve-out: American Division winner versus Athletic Division winner."""
    by_division: dict[str, list[ConferenceRecord]] = {d: [] for d in AAC_DIVISIONS}
    for record in records:
        division = record.division or division_of.get(record.schedule_id)
        if division not in AAC_DIVISIONS:
            raise InputValidationError(
                f"AAC team {record.schedule_id} has no governed division assignment"
            )
        by_division[division].append(record)

    empty = sorted(d for d, rows in by_division.items() if not rows)
    if empty:
        raise InputValidationError(f"AAC divisions with no teams: {empty}")

    winners: list[str] = []
    steps: list[str] = []
    for division in AAC_DIVISIONS:
        winner, step = _resolve_band(
            _band(by_division[division], set()), inputs, f"AAC {division} division"
        )
        winners.append(winner)
        steps.append(f"{division}:{step}")

    return CcgSelection(
        conference=AAC_CONFERENCE, seat_1=winners[0], seat_2=winners[1], steps=tuple(steps)
    )
