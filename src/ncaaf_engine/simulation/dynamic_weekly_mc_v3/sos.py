"""Committee strength of schedule for V3.

Ruling R2-SOS fixes one quantity, one direction, one definition::

    SOS = 0.25 * WP + 0.50 * OWP + 0.25 * OOWP

Higher is a harder schedule. There is no second SOS, no mean-opponent-Elo
variant, and no revival of ``schedule_path_score`` + ``resume_ceiling_index``
double counting (both RETIRED in the Bracket Regime Deferred Register; DEF-2
records ``sos_index`` as "REPORTED, never scored").

The semantics underneath them are now governed too
--------------------------------------------------
Ruling R3-SOS-OWP-OOWP-SEMANTICS (direct Chairman authority, PR #3 final
convergence) answers the six questions that used to fail closed here:

1. an opponent's games **against the evaluated team are excluded** from that
   opponent's record when computing OWP;
2. OWP is **schedule-instance weighted**, not team-averaged;
3. a **repeated opponent counts once per completed meeting** — two meetings
   contribute two values, and unique-opponent averaging is not substituted;
4. **OOWP is the mean of each opponent's own governed OWP**, taken once per
   schedule instance, not a flattened pool of every opponent-of-opponent;
5. schedule-only **FCS** entities contribute only governed available qualifying
   completed-game records — where the record does not exist the component is
   UNAVAILABLE, never an invented win, loss, ``.500`` or ``0``;
6. a component with **zero qualifying observations is UNAVAILABLE / NULL**,
   never ``0``, ``0.0`` or ``0.500``.

Only games completed through the applicable week participate, so no future
result can leak into a weekly value.

Unavailability is a value, not a number
---------------------------------------
:data:`UNAVAILABLE` (``None``) propagates: an unavailable WP, OWP or OOWP makes
the SOS itself unavailable rather than silently becoming numeric. For reporting,
:func:`sos_report_row` stamps the unavailable component with its provenance. For
tiebreaks, a criterion that cannot be evaluated because a required governed
component is unavailable **does not resolve the tie** — processing advances to
the next already-governed stage rather than inventing a separation.

The pre-ruling instances remain constructible so the historical policies stay
testable; :data:`GOVERNED_SOS_SEMANTICS` is the one the production gate accepts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

from .errors import GovernanceBlock, InputValidationError
from .rulings import R2_SOS, R3_SOS_SEMANTICS

#: FACT — ruling R2-SOS.
WP_WEIGHT = 0.25
OWP_WEIGHT = 0.50
OOWP_WEIGHT = 0.25

SOS_SEMANTICS_BLOCKER = "governance.OWP_OOWP_DENOMINATOR_SEMANTICS_NOT_GOVERNED"

InstanceWeighting = Literal["PER_GAME", "PER_OPPONENT"]
OowpConstruction = Literal["MEAN_OF_OPPONENT_OWP", "MEAN_OVER_ALL_OPPONENT_OPPONENTS"]
FcsTreatment = Literal[
    "INCLUDE",
    "EXCLUDE_FROM_ALL",
    "COUNT_IN_WP_ONLY",
    "INCLUDE_WHERE_GOVERNED_RECORD_EXISTS",
]
ZeroGamesPolicy = Literal[
    "TREAT_AS_ZERO",
    "EXCLUDE_FROM_AVERAGES",
    "BLOCK",
    "UNAVAILABLE",
]

#: A component with no qualifying observations. Never 0, 0.0 or 0.500.
UNAVAILABLE: None = None

#: Stamped on any reported component that came back UNAVAILABLE.
UNAVAILABLE_PROVENANCE = (
    "UNAVAILABLE — zero qualifying completed-game observations under ruling "
    "R3-SOS-OWP-OOWP-SEMANTICS. No value was invented."
)

#: The six semantics questions a governed ruling must answer, in order.
REQUIRED_SEMANTICS_RULINGS = (
    "Are an opponent's games against the evaluated team removed from that opponent's "
    "record when computing OWP?",
    "Is OWP team-averaged or schedule-instance-weighted?",
    "How is a repeated opponent treated - once, or once per meeting?",
    "How is OOWP constructed - the mean of each opponent's OWP, or the mean over every "
    "opponent-of-opponent directly?",
    "How do schedule-only FCS opponent records enter WP, OWP and OOWP?",
    "What happens to a team with zero qualifying games?",
)


@dataclass(frozen=True)
class GameResult:
    """One completed game from the rated team's point of view."""

    game_id: str
    week: int
    team: str
    opponent: str
    won: bool


@dataclass(frozen=True)
class SosSemantics:
    """The denominator and exclusion rules the governed weights are applied to."""

    semantics_id: str
    authority: str
    #: Exclude the rated team's games against an opponent from that opponent's WP.
    exclude_rated_team_from_owp: bool
    #: Weight an opponent once per game played, or once per distinct opponent.
    instance_weighting: InstanceWeighting
    #: Exclude the rated team when averaging each opponent's OWP into OOWP.
    exclude_rated_team_from_oowp: bool
    #: How OOWP is assembled from the opponent set.
    oowp_construction: OowpConstruction = "MEAN_OF_OPPONENT_OWP"
    #: How schedule-only FCS opponents enter WP / OWP / OOWP.
    schedule_only_fcs_treatment: FcsTreatment = "INCLUDE"
    #: What a team with no qualifying games contributes to an average.
    zero_qualifying_games: ZeroGamesPolicy = "TREAT_AS_ZERO"
    #: Schedule IDs to treat as schedule-only FCS entities.
    schedule_only_fcs_ids: frozenset[str] = frozenset()

    def as_dict(self) -> dict[str, object]:
        return {
            "semantics_id": self.semantics_id,
            "authority": self.authority,
            "exclude_rated_team_from_owp": self.exclude_rated_team_from_owp,
            "instance_weighting": self.instance_weighting,
            "exclude_rated_team_from_oowp": self.exclude_rated_team_from_oowp,
            "oowp_construction": self.oowp_construction,
            "schedule_only_fcs_treatment": self.schedule_only_fcs_treatment,
            "zero_qualifying_games": self.zero_qualifying_games,
        }


def governed_sos_semantics(
    schedule_only_fcs_ids: frozenset[str] = frozenset(),
) -> SosSemantics:
    """The semantics ruling R3-SOS-OWP-OOWP-SEMANTICS issues, in full.

    ``schedule_only_fcs_ids`` names the schedule-only FCS entities for a given
    run. They are included wherever a governed qualifying record exists and make
    the component UNAVAILABLE where it does not — the ruling forbids inventing
    one either way.
    """
    return SosSemantics(
        semantics_id=R3_SOS_SEMANTICS.convergence_id,
        authority=(
            "Direct Chairman authority, ruling "
            f"{R3_SOS_SEMANTICS.convergence_id} ({R3_SOS_SEMANTICS.instruction})"
        ),
        # Q1: an opponent's games against the evaluated team are excluded.
        exclude_rated_team_from_owp=True,
        # Q2 + Q3: schedule-instance weighted, once per completed meeting.
        instance_weighting="PER_GAME",
        # Q4: OOWP is the mean of each opponent's *own* governed OWP. O's OWP is
        # computed normally, so the evaluated team is not additionally stripped
        # out of it — the ruling says "O's own governed OWP", not "minus T".
        exclude_rated_team_from_oowp=False,
        oowp_construction="MEAN_OF_OPPONENT_OWP",
        # Q5: governed available records only; absence is UNAVAILABLE.
        schedule_only_fcs_treatment="INCLUDE_WHERE_GOVERNED_RECORD_EXISTS",
        # Q6: zero qualifying observations is UNAVAILABLE / NULL.
        zero_qualifying_games="UNAVAILABLE",
        schedule_only_fcs_ids=schedule_only_fcs_ids,
    )


#: The governed semantics. Before ruling R3-SOS-OWP-OOWP-SEMANTICS this was
#: deliberately ``None`` and every entry point failed closed.
GOVERNED_SOS_SEMANTICS: SosSemantics | None = governed_sos_semantics()

#: Authorities that are explicitly not governance. Named so the gate can say why.
NON_GOVERNED_AUTHORITIES = ("TEST_FIXTURE", "RESEARCH", "PROPOSED", "ASSUMED", "")


def required_ruling_text() -> str:
    """The precise mathematical ruling this blocker is waiting on."""
    numbered = "\n".join(
        f"  {i}. {q}" for i, q in enumerate(REQUIRED_SEMANTICS_RULINGS, 1)
    )
    return (
        f"Ruling {R2_SOS.convergence_id} fixes the SOS weights "
        "(0.25 WP / 0.50 OWP / 0.25 OOWP). A governed ruling must additionally answer, "
        "for both SOS and the common-opponent comparison that shares these semantics:\n"
        f"{numbered}"
    )


def require_governed_sos_semantics(semantics: SosSemantics | None) -> SosSemantics:
    """Fail closed until all six OWP/OOWP semantics questions are governed."""
    if semantics is None:
        raise GovernanceBlock(f"{SOS_SEMANTICS_BLOCKER}: {required_ruling_text()}")
    if semantics.authority.upper() in NON_GOVERNED_AUTHORITIES:
        raise GovernanceBlock(
            f"{SOS_SEMANTICS_BLOCKER}: SOS semantics {semantics.semantics_id!r} carries "
            f"authority {semantics.authority!r}, which is not a governed source.\n"
            f"{required_ruling_text()}"
        )
    return semantics


class ResumeLedger:
    """Completed games, queryable as of a week so no future result can leak in."""

    def __init__(self, results: Iterable[GameResult]) -> None:
        self._results = tuple(sorted(results, key=lambda r: (r.week, r.game_id, r.team)))
        seen: set[tuple[str, str]] = set()
        for r in self._results:
            key = (r.game_id, r.team)
            if key in seen:
                raise InputValidationError(f"Duplicate ledger row for {r.team} in {r.game_id}")
            seen.add(key)

    @property
    def results(self) -> tuple[GameResult, ...]:
        return self._results

    def through_week(self, as_of_week: int) -> "ResumeLedger":
        return ResumeLedger(r for r in self._results if r.week <= as_of_week)

    def teams(self) -> tuple[str, ...]:
        return tuple(sorted({r.team for r in self._results}))

    def games_for(self, team: str) -> tuple[GameResult, ...]:
        return tuple(r for r in self._results if r.team == team)

    def record(self, team: str, *, excluding_opponent: str | None = None) -> tuple[int, int]:
        wins = losses = 0
        for r in self.games_for(team):
            if excluding_opponent is not None and r.opponent == excluding_opponent:
                continue
            if r.won:
                wins += 1
            else:
                losses += 1
        return wins, losses


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _unavailable(semantics: SosSemantics | None) -> bool:
    """True when this semantics reports an empty component as UNAVAILABLE."""
    return semantics is not None and semantics.zero_qualifying_games == "UNAVAILABLE"


def _mean_or_unavailable(
    values: list[float | None], semantics: SosSemantics | None
) -> float | None:
    """Arithmetic mean, or UNAVAILABLE when the ruling forbids inventing one.

    Under ruling R3-SOS-OWP-OOWP-SEMANTICS a component with zero qualifying
    observations, or one whose own inputs are unavailable, is UNAVAILABLE. It is
    never backfilled with 0, 0.0 or 0.500.
    """
    if _unavailable(semantics):
        if not values or any(v is None for v in values):
            return UNAVAILABLE
        return sum(float(v) for v in values) / len(values)
    return _mean([0.0 if v is None else float(v) for v in values])


def win_pct(
    ledger: ResumeLedger,
    team: str,
    *,
    excluding_opponent: str | None = None,
    semantics: SosSemantics | None = None,
) -> float | None:
    """WP = wins / completed qualifying games, under the zero-games policy.

    With no semantics supplied the historical default applies (zero games reads
    0.0). Under the governed ruling the policy is ``UNAVAILABLE``: a team with no
    qualifying completed games returns :data:`UNAVAILABLE` rather than 0.0 or
    0.500, and that unavailability propagates into OWP, OOWP and SOS.
    """
    wins, losses = ledger.record(team, excluding_opponent=excluding_opponent)
    played = wins + losses
    if played:
        return wins / played
    policy = semantics.zero_qualifying_games if semantics else "TREAT_AS_ZERO"
    if policy == "BLOCK":
        raise GovernanceBlock(
            f"{team} has zero qualifying games and the governed zero-games policy is BLOCK."
        )
    if policy == "UNAVAILABLE":
        return UNAVAILABLE
    return 0.0


def _counts_toward(opponent: str, semantics: SosSemantics, stage: str) -> bool:
    """Whether a schedule-only FCS opponent enters this stage of the calculation."""
    if opponent not in semantics.schedule_only_fcs_ids:
        return True
    if semantics.schedule_only_fcs_treatment == "INCLUDE":
        return True
    if semantics.schedule_only_fcs_treatment == "EXCLUDE_FROM_ALL":
        return False
    if semantics.schedule_only_fcs_treatment == "INCLUDE_WHERE_GOVERNED_RECORD_EXISTS":
        # The schedule instance is real, so it participates. Whether a governed
        # record exists is decided downstream: absent one, the component comes
        # back UNAVAILABLE instead of being invented.
        return True
    return stage == "WP"


def _opponent_instances(
    ledger: ResumeLedger, team: str, semantics: SosSemantics
) -> list[str]:
    opponents = [
        r.opponent for r in ledger.games_for(team)
        if _counts_toward(r.opponent, semantics, "OWP")
    ]
    if semantics.instance_weighting == "PER_OPPONENT":
        return sorted(set(opponents))
    if semantics.instance_weighting != "PER_GAME":
        raise InputValidationError(f"Unknown instance weighting {semantics.instance_weighting!r}")
    return sorted(opponents)


def opponent_win_pct(
    ledger: ResumeLedger, team: str, semantics: SosSemantics
) -> float | None:
    """OWP: mean opponent WP, under the governed exclusion and weighting.

    Under ruling R3-SOS-OWP-OOWP-SEMANTICS this is schedule-instance weighted:
    one value per completed meeting, with the opponent's games against the
    evaluated team excluded from that opponent's record. A repeated opponent
    therefore contributes once per meeting, and an opponent with no governed
    qualifying record makes the whole component UNAVAILABLE.
    """
    exclude = team if semantics.exclude_rated_team_from_owp else None
    values: list[float | None] = []
    for opp in _opponent_instances(ledger, team, semantics):
        if semantics.zero_qualifying_games == "EXCLUDE_FROM_AVERAGES":
            wins, losses = ledger.record(opp, excluding_opponent=exclude)
            if wins + losses == 0:
                continue
        values.append(win_pct(ledger, opp, excluding_opponent=exclude, semantics=semantics))
    return _mean_or_unavailable(values, semantics)


def opponent_opponent_win_pct(
    ledger: ResumeLedger, team: str, semantics: SosSemantics
) -> float | None:
    """OOWP under the configured construction.

    ``MEAN_OF_OPPONENT_OWP`` averages each opponent's own OWP.
    ``MEAN_OVER_ALL_OPPONENT_OPPONENTS`` pools every opponent-of-opponent into a
    single average instead. The two differ whenever opponents played unequal
    numbers of games, which is most of a real season.
    """
    per_opponent: list[float | None] = []
    pooled: list[float | None] = []
    for opp in _opponent_instances(ledger, team, semantics):
        opp_opponents = _opponent_instances(ledger, opp, semantics)
        if semantics.exclude_rated_team_from_oowp:
            opp_opponents = [o for o in opp_opponents if o != team]
        exclude = opp if semantics.exclude_rated_team_from_owp else None
        inner: list[float | None] = [
            win_pct(ledger, o, excluding_opponent=exclude, semantics=semantics)
            for o in opp_opponents
        ]
        # One OWP(O) value per schedule instance T-vs-O, exactly as ruled.
        per_opponent.append(_mean_or_unavailable(inner, semantics))
        pooled.extend(inner)
    if semantics.oowp_construction == "MEAN_OVER_ALL_OPPONENT_OPPONENTS":
        return _mean_or_unavailable(pooled, semantics)
    return _mean_or_unavailable(per_opponent, semantics)


def strength_of_schedule(
    ledger: ResumeLedger, team: str, semantics: SosSemantics
) -> float | None:
    """SOS = 0.25 * WP + 0.50 * OWP + 0.25 * OOWP (ruling R2-SOS).

    The weights are R2's and are unchanged. Under the governed semantics an
    UNAVAILABLE component makes the SOS itself UNAVAILABLE — it never silently
    becomes numeric by treating a missing component as zero.
    """
    wp = win_pct(ledger, team, semantics=semantics)
    owp = opponent_win_pct(ledger, team, semantics)
    oowp = opponent_opponent_win_pct(ledger, team, semantics)
    if _unavailable(semantics) and (wp is None or owp is None or oowp is None):
        return UNAVAILABLE
    return (
        WP_WEIGHT * float(wp or 0.0)
        + OWP_WEIGHT * float(owp or 0.0)
        + OOWP_WEIGHT * float(oowp or 0.0)
    )


def sos_components(
    ledger: ResumeLedger, team: str, semantics: SosSemantics
) -> dict[str, float | None]:
    return {
        "wp": win_pct(ledger, team, semantics=semantics),
        "owp": opponent_win_pct(ledger, team, semantics),
        "oowp": opponent_opponent_win_pct(ledger, team, semantics),
        "sos": strength_of_schedule(ledger, team, semantics),
    }


def sos_report_row(
    ledger: ResumeLedger, team: str, semantics: SosSemantics
) -> dict[str, object]:
    """One reporting row, with every unavailable component stamped.

    The ruling requires unavailability be reported with provenance rather than
    rendered as a number, so the caller can never mistake an absent component for
    a zero-strength one.
    """
    components = sos_components(ledger, team, semantics)
    unavailable = sorted(k for k, v in components.items() if v is None)
    return {
        "ruling": R3_SOS_SEMANTICS.convergence_id,
        "semantics_id": semantics.semantics_id,
        "team": team,
        **components,
        "unavailable_components": unavailable,
        "provenance": UNAVAILABLE_PROVENANCE if unavailable else "COMPLETE",
    }


def criterion_resolves(value_a: float | None, value_b: float | None) -> bool:
    """Whether a tiebreak criterion actually separates two teams.

    A criterion whose required governed component is UNAVAILABLE on either side
    does not resolve the tie: the ruling sends processing to the next
    already-governed stage rather than letting an absent value decide.
    """
    if value_a is None or value_b is None:
        return False
    return value_a != value_b


def rank_by_sos(
    ledger: ResumeLedger, teams: Iterable[str], semantics: SosSemantics
) -> list[str]:
    """Hardest schedule first; ties break on schedule_id so the order is total.

    A team whose SOS is UNAVAILABLE cannot be placed in a strength order without
    inventing the missing component, so this fails closed and names the teams
    rather than sorting them to the bottom.
    """
    listed = sorted(set(teams))
    scored = {t: strength_of_schedule(ledger, t, semantics) for t in listed}
    unavailable = sorted(t for t, v in scored.items() if v is None)
    if unavailable:
        raise GovernanceBlock(
            f"Cannot rank by SOS: {unavailable} have an UNAVAILABLE component under "
            f"ruling {R3_SOS_SEMANTICS.convergence_id}. {UNAVAILABLE_PROVENANCE}"
        )
    return sorted(listed, key=lambda t: (-float(scored[t]), t))
