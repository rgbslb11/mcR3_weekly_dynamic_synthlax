"""A8/ECL champion ordering circularity detection for Dynamic Weekly MC V3.

Two governed rules interlock:

``R-CCG-08``
    Atlantic-8 and ECL champions are decided by conference play W1–W14 on best
    conference win%. There is no title game; the award is standings-only.

``TB-ECL/A8``
    When that standings race ties, the chain is TB-1 head-to-head, TB-2 mini
    round-robin, then **TB-3 the FINAL committee ranking** — explicitly the
    final board, not the pre-Championship-Saturday board used by R-CCG-01.

The final committee board, in this implementation, ranks on a key that includes
``conference_champion`` (see :mod:`committee`), and CG-8 routes the G5 auto-bid
through champion status as well. So a tied A8/ECL race needs the final board,
while the final board needs champion flags — including the very flag still being
resolved. That is a genuine cycle, not an artifact of implementation order.

The cycle only *binds* when an A8 or ECL standings race is actually tied through
TB-1 and TB-2. Unbroken races resolve without ever consulting the board. This
module therefore distinguishes "cycle is structurally present" from "cycle binds
on this path", and fails closed only on the latter — a run must not be blocked by
a hazard that never materializes, nor allowed to proceed through one that does.

Breaking the cycle requires a governed ruling. This module does not choose one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .errors import GovernanceBlock

STANDINGS_ONLY_CONFERENCES = ("Atlantic-8", "ECL")

# Candidate resolutions, recorded for the decision packet. None is implemented.
RESOLUTION_OPTIONS = (
    "PRELIMINARY_BOARD_BEFORE_CHAMPION_FLAG",
    "CHAMPION_RESOLUTION_BEFORE_FINAL_BOARD_WITH_CHAMPION_BLIND_TIE_BOARD",
    "EXPLICIT_SOURCE_SUPPORTED_ALTERNATIVE",
)


@dataclass(frozen=True)
class OrderingDependency:
    consumer: str
    depends_on: str
    authority: str
    note: str


#: The governed dependency edges that together form the cycle.
DEPENDENCY_GRAPH: tuple[OrderingDependency, ...] = (
    OrderingDependency(
        consumer="A8_ECL_CHAMPION",
        depends_on="FINAL_COMMITTEE_BOARD",
        authority="TB-ECL/A8",
        note="TB-3 resolves a tied standings race using the FINAL committee ranking.",
    ),
    OrderingDependency(
        consumer="FINAL_COMMITTEE_BOARD",
        depends_on="CONFERENCE_CHAMPION_FLAG",
        authority="committee.rank_committee_results_first",
        note="Board ordering key includes conference_champion.",
    ),
    OrderingDependency(
        consumer="CONFERENCE_CHAMPION_FLAG",
        depends_on="A8_ECL_CHAMPION",
        authority="R-CCG-08",
        note="A8/ECL champions are themselves conference champions carrying the flag.",
    ),
)


def cycle_path() -> list[str]:
    """Return the ordering cycle as an explicit node path."""
    path = [DEPENDENCY_GRAPH[0].consumer]
    for edge in DEPENDENCY_GRAPH:
        path.append(edge.depends_on)
    return path


@dataclass(frozen=True)
class TiedStandingsRace:
    conference: str
    teams: tuple[str, ...]
    resolved_by_head_to_head: bool = False
    resolved_by_mini_round_robin: bool = False

    @property
    def requires_final_board(self) -> bool:
        """True when TB-1 and TB-2 both fail and TB-3 must be consulted."""
        return not (self.resolved_by_head_to_head or self.resolved_by_mini_round_robin)


@dataclass(frozen=True)
class OrderingDiagnosis:
    structurally_circular: bool
    binding_races: tuple[TiedStandingsRace, ...] = field(default=())

    @property
    def binds(self) -> bool:
        return self.structurally_circular and bool(self.binding_races)

    def as_dict(self) -> dict[str, object]:
        return {
            "structurally_circular": self.structurally_circular,
            "cycle_path": cycle_path(),
            "binds_on_this_path": self.binds,
            "binding_races": [
                {"conference": r.conference, "teams": list(r.teams)} for r in self.binding_races
            ],
            "resolution_options": list(RESOLUTION_OPTIONS),
            "resolution_ruling_present": False,
        }


def diagnose_ordering(races: list[TiedStandingsRace] | None = None) -> OrderingDiagnosis:
    """Diagnose whether the A8/ECL ordering cycle binds for the given races."""
    races = races or []
    binding = tuple(
        r
        for r in races
        if r.conference in STANDINGS_ONLY_CONFERENCES and r.requires_final_board and len(r.teams) > 1
    )
    return OrderingDiagnosis(structurally_circular=True, binding_races=binding)


def require_resolved_ordering(
    races: list[TiedStandingsRace] | None = None, *, ordering_ruling: str | None = None
) -> OrderingDiagnosis:
    """Fail closed when the A8/ECL ordering cycle binds without a governed ruling.

    ``ordering_ruling`` must name one of :data:`RESOLUTION_OPTIONS`. No default is
    supplied: an unset ruling is the blocked state, not an invitation to pick.
    """
    diagnosis = diagnose_ordering(races)
    if not diagnosis.binds:
        return diagnosis
    if ordering_ruling is None:
        raise GovernanceBlock(
            "A8/ECL final-board tiebreak ordering is circular and binds on this path: "
            f"{' -> '.join(cycle_path())}. Tied standings races requiring TB-3: "
            + ", ".join(f"{r.conference}({'/'.join(r.teams)})" for r in diagnosis.binding_races)
            + ". No governed ordering ruling is present; refusing to break the cycle by inference."
        )
    if ordering_ruling not in RESOLUTION_OPTIONS:
        raise GovernanceBlock(
            f"Unknown A8/ECL ordering ruling {ordering_ruling!r}; "
            f"expected one of {sorted(RESOLUTION_OPTIONS)}."
        )
    return diagnosis
