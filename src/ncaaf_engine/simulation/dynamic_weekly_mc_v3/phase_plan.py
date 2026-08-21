from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SeasonPhase:
    name: str
    weeks: tuple[int, ...]
    simulate_games: bool
    rerate_after_phase_week: bool
    committee_selection: bool = False
    strength_frozen: bool = False


V3_INITIAL_PHASE_PLAN = (
    SeasonPhase("PRESELECTION_REGULAR", tuple(range(1, 15)), True, True),
    SeasonPhase("CONFERENCE_CHAMPIONSHIPS", (15,), True, True),
    SeasonPhase("CFP_SELECTION", (), False, False, committee_selection=True, strength_frozen=True),
    SeasonPhase("POST_SELECTION_ARMY_NAVY", (16,), True, False, strength_frozen=True),
    SeasonPhase("CFP_POSTSEASON", (), True, False, strength_frozen=True),
)


def validate_phase_plan() -> None:
    assert V3_INITIAL_PHASE_PLAN[0].weeks == tuple(range(1, 15))
    assert V3_INITIAL_PHASE_PLAN[1].weeks == (15,)
    assert V3_INITIAL_PHASE_PLAN[3].weeks == (16,)
    assert V3_INITIAL_PHASE_PLAN[3].rerate_after_phase_week is False
    assert V3_INITIAL_PHASE_PLAN[4].strength_frozen is True
