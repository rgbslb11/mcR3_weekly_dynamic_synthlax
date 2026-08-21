"""The witness harness — one schedule in, two independent witnesses out.

Ruling ``R2-CAL-OBJECTIVE`` is unusually specific about shape: out-of-sample
Baxter Rating RMSE is the primary criterion, Colley Matrix and SRS are
independent witnesses **reported separately**, and no weighted composite of the
three is authorised. ACC-EXT-12 records that composite — the Body-of-Work Index
— as PROPOSAL ONLY / NOT ADOPTED.

This module is the integration surface for that shape. It exists because the
alternative is worse: without one place to feed both witnesses from a single
governed schedule, each consumer builds its own adapter, and the first time two
adapters disagree about which games qualify, the witnesses appear to disagree
about football when they actually disagree about bookkeeping.

What it does
------------
Takes one :class:`WitnessSchedule`, runs Colley and SRS over it independently,
and reports both alongside **disagreement flags** — where the two orderings
differ, and by how much.

What it refuses to do
---------------------
Combine them. A disagreement flag is a diagnostic that says *look here*; it is
not a score, it carries no weight, and :func:`reject_witness_composite` refuses
any attempt to turn the pair into one number. Nor does the report carry a
primary-criterion value: no calibration observation set is mounted, so
``out_of_sample_baxter_rating_rmse`` stays :data:`BLOCKED_ON_CALIBRATION_DATA`
and a witness report that quietly stood in for it would be the exact inversion
the ruling forbids.

Evidence class
--------------
A schedule carries its own authority. Synthetic fixtures declare ``TEST_FIXTURE``
and every report built from one is stamped ``NOT_GOVERNED_EVIDENCE``;
:func:`require_governed_witness_evidence` refuses to let such a report be cited
as calibration evidence. The stamp travels with the payload rather than living
in a caller's memory of where the numbers came from.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from . import colley as colley_witness
from . import srs as srs_witness
from .calibration import (
    BLOCKED_ON_CALIBRATION_DATA,
    INDEPENDENT_WITNESSES,
    PRIMARY_CALIBRATION_DIRECTION,
    PRIMARY_CALIBRATION_METRIC,
    CandidateRegime,
)
from .errors import GovernanceBlock, InputValidationError
from .rulings import R2_CALIBRATION
from .sos import NON_GOVERNED_AUTHORITIES

#: The contract C2 integrates against. Bump only for a breaking change to the
#: field set below; adding an optional field is not one.
WITNESS_INTERFACE_VERSION = "C3-WITNESS-1"

#: Every top-level key :func:`witness_report` returns, in emission order.
WITNESS_REPORT_FIELDS = (
    "interface_version",
    "ruling",
    "schedule_id",
    "as_of_week",
    "authority",
    "evidence_class",
    "teams",
    "games",
    "regime",
    "primary_criterion",
    "witnesses",
    "disagreement",
    "governance",
)

#: Stamped on a report whose schedule authority is not governance.
EVIDENCE_NOT_GOVERNED = "NOT_GOVERNED_EVIDENCE"
EVIDENCE_GOVERNED = "GOVERNED_SCHEDULE_EVIDENCE"

#: A witness the schedule cannot support. Never 0, 0.0 or an invented ordering.
UNAVAILABLE: None = None

UNAVAILABLE_SRS_PROVENANCE = (
    "UNAVAILABLE — SRS is an opponent-adjusted capped-margin model and this schedule "
    "does not carry a governed margin for every completed game. No margin was inferred "
    "from the win/loss result."
)


@dataclass(frozen=True)
class WitnessGame:
    """One completed game, from ``team``'s point of view.

    ``won`` and ``margin`` are carried separately and checked against each other
    rather than either being derived from the other. Colley needs only the
    result and SRS needs only the margin; deriving one from the other would let
    a bookkeeping error in one witness propagate silently into the other, which
    is the single thing two independent witnesses exist to prevent.
    """

    game_id: str
    team: str
    opponent: str
    won: bool
    #: Points scored minus points allowed, from ``team``'s side. ``None`` means
    #: no governed margin is mounted for this game — it does not mean zero.
    margin: float | None = None

    def __post_init__(self) -> None:
        if not self.game_id:
            raise InputValidationError("Witness game requires a game_id")
        if not self.team or not self.opponent:
            raise InputValidationError(f"Game {self.game_id} names an empty team or opponent")
        if self.team == self.opponent:
            raise InputValidationError(f"Game {self.game_id} has {self.team} playing itself")
        if not isinstance(self.won, bool):
            raise InputValidationError(
                f"Game {self.game_id} result for {self.team} is {self.won!r}; the governed "
                "witnesses take a win or a loss"
            )
        if self.margin is None:
            return
        margin = float(self.margin)
        if margin == 0.0:
            raise InputValidationError(
                f"Game {self.game_id} has margin 0 for {self.team}. A tie has no governed "
                "treatment in either witness; see colley.require_colley_tie_policy."
            )
        if (margin > 0.0) != self.won:
            raise InputValidationError(
                f"Game {self.game_id}: {self.team} is recorded as "
                f"{'winning' if self.won else 'losing'} with margin {margin}. The result and "
                "the margin disagree; neither is authoritative over the other."
            )


@dataclass(frozen=True)
class WitnessSchedule:
    """A governed win/loss schedule, with the authority it was mounted under."""

    schedule_id: str
    authority: str
    games: tuple[WitnessGame, ...]
    as_of_week: int | None = None

    def __post_init__(self) -> None:
        if not self.schedule_id:
            raise InputValidationError("Witness schedule requires a schedule_id")
        if not self.games:
            raise InputValidationError(
                f"Witness schedule {self.schedule_id} carries no completed games"
            )

    @property
    def is_governed_evidence(self) -> bool:
        return self.authority.strip().upper() not in NON_GOVERNED_AUTHORITIES

    @property
    def evidence_class(self) -> str:
        return EVIDENCE_GOVERNED if self.is_governed_evidence else EVIDENCE_NOT_GOVERNED

    @property
    def teams(self) -> list[str]:
        return sorted({t for g in self.games for t in (g.team, g.opponent)})

    @property
    def has_complete_margins(self) -> bool:
        return all(g.margin is not None for g in self.games)


def _paired(schedule: WitnessSchedule) -> list[WitnessGame]:
    """Both sides of every game, from one row per game.

    A schedule records a game once. Both witnesses want it from each side, and
    generating the mirror here — rather than asking every caller to supply it —
    is what makes the two witnesses provably see the same games.
    """
    out: list[WitnessGame] = []
    seen: set[str] = set()
    for game in schedule.games:
        if game.game_id in seen:
            raise InputValidationError(
                f"Schedule {schedule.schedule_id} records game {game.game_id} more than once. "
                "Supply one row per completed game; the opposing side is generated."
            )
        seen.add(game.game_id)
        out.append(game)
        out.append(
            WitnessGame(
                game_id=game.game_id,
                team=game.opponent,
                opponent=game.team,
                won=not game.won,
                margin=None if game.margin is None else -float(game.margin),
            )
        )
    return out


def colley_games(schedule: WitnessSchedule) -> list[colley_witness.ColleyGame]:
    """Adapt a schedule to the Colley witness. Margins are dropped, not used."""
    return [
        colley_witness.ColleyGame(g.game_id, g.team, g.opponent, g.won)
        for g in _paired(schedule)
    ]


def srs_games(schedule: WitnessSchedule) -> list[srs_witness.SrsGame]:
    """Adapt a schedule to the SRS witness. Requires a margin on every game."""
    missing = sorted({g.game_id for g in schedule.games if g.margin is None})
    if missing:
        raise InputValidationError(
            f"SRS needs a governed margin for every completed game; {len(missing)} "
            f"missing, first {missing[:3]}. {UNAVAILABLE_SRS_PROVENANCE}"
        )
    return [
        srs_witness.SrsGame(g.game_id, g.team, g.opponent, float(g.margin))
        for g in _paired(schedule)
    ]


@dataclass(frozen=True)
class OrderingDisagreement:
    """One pair of teams the two witnesses order differently."""

    team_a: str
    team_b: str
    colley_prefers: str
    srs_prefers: str
    colley_gap: float
    srs_gap: float

    def as_dict(self) -> dict[str, object]:
        return {
            "pair": [self.team_a, self.team_b],
            "colley_prefers": self.colley_prefers,
            "srs_prefers": self.srs_prefers,
            "colley_gap": self.colley_gap,
            "srs_gap": self.srs_gap,
        }


def ordering_disagreements(
    colley_ratings: dict[str, float], srs_ratings: dict[str, float]
) -> list[OrderingDisagreement]:
    """Every team pair the two witnesses rank in opposite order.

    Pairwise rather than a single rank-correlation number, and deliberately: a
    correlation coefficient is one more number that invites being weighted into
    something, while a list of pairs says only "these two disagree about these
    teams", which is all a witness is entitled to say.

    Exact ties are not disagreements. Both witnesses break ties on schedule_id
    to make their orderings total, and an artefact of that tiebreak is not
    evidence about football.
    """
    shared = sorted(set(colley_ratings) & set(srs_ratings))
    out: list[OrderingDisagreement] = []
    for i, a in enumerate(shared):
        for b in shared[i + 1 :]:
            colley_gap = colley_ratings[a] - colley_ratings[b]
            srs_gap = srs_ratings[a] - srs_ratings[b]
            if colley_gap == 0.0 or srs_gap == 0.0:
                continue
            if (colley_gap > 0.0) == (srs_gap > 0.0):
                continue
            out.append(
                OrderingDisagreement(
                    team_a=a,
                    team_b=b,
                    colley_prefers=a if colley_gap > 0.0 else b,
                    srs_prefers=a if srs_gap > 0.0 else b,
                    colley_gap=colley_gap,
                    srs_gap=srs_gap,
                )
            )
    return out


def rank_displacements(
    colley_ratings: dict[str, float], srs_ratings: dict[str, float]
) -> dict[str, int]:
    """Per-team ``colley_rank - srs_rank``, over the teams both witnesses rate."""
    shared = set(colley_ratings) & set(srs_ratings)
    colley_rank = {
        t: i
        for i, t in enumerate(
            colley_witness.colley_ordering({t: colley_ratings[t] for t in shared})
        )
    }
    srs_rank = {
        t: i
        for i, t in enumerate(srs_witness.srs_ordering({t: srs_ratings[t] for t in shared}))
    }
    return {t: colley_rank[t] - srs_rank[t] for t in sorted(shared)}


def disagreement_flags(
    colley_ratings: dict[str, float], srs_ratings: dict[str, float] | None
) -> dict[str, object]:
    """The flag block. UNAVAILABLE, never empty-and-quiet, when SRS is missing."""
    if srs_ratings is None:
        return {
            "available": False,
            "reason": UNAVAILABLE_SRS_PROVENANCE,
            "pairs_compared": UNAVAILABLE,
            "pairs_disagreeing": UNAVAILABLE,
            "disagreeing_pairs": UNAVAILABLE,
            "rank_displacement": UNAVAILABLE,
            "max_abs_rank_displacement": UNAVAILABLE,
            "orderings_identical": UNAVAILABLE,
            "is_composite": False,
        }
    shared = sorted(set(colley_ratings) & set(srs_ratings))
    pairs = len(shared) * (len(shared) - 1) // 2
    disagreements = ordering_disagreements(colley_ratings, srs_ratings)
    displacement = rank_displacements(colley_ratings, srs_ratings)
    return {
        "available": True,
        "reason": None,
        "teams_compared": shared,
        "pairs_compared": pairs,
        "pairs_disagreeing": len(disagreements),
        "disagreeing_pairs": [d.as_dict() for d in disagreements],
        "rank_displacement": displacement,
        "max_abs_rank_displacement": max((abs(v) for v in displacement.values()), default=0),
        "orderings_identical": not disagreements
        and all(v == 0 for v in displacement.values()),
        # Said out loud because the temptation to weight these into a score is
        # exactly what ACC-EXT-12 records as NOT ADOPTED.
        "is_composite": False,
        "flags_are_diagnostic_only": True,
    }


def reject_witness_composite(components: Iterable[str]) -> None:
    """Refuse any blend of the primary criterion and the witnesses."""
    colley_witness.reject_witness_composite(components)


def witness_report(
    schedule: WitnessSchedule,
    *,
    regime: CandidateRegime | None = None,
    baxter_rmse: float | None = None,
) -> dict[str, object]:
    """Run both witnesses over one schedule and return the C2 payload.

    ``regime`` names the candidate regime the run belongs to and is stamped, not
    scored — a witness output is not a promotion path and
    :func:`reject_witness_promotion` says so in code.

    ``baxter_rmse`` is accepted only to be *refused*: the primary criterion is
    computed from a registered calibration observation set, none is mounted, and
    a number handed in through this door would be a witness report wearing the
    primary criterion's clothes.
    """
    if baxter_rmse is not None:
        raise GovernanceBlock(
            f"{PRIMARY_CALIBRATION_METRIC} may not be supplied to the witness harness. "
            f"Ruling {R2_CALIBRATION.convergence_id} makes it the primary criterion, "
            "computed from a registered calibration observation set; none is mounted and "
            f"its status is {BLOCKED_ON_CALIBRATION_DATA}."
        )
    if regime is not None and not isinstance(regime, CandidateRegime):
        raise InputValidationError(
            "regime must be a CandidateRegime; witness outputs are stamped with the "
            "candidate they belong to, never with a canonical configuration"
        )

    colley_ratings = colley_witness.compute_colley(colley_games(schedule))
    colley_record_map = colley_witness.colley_records(colley_games(schedule))
    colley_payload = colley_witness.witness_as_dict(colley_ratings, colley_record_map)
    colley_payload["properties"] = colley_witness.assert_colley_properties(
        colley_games(schedule)
    )

    if schedule.has_complete_margins:
        srs_input = srs_games(schedule)
        srs_ratings = srs_witness.compute_srs(srs_input)
        srs_payload = srs_witness.witness_as_dict(srs_ratings)
        srs_payload["properties"] = srs_witness.assert_solver_equivalence(srs_input)
        srs_payload["available"] = True
    else:
        srs_ratings = None
        srs_payload = {
            "model": "SRS",
            "role": srs_witness.WITNESS_ROLE,
            "available": False,
            "unavailable_reason": UNAVAILABLE_SRS_PROVENANCE,
            "ratings": UNAVAILABLE,
            "ordering": UNAVAILABLE,
            "canonical_validation_status": "NOT_VALIDATED_AGAINST_CANONICAL_ANCHORS",
            "canonical_validation_blocker": srs_witness.CANONICAL_VALIDATION_BLOCKER,
        }

    return {
        "interface_version": WITNESS_INTERFACE_VERSION,
        "ruling": R2_CALIBRATION.convergence_id,
        "schedule_id": schedule.schedule_id,
        "as_of_week": schedule.as_of_week,
        "authority": schedule.authority,
        "evidence_class": schedule.evidence_class,
        "teams": schedule.teams,
        "games": len(schedule.games),
        "regime": (
            None
            if regime is None
            else {
                "regime_id": regime.regime_id,
                "status": regime.status,
                "fields_set": sorted(regime.values),
                "promotion_authorised": False,
            }
        ),
        "primary_criterion": {
            "metric": PRIMARY_CALIBRATION_METRIC,
            "direction": PRIMARY_CALIBRATION_DIRECTION,
            "value": UNAVAILABLE,
            "status": BLOCKED_ON_CALIBRATION_DATA,
            "note": (
                "The witnesses below do not stand in for this criterion and are not "
                "blended into it."
            ),
        },
        "witnesses": {
            "reported_independently": list(INDEPENDENT_WITNESSES),
            "weighted_composite_authorised": False,
            "colley_matrix": colley_payload,
            "srs": srs_payload,
        },
        "disagreement": disagreement_flags(colley_ratings, srs_ratings),
        "governance": {
            "witness_role": colley_witness.WITNESS_ROLE,
            "is_governed_evidence": schedule.is_governed_evidence,
            "promotion_authorised": False,
            "canonical_values_written": False,
            "colley_canonical_spec_mounted": colley_witness.CANONICAL_COLLEY_SPEC_MOUNTED,
            "srs_canonical_spec_mounted": srs_witness.CANONICAL_SRS_SPEC_MOUNTED,
            "srs_over_40_semantics": srs_witness.SRS_OVER_40_SEMANTICS,
        },
    }


def require_governed_witness_evidence(report: dict[str, object]) -> dict[str, object]:
    """Fail closed before a synthetic-fixture report is cited as evidence."""
    if report.get("evidence_class") != EVIDENCE_GOVERNED:
        raise GovernanceBlock(
            f"Witness report for schedule {report.get('schedule_id')!r} was built under "
            f"authority {report.get('authority')!r}, which is not governance. A "
            f"{EVIDENCE_NOT_GOVERNED} report may be inspected but may not be cited as "
            "calibration evidence."
        )
    return report


def reject_witness_promotion(report: dict[str, object]) -> None:
    """Refuse promotion of a calibration value on witness output.

    A witness can disagree loudly and still not be an authority. Ruling
    R2-CAL-OBJECTIVE recognises governed calibration evidence from the holdout
    split, or explicit Chairman justification, and both additionally require the
    human approval token; a Colley/SRS report is neither.
    """
    raise GovernanceBlock(
        f"Witness output for schedule {report.get('schedule_id')!r} is not a promotion "
        f"authority. Ruling {R2_CALIBRATION.convergence_id} keeps "
        f"{PRIMARY_CALIBRATION_METRIC} primary and reports Colley and SRS independently; "
        "promotion additionally requires the human approval token. Use "
        "calibration.promote_regime_r2 with a named authority."
    )


def witness_interface_as_dict() -> dict[str, object]:
    """The contract itself, so an integrator can assert against it rather than a sample."""
    return {
        "interface_version": WITNESS_INTERFACE_VERSION,
        "ruling": R2_CALIBRATION.convergence_id,
        "report_fields": list(WITNESS_REPORT_FIELDS),
        "witnesses": list(INDEPENDENT_WITNESSES),
        "primary_metric": PRIMARY_CALIBRATION_METRIC,
        "primary_direction": PRIMARY_CALIBRATION_DIRECTION,
        "primary_status": BLOCKED_ON_CALIBRATION_DATA,
        "weighted_composite_authorised": False,
        "promotion_authorised": False,
        "evidence_classes": [EVIDENCE_GOVERNED, EVIDENCE_NOT_GOVERNED],
        "non_governed_authorities": list(NON_GOVERNED_AUTHORITIES),
        "srs_requires_margins": True,
        "colley_requires_margins": False,
    }
