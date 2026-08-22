"""Full-season execution for the INTERNAL / SHADOW / TEST_ONLY MVP.

The V3 phase plan has always named five phases. Four of them had governed
implementations and no orchestration: the weekly loop stopped at Week 14 and
:mod:`.cli` raised on the way to anything further, because the rerating the later
phases depend on was fail-closed. With the six calibration values promoted and
the FCS scale adapter installed, the orchestration is what is left, and this
module is it — the phases in their governed order, each one calling the module
that already owns it.

    PRESELECTION_REGULAR (W1-W14)  -> engine, promoted rerating after each week
    CONFERENCE_CHAMPIONSHIPS (W15) -> ccg, then one further promoted rerating
    CFP_SELECTION                  -> committee board, then strength freezes
    POST_SELECTION_ARMY_NAVY (W16) -> played on frozen strength, no rerating
    CFP_POSTSEASON                 -> postseason, fixed topology, frozen strength

Three properties are structural rather than checked afterwards.

*Nothing new is decided here.* Every governed question — who fills a CCG seat,
which G5 champion takes seed 5, which first-round winner reaches which
quarterfinal — is answered by the module that holds the ruling. This module
sequences them and simulates games.

*Tier changes only how many paths are drawn.* Draws are keyed by semantic
coordinates in :mod:`.rng`, so path 17 of a 500-path run is bit-identical to
path 17 of a 10,000-path run. No mathematics, no governance and no parameter in
this module reads the path count.

*Venue is never invented.* A regular-season or championship game uses the venue
its governed schedule row carries. Every postseason game is NEUTRAL: the mounted
bracket artifacts name fixed sites and assign no home host to any bracket slot,
so there is no governed home-field modifier to apply, and V3's neutral branch
already means exactly zero rather than a default.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

from . import ccg as ccg_policy
from . import committee, fcs as fcs_policy, mvp_control, ordering, postseason, sos
from . import run_tier as tier_policy
from .aac_divisions import require_governed_aac_divisions_csv
from .config import V3Config
from .engine import DynamicWeeklyMCV3
from .errors import GovernanceBlock
from .game import simulate_game
from .inputs import load_schedule, load_teams
from .models import GameObservation, ScheduledGame, Team, TeamPathState, TeamSeasonOutcome
from .rerating import PromotedRegimeRerater
from .rulings import R5_FCS_SCALE, R5_MVP_CONTROL_CORPUS

#: Conferences whose champion is decided on conference play rather than a CCG.
STANDINGS_ONLY_CONFERENCES: tuple[str, ...] = ordering.STANDINGS_ONLY_CONFERENCES

#: The conference with no champion at all. Independents are not champion-eligible
#: and the schedule carries no CCG row for them.
NO_CHAMPION_CONFERENCES: tuple[str, ...] = ("Independent",)


# ---------------------------------------------------------------------------
# Governance activation.
# ---------------------------------------------------------------------------


def activate_internal_shadow_mvp(root: Path) -> dict[str, object]:
    """Install the two R5 governance items, each through its own gate.

    Deliberately explicit and deliberately not automatic. An FCS point value and
    a calibrated game-SD are both governance events, so they happen at a call a
    reader can find, and any caller that has not made it still sees the
    pre-ruling fail-closed state.
    """
    adapter = fcs_policy.install_governed_fcs_scale_adapter()
    venue_modifier = fcs_policy.install_governed_fcs_hfa_modifier()
    calibration = mvp_control.run_control_calibration(root)
    promotion = mvp_control.install_calibration_promotion(calibration.promotion)
    return {
        "scope": mvp_control.MVP_SCOPE,
        "rulings": [R5_FCS_SCALE.convergence_id, R5_MVP_CONTROL_CORPUS.convergence_id],
        "fcs_scale_adapter": adapter.as_dict(),
        "fcs_venue_clause": fcs_policy.fcs_venue_clause_as_dict(),
        "fcs_home_field_modifier": venue_modifier,
        "calibration_promotion": promotion,
        "calibration_report": calibration.report,
    }


# ---------------------------------------------------------------------------
# A resume ledger the governed SOS functions can be driven at path scale.
# ---------------------------------------------------------------------------


class IndexedResumeLedger(sos.ResumeLedger):
    """:class:`sos.ResumeLedger` with its two hot lookups indexed and memoised.

    The governed SOS mathematics is not reimplemented here and must not be: OWP
    exclusions, schedule-instance weighting and the OOWP construction all live in
    :mod:`.sos` under ruling R3-SOS-OWP-OOWP-SEMANTICS, and a second copy of them
    would be a second thing to keep correct. What is replaced is only the two
    accessors those functions call — both of which scan the whole result tuple in
    the base class, which is fine for one report and quadratic across a
    ten-thousand-path season.

    ``tests`` pin the equivalence directly: the same season scored through the
    base class and through this one must agree exactly, and the base class stays
    the definition of correct.
    """

    def __init__(self, results: Iterable[sos.GameResult]) -> None:
        super().__init__(results)
        by_team: dict[str, list[sos.GameResult]] = {}
        for result in self.results:
            by_team.setdefault(result.team, []).append(result)
        self._by_team = {team: tuple(rows) for team, rows in by_team.items()}
        self._records: dict[tuple[str, str | None], tuple[int, int]] = {}

    def games_for(self, team: str) -> tuple[sos.GameResult, ...]:
        return self._by_team.get(team, ())

    def record(
        self, team: str, *, excluding_opponent: str | None = None
    ) -> tuple[int, int]:
        key = (team, excluding_opponent)
        cached = self._records.get(key)
        if cached is not None:
            return cached
        wins = losses = 0
        for row in self._by_team.get(team, ()):
            if excluding_opponent is not None and row.opponent == excluding_opponent:
                continue
            if row.won:
                wins += 1
            else:
                losses += 1
        self._records[key] = (wins, losses)
        return self._records[key]


def ledger_from_observations(
    observations: Sequence[GameObservation],
) -> IndexedResumeLedger:
    rows: list[sos.GameResult] = []
    for observation in observations:
        rows.append(
            sos.GameResult(
                game_id=observation.game_id,
                week=observation.week,
                team=observation.home_team,
                opponent=observation.away_team,
                won=observation.home_won,
            )
        )
        rows.append(
            sos.GameResult(
                game_id=observation.game_id,
                week=observation.week,
                team=observation.away_team,
                opponent=observation.home_team,
                won=not observation.home_won,
            )
        )
    return IndexedResumeLedger(rows)


# ---------------------------------------------------------------------------
# The committee board.
# ---------------------------------------------------------------------------
#
# The board is results-first, exactly as committee.rank_committee_results_first
# builds it: win percentage, then opponent win percentage, then champion status,
# then head-to-head among teams tied on all three, then the governed
# strength-of-schedule, then the schedule id.
#
# The fourth key is deliberately the governed SOS and never a strength number.
# Ruling R2-COMMITTEE-TB retired the framing in which a hidden strength value
# breaks a committee tie and replaced it with the chain TB1 head-to-head, TB2
# common-opponent performance, TB3 SOS, TB4 previous board. TB1 and TB3 are what
# this board consults; no football strength value enters it, which is asserted by
# test rather than left to the reader.

BOARD_TIEBREAKS_CONSULTED: tuple[str, ...] = (
    "COMMITTEE-TB1_HEAD_TO_HEAD",
    "COMMITTEE-TB3_STRENGTH_OF_SCHEDULE",
)

#: Recorded rather than quietly skipped. TB2 sits between the two consulted
#: stages and is not reached: the board's preceding keys already order the field
#: totally except where TB1 applies, and pairwise common-opponent scoring across
#: a 121-team board on every path is not what this MVP needs. Carried forward.
BOARD_TIEBREAKS_NOT_CONSULTED: tuple[str, ...] = (
    "COMMITTEE-TB2_COMMON_OPPONENT_PERFORMANCE",
    "COMMITTEE-TB4_PREVIOUS_WEEK_BOARD",
)

#: The final, fully deterministic key. Not a governance claim: a disclosed
#: convention that makes the ordering total when every governed criterion ties.
BOARD_TERMINAL_ORDERING = "CANONICAL_SCHEDULE_ID_ASCENDING"


def head_to_head_from(observations: Sequence[GameObservation]) -> Callable[[str, str], str | None]:
    """Pairwise head-to-head over completed games, or ``None`` if unresolved."""
    tally: dict[frozenset[str], dict[str, int]] = {}
    for observation in observations:
        key = frozenset((observation.home_team, observation.away_team))
        winner = observation.home_team if observation.home_won else observation.away_team
        tally.setdefault(key, {})
        tally[key][winner] = tally[key].get(winner, 0) + 1

    def resolve(team_a: str, team_b: str) -> str | None:
        results = tally.get(frozenset((team_a, team_b)))
        if not results:
            return None
        a_wins = results.get(team_a, 0)
        b_wins = results.get(team_b, 0)
        if a_wins == b_wins:
            return None
        return team_a if a_wins > b_wins else team_b

    return resolve


def build_board(
    fbs_teams: Sequence[str],
    observations: Sequence[GameObservation],
    conference_champions: Mapping[str, str],
    semantics: sos.SosSemantics,
) -> tuple[str, ...]:
    """The committee board over the governed FBS membership."""
    ledger = ledger_from_observations(observations)
    champions = set(conference_champions.values())
    inputs: dict[str, committee.CommitteeInputs] = {}
    for team in fbs_teams:
        wins, losses = ledger.record(team)
        owp = sos.opponent_win_pct(ledger, team, semantics)
        schedule_strength = sos.strength_of_schedule(ledger, team, semantics)
        inputs[team] = committee.CommitteeInputs(
            wins=wins,
            losses=losses,
            opponent_win_pct=float(owp or 0.0),
            conference_champion=team in champions,
            # TB3, not a strength. See BOARD_TIEBREAKS_CONSULTED above.
            strength_tiebreak=float(schedule_strength or 0.0),
        )
    pairwise = head_to_head_from(observations)
    head_to_head: dict[frozenset[str], str] = {}
    for observation in observations:
        key = frozenset((observation.home_team, observation.away_team))
        if key in head_to_head or len(key) != 2:
            continue
        left, right = tuple(sorted(key))
        winner = pairwise(left, right)
        if winner is not None:
            head_to_head[key] = winner
    return tuple(committee.rank_committee_results_first(inputs, head_to_head))


# ---------------------------------------------------------------------------
# One season path.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SeasonPath:
    """Everything one path produced, before aggregation."""

    path_id: int
    observations: tuple[GameObservation, ...]
    outcomes: tuple[TeamSeasonOutcome, ...]
    conference_champions: dict[str, str]
    pre_ccg_board: tuple[str, ...]
    post_ccg_board: tuple[str, ...]
    cfp_seeds: dict[int, str]
    bid_types: dict[str, str]
    bracket: dict[str, tuple[str, str, str]]
    national_champion: str


def _simulate_one_game(
    *,
    config: V3Config,
    path_id: int,
    game: ScheduledGame,
    states: Mapping[str, TeamPathState],
    teams: Mapping[str, Team],
    state_version: str,
) -> GameObservation:
    home_team = teams[str(game.home_team)]
    return simulate_game(
        base_seed=config.base_seed,
        path_id=path_id,
        game=game,
        home=states[str(game.home_team)],
        away=states[str(game.away_team)],
        hfa_baseline_points=float(config.hfa_baseline_points or 0.0),
        home_hfa_modifier=fcs_policy.require_fcs_hfa_modifier(
            home_team.hfa_modifier, str(game.home_team)
        ),
        game_sd_points=float(config.calibration.game_sd_points or 0.0),
        rating_state_version=state_version,
    )


def _apply_result(
    observation: GameObservation,
    game: ScheduledGame,
    states: Mapping[str, TeamPathState],
) -> None:
    home = states[observation.home_team]
    away = states[observation.away_team]
    winner = home if observation.home_won else away
    loser = away if observation.home_won else home
    winner.wins += 1
    loser.losses += 1
    home.games_played += 1
    away.games_played += 1
    if game.conference_game:
        winner.conference_wins += 1
        loser.conference_losses += 1


def simulate_season_path(
    engine: DynamicWeeklyMCV3,
    *,
    path_id: int,
    teams: Mapping[str, Team],
    schedule: Sequence[ScheduledGame],
    division_of: Mapping[str, str],
    semantics: sos.SosSemantics,
) -> SeasonPath:
    """Play one complete governed season, phase by phase."""
    config = engine.config
    states = engine._initialize_states(dict(teams))
    fbs_teams = sorted(
        sid for sid, team in teams.items() if team.entity_scope == "FBS_MEMBER"
    )
    conference_of = {sid: str(team.conference or "") for sid, team in teams.items()}
    schedule_by_id = {game.game_id: game for game in schedule}
    observations: list[GameObservation] = []

    # --- PRESELECTION_REGULAR, W1-W14 ------------------------------------
    regular = [g for g in schedule if g.game_type == "REG"]
    for week in range(1, 15):
        weekly = sorted((g for g in regular if g.week == week), key=lambda g: g.game_id)
        weekly_residuals: dict[str, list[float]] = {sid: [] for sid in states}
        version = f"path-{path_id:05d}:week-{week:02d}:OPEN"
        for game in weekly:
            observation = _simulate_one_game(
                config=config,
                path_id=path_id,
                game=game,
                states=states,
                teams=teams,
                state_version=version,
            )
            observations.append(observation)
            weekly_residuals[observation.home_team].append(
                observation.performance_residual_home
            )
            weekly_residuals[observation.away_team].append(
                observation.performance_residual_away
            )
            _apply_result(observation, game, states)
        _promote_week(engine, week, states, weekly_residuals)

    pre_ccg_board = build_board(fbs_teams, observations, {}, semantics)

    # --- CONFERENCE_CHAMPIONSHIPS, W15 -----------------------------------
    champions: dict[str, str] = {}
    ccg_participants: list[str] = []
    ccg_rows = sorted(
        (g for g in schedule if g.game_type == "CCG"), key=lambda g: g.game_id
    )
    tiebreak_inputs = ccg_policy.CcgTiebreakInputs(
        head_to_head=head_to_head_from(observations),
        mini_round_robin=_mini_round_robin(observations, schedule_by_id),
        last_board_before_championship_saturday=pre_ccg_board,
    )
    weekly_residuals = {sid: [] for sid in states}
    version = f"path-{path_id:05d}:week-15:OPEN"
    for game in ccg_rows:
        conference = str(game.home_conf)
        members = [
            sid
            for sid in fbs_teams
            if conference_of[sid] == conference
        ]
        records = [
            ccg_policy.ConferenceRecord(
                schedule_id=sid,
                conference_wins=states[sid].conference_wins,
                conference_losses=states[sid].conference_losses,
                division=division_of.get(sid),
            )
            for sid in members
        ]
        if conference == ccg_policy.AAC_CONFERENCE:
            selection = ccg_policy.select_aac_ccg_participants(
                records, tiebreak_inputs, division_of
            )
        else:
            selection = ccg_policy.select_ccg_participants(
                conference, records, tiebreak_inputs
            )
        ccg_participants.extend((selection.seat_1, selection.seat_2))
        resolved = replace(
            game, home_team=selection.seat_1, away_team=selection.seat_2
        )
        observation = _simulate_one_game(
            config=config,
            path_id=path_id,
            game=resolved,
            states=states,
            teams=teams,
            state_version=version,
        )
        observations.append(observation)
        weekly_residuals[observation.home_team].append(
            observation.performance_residual_home
        )
        weekly_residuals[observation.away_team].append(
            observation.performance_residual_away
        )
        _apply_result(observation, resolved, states)
        schedule_by_id[observation.game_id] = resolved
        champions[conference] = (
            observation.home_team if observation.home_won else observation.away_team
        )
    _promote_week(engine, 15, states, weekly_residuals)

    # --- CFP_SELECTION ----------------------------------------------------
    # The A8/ECL board is computed after the championships and before any G5
    # automatic-bid seeding, which is the causal sequencing ruling R2-A8-ECL-ORDER
    # uses to break the cycle. It is also the board the committee selects from.
    post_ccg_board = build_board(fbs_teams, observations, champions, semantics)
    ledger = ledger_from_observations(observations)
    standings_board = ordering.PostCcgBoard(
        order=post_ccg_board, ccgs_complete=True, g5_seeding_applied=False
    )
    for conference in STANDINGS_ONLY_CONFERENCES:
        members = [sid for sid in fbs_teams if conference_of[sid] == conference]
        best = max(
            (
                states[sid].conference_wins
                / max(1, states[sid].conference_wins + states[sid].conference_losses)
            )
            for sid in members
        )
        contenders = [
            sid
            for sid in members
            if (
                states[sid].conference_wins
                / max(1, states[sid].conference_wins + states[sid].conference_losses)
            )
            == best
        ]
        champion, _step = ordering.resolve_standings_champion(
            conference,
            contenders,
            head_to_head=head_to_head_from(observations),
            common_opponent_score=_common_opponent_scorer(ledger, semantics),
            post_ccg_board=standings_board,
        )
        champions[conference] = champion

    selection = postseason.select_governed_14_team_cfp(
        list(post_ccg_board), conference_of, champions
    )
    selection = postseason.apply_g5_automatic_bid_seed(
        selection, list(post_ccg_board), champions
    )
    postseason.g5_automatic_bid_audit(selection, conference_of)

    # Strength freezes here. Nothing below promotes a rerating.
    frozen_strength = {sid: state.current_strength_points for sid, state in states.items()}

    # --- POST_SELECTION_ARMY_NAVY, W16 ------------------------------------
    version = f"path-{path_id:05d}:week-16:FROZEN"
    for game in sorted(
        (g for g in regular if g.week == 16), key=lambda g: g.game_id
    ):
        observation = _simulate_one_game(
            config=config,
            path_id=path_id,
            game=game,
            states=states,
            teams=teams,
            state_version=version,
        )
        observations.append(observation)
        _apply_result(observation, game, states)

    # --- CFP_POSTSEASON ---------------------------------------------------
    bracket = postseason.advance_bracket(
        selection,
        _bracket_winner(config, path_id, frozen_strength),
    )
    champion = bracket["CHAMPIONSHIP"][2]

    return SeasonPath(
        path_id=path_id,
        observations=tuple(observations),
        outcomes=tuple(
            _season_outcomes(
                path_id=path_id,
                fbs_teams=fbs_teams,
                states=states,
                champions=champions,
                board=post_ccg_board,
                selection=selection,
                bracket=bracket,
                frozen_strength=frozen_strength,
                ccg_participants=ccg_participants,
            )
        ),
        conference_champions=dict(champions),
        pre_ccg_board=pre_ccg_board,
        post_ccg_board=post_ccg_board,
        cfp_seeds=dict(selection.seeds),
        bid_types=dict(selection.bid_types),
        bracket=dict(bracket),
        national_champion=champion,
    )


def _promote_week(
    engine: DynamicWeeklyMCV3,
    week: int,
    states: dict[str, TeamPathState],
    weekly_residuals: Mapping[str, Sequence[float]],
) -> None:
    """Append the week's mean residual and apply the governed rerating.

    Identical in shape to the engine's own weekly promotion, including the 0.0
    a team on a bye appends: the calibration was run against exactly this
    aggregation, so it is reproduced rather than improved on.
    """
    for sid, state in states.items():
        values = list(weekly_residuals.get(sid, ()))
        state.residual_history.append(
            sum(values) / len(values) if values else 0.0
        )
    candidate = engine.rerater.rerate(
        week_completed=week, states=states, config=engine.config
    )
    if engine.config.audit_only_after_week(week):
        return
    for sid, strength in candidate.items():
        states[sid].promoted_strength_points = strength
        states[sid].current_strength_points = strength


def _mini_round_robin(
    observations: Sequence[GameObservation],
    schedule_by_id: Mapping[str, ScheduledGame],
) -> Callable[[Sequence[str]], Sequence[str]]:
    """CCG-TB2: survivors of the mini round-robin among a tied band."""

    def resolve(band: Sequence[str]) -> Sequence[str]:
        members = set(band)
        wins = {team: 0 for team in band}
        played = {team: 0 for team in band}
        for observation in observations:
            if not {observation.home_team, observation.away_team}.issubset(members):
                continue
            game = schedule_by_id.get(observation.game_id)
            if game is None or not game.conference_game:
                continue
            winner = observation.home_team if observation.home_won else observation.away_team
            wins[winner] += 1
            played[observation.home_team] += 1
            played[observation.away_team] += 1
        rates = {
            team: (wins[team] / played[team] if played[team] else -1.0) for team in band
        }
        best = max(rates.values())
        if best < 0.0:
            return list(band)
        return sorted(team for team in band if rates[team] == best)

    return resolve


def _common_opponent_scorer(
    ledger: sos.ResumeLedger, semantics: sos.SosSemantics
) -> Callable[[str, str], tuple[float, float]]:
    from .common_opponents import governed_common_opponent_score

    def score(team_a: str, team_b: str) -> tuple[float, float]:
        left = governed_common_opponent_score(ledger, team_a, team_b, semantics)
        right = governed_common_opponent_score(ledger, team_b, team_a, semantics)
        return float(left.score or 0.0), float(right.score or 0.0)

    return score


def _bracket_winner(
    config: V3Config, path_id: int, frozen_strength: Mapping[str, float]
) -> Callable[[str, str, str], str]:
    """Simulate one bracket game at a neutral site, on frozen strength."""
    from .rng import deterministic_normal

    def pick(slot: str, team_a: str, team_b: str) -> str:
        margin = deterministic_normal(
            config.base_seed,
            frozen_strength[team_a] - frozen_strength[team_b],
            float(config.calibration.game_sd_points or 0.0),
            "CFP",
            path_id,
            slot,
            f"{team_a}-{team_b}",
        )
        return team_a if margin >= 0.0 else team_b

    return pick


def _season_outcomes(
    *,
    path_id: int,
    fbs_teams: Sequence[str],
    states: Mapping[str, TeamPathState],
    champions: Mapping[str, str],
    board: Sequence[str],
    selection: postseason.CFPSelection,
    bracket: Mapping[str, tuple[str, str, str]],
    frozen_strength: Mapping[str, float],
    ccg_participants: Sequence[str],
) -> list[TeamSeasonOutcome]:
    seed_of = {team: seed for seed, team in selection.seeds.items()}
    rank_of = {team: index + 1 for index, team in enumerate(board)}
    champion_set = set(champions.values())
    quarterfinalists = {
        winner for slot, (_a, _b, winner) in bracket.items() if slot.startswith("R1_")
    } | {selection.seeds[seed] for seed in postseason.BYE_SEEDS}
    semifinalists = {
        winner for slot, (_a, _b, winner) in bracket.items() if slot.startswith("QF_")
    }
    finalists = {
        winner for slot, (_a, _b, winner) in bracket.items() if slot.startswith("SEMI_")
    }
    national_champion = bracket["CHAMPIONSHIP"][2]

    out: list[TeamSeasonOutcome] = []
    for team in fbs_teams:
        state = states[team]
        out.append(
            TeamSeasonOutcome(
                path_id=path_id,
                schedule_id=team,
                regular_season_wins=state.wins,
                ccg_appearance=team in set(ccg_participants),
                conference_title=team in champion_set,
                cfp_selected=team in seed_of,
                cfp_bye=seed_of.get(team) in postseason.BYE_SEEDS,
                quarterfinal=team in quarterfinalists,
                semifinal=team in semifinalists,
                national_title_game=team in finalists,
                national_champion=team == national_champion,
                final_committee_rank=rank_of.get(team),
                final_strength_points=frozen_strength[team],
            )
        )
    return out


# ---------------------------------------------------------------------------
# Tier execution.
# ---------------------------------------------------------------------------

#: Governed universe counts. Checked on every tier rather than assumed from the
#: loader, because "the loader validates it" is exactly the assumption a
#: regression breaks silently.
GOVERNED_FBS_MEMBERS = 121
GOVERNED_SCHEDULE_ONLY_FCS = 13
GOVERNED_SCHEDULE_ENTITIES = 134
GOVERNED_CFP_FIELD_SIZE = 14

#: Per-path structural totals every aggregated probability column must reconcile
#: to. Each is a count that is the same on every path by construction — one
#: champion, fourteen selections, four byes — so summing the column across teams
#: must return it exactly. This is a much sharper check than a range test: a
#: bracket that advanced two teams out of one slot, or a selection that seeded a
#: team twice, changes a total here while leaving every individual value inside
#: [0, 1].
GOVERNED_COLUMN_TOTALS: dict[str, float] = {
    "cfp_pct": 14.0,
    "cfp_bye_pct": 4.0,
    "quarterfinal_pct": 8.0,
    "semifinal_pct": 4.0,
    "national_title_appearance_pct": 2.0,
    "national_title_win_pct": 1.0,
    "conference_title_pct": 9.0,
}

#: Every aggregated column that is a probability and must lie in [0, 1].
PROBABILITY_COLUMNS: tuple[str, ...] = (
    "ccg_appearance_pct",
    "conference_title_pct",
    "cfp_pct",
    "cfp_bye_pct",
    "quarterfinal_pct",
    "semifinal_pct",
    "national_title_appearance_pct",
    "national_title_win_pct",
)


def _canonical_digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
    ).hexdigest()


@dataclass(frozen=True)
class TierResult:
    """One tier's outputs and the checks they passed."""

    tier: str
    paths: int
    base_seed: int
    configuration_version: str
    parameter_set_hash: str
    input_manifest_hash: str
    team_summary: tuple[dict[str, object], ...]
    champion_probabilities: dict[str, float]
    output_hash: str
    validation: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            "tier": self.tier,
            "paths": self.paths,
            "base_seed": self.base_seed,
            "rng": "deterministic_normal keyed by (base_seed, semantic coordinates)",
            "configuration_version": self.configuration_version,
            "parameter_set_hash": self.parameter_set_hash,
            "input_manifest_hash": self.input_manifest_hash,
            "output_hash": self.output_hash,
            "validation": self.validation,
            "status": "COMPLETE" if self.validation["passed"] else "VALIDATION_FAILED",
        }


def parameter_set_hash(config: V3Config) -> str:
    """Digest of every value that can change a number, and nothing else.

    Path count is deliberately excluded: it changes how much of the same
    distribution is drawn and never what the distribution is, so a DEV and a
    PUBLISH run of the same model must share this hash. The tier is recorded
    separately, where it belongs.
    """
    return _canonical_digest(
        {
            "hfa_baseline_points": config.hfa_baseline_points,
            "fcs_translation_policy": config.fcs_translation_policy,
            "fcs_unified_points": fcs_policy.require_fcs_unified_points(),
            "first_promoted_rerating_after_week": (
                config.first_promoted_rerating_after_week
            ),
            "prior_decay": {str(k): v for k, v in sorted(config.prior_decay.items())},
            "freeze_strength_after_selection": config.freeze_strength_after_selection,
            "calibration": {
                "weekly_performance_residual_coefficient": (
                    config.calibration.weekly_performance_residual_coefficient
                ),
                "weekly_movement_cap_points": config.calibration.weekly_movement_cap_points,
                "recent_form_weights": list(config.calibration.recent_form_weights or ()),
                "blowout_treatment": config.calibration.blowout_treatment,
                "game_sd_points": config.calibration.game_sd_points,
                "sample_size_regularization": config.calibration.sample_size_regularization,
            },
        }
    )


def _validate_tier(
    *,
    teams: Mapping[str, Team],
    paths: Sequence[SeasonPath],
    champion_probabilities: Mapping[str, float],
    team_summary: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """The checks a tier must pass before its outputs may be reported.

    Each one is a property of the governed universe or of a probability, not a
    plausibility judgement about a football result. A surprising result is not a
    failure; an impossible one is.
    """
    findings: list[str] = []

    fbs = sorted(sid for sid, t in teams.items() if t.entity_scope == "FBS_MEMBER")
    schedule_only = sorted(
        sid for sid, t in teams.items() if t.entity_scope == "SCHEDULE_ONLY_FCS"
    )
    if len(fbs) != GOVERNED_FBS_MEMBERS:
        findings.append(f"{len(fbs)} FBS members, expected {GOVERNED_FBS_MEMBERS}")
    if len(schedule_only) != GOVERNED_SCHEDULE_ONLY_FCS:
        findings.append(
            f"{len(schedule_only)} schedule-only FCS entities, expected "
            f"{GOVERNED_SCHEDULE_ONLY_FCS}"
        )
    if len(teams) != GOVERNED_SCHEDULE_ENTITIES:
        findings.append(
            f"{len(teams)} schedule entities, expected {GOVERNED_SCHEDULE_ENTITIES}"
        )
    if set(fbs) & set(schedule_only):
        findings.append("an entity is both an FBS member and schedule-only FCS")
    if len(set(teams)) != len(teams):
        findings.append("duplicate team identity in the canonical universe")

    fcs_in_field = 0
    for path in paths:
        if len(path.cfp_seeds) != GOVERNED_CFP_FIELD_SIZE:
            findings.append(
                f"path {path.path_id} selected {len(path.cfp_seeds)} CFP teams"
            )
            break
        if sorted(path.cfp_seeds) != list(range(1, GOVERNED_CFP_FIELD_SIZE + 1)):
            findings.append(f"path {path.path_id} CFP seeds are not 1..14")
            break
        if len(set(path.cfp_seeds.values())) != GOVERNED_CFP_FIELD_SIZE:
            findings.append(f"path {path.path_id} seeded a team twice")
            break
        fcs_in_field += sum(1 for t in path.cfp_seeds.values() if t in set(schedule_only))
    if fcs_in_field:
        findings.append(f"{fcs_in_field} schedule-only FCS entities reached a CFP field")

    for team, probability in champion_probabilities.items():
        if not (0.0 <= probability <= 1.0):
            findings.append(f"{team} carries championship probability {probability}")
    total = sum(champion_probabilities.values())
    if abs(total - 1.0) > 1e-9:
        findings.append(f"championship probabilities sum to {total}, not 1")
    outside = sorted(set(champion_probabilities) - set(fbs))
    if outside:
        findings.append(f"non-FBS entities carry championship probability: {outside}")

    out_of_range = [
        (str(row["schedule_id"]), column, row[column])
        for row in team_summary
        for column in PROBABILITY_COLUMNS
        if not (0.0 <= float(row[column]) <= 1.0)
    ]
    if out_of_range:
        findings.append(f"probability outside [0, 1]: {out_of_range[:5]}")

    column_totals = {
        column: sum(float(row[column]) for row in team_summary)
        for column in GOVERNED_COLUMN_TOTALS
    }
    unreconciled = {
        column: (column_totals[column], expected)
        for column, expected in GOVERNED_COLUMN_TOTALS.items()
        if abs(column_totals[column] - expected) > 1e-9
    }
    if unreconciled:
        findings.append(f"column totals do not reconcile: {unreconciled}")

    if len(team_summary) != GOVERNED_FBS_MEMBERS:
        findings.append(
            f"team summary carries {len(team_summary)} rows, expected "
            f"{GOVERNED_FBS_MEMBERS}"
        )
    if len({str(row["schedule_id"]) for row in team_summary}) != len(team_summary):
        findings.append("team summary carries a duplicate team identity")

    return {
        "passed": not findings,
        "findings": findings,
        "fbs_members": len(fbs),
        "schedule_only_fcs": len(schedule_only),
        "schedule_entities": len(teams),
        "duplicate_team_identities": 0,
        "cfp_field_size_invariant": GOVERNED_CFP_FIELD_SIZE,
        "championship_probability_total": total,
        "probabilities_within_unit_interval": all(
            0.0 <= p <= 1.0 for p in champion_probabilities.values()
        ),
        "schedule_only_fcs_remained_non_fbs": fcs_in_field == 0,
        "team_summary_rows": len(team_summary),
        "probability_columns_within_unit_interval": not out_of_range,
        "governed_column_totals": {
            column: {"observed": column_totals[column], "expected": expected}
            for column, expected in sorted(GOVERNED_COLUMN_TOTALS.items())
        },
        "governed_column_totals_reconcile": not unreconciled,
    }


def run_tier(
    config: V3Config,
    root: Path,
    *,
    paths: int,
    output_dir: Path | None = None,
) -> TierResult:
    """Execute one governed tier end to end.

    The tier is derived from the path count by :func:`run_tier.tier_for_paths`,
    which refuses any count that is not one of the three governed ones. Preflight
    must come back with zero execution blockers; a run is not attempted otherwise.
    """
    from .aggregate import aggregate_team_outcomes
    from .manifest import build_input_manifest

    tier = tier_policy.tier_for_paths(paths)
    tier_config = replace(config, paths=paths)
    engine = DynamicWeeklyMCV3(
        tier_config, rerater=PromotedRegimeRerater.from_config(tier_config)
    )
    report = engine.preflight()
    blockers = list(report["execution_blockers"])  # type: ignore[arg-type]
    if blockers:
        raise GovernanceBlock(
            f"{tier.name} run refused: execution blockers remain — {', '.join(blockers)}"
        )

    teams = load_teams(
        tier_config.inputs.canonical_master_md,
        tier_config.inputs.unified_preseason_ratings_xlsx,
    )
    schedule = load_schedule(tier_config.inputs.schedule_xlsx)
    division_of = _aac_divisions(tier_config)
    semantics = sos.governed_sos_semantics(
        frozenset(
            sid for sid, t in teams.items() if t.entity_scope == "SCHEDULE_ONLY_FCS"
        )
    )

    season_paths: list[SeasonPath] = []
    outcomes: list[TeamSeasonOutcome] = []
    champions: dict[str, int] = {}
    for path_id in range(1, paths + 1):
        season = simulate_season_path(
            engine,
            path_id=path_id,
            teams=teams,
            schedule=schedule,
            division_of=division_of,
            semantics=semantics,
        )
        season_paths.append(season)
        outcomes.extend(season.outcomes)
        champions[season.national_champion] = champions.get(season.national_champion, 0) + 1

    summary = aggregate_team_outcomes(outcomes)
    preseason_of = {
        sid: team.preseason_strength_points for sid, team in teams.items()
    }
    for row in summary:
        row["preseason_strength"] = preseason_of[str(row["schedule_id"])]
    champion_probabilities = {
        team: champions.get(team, 0) / paths
        for team in sorted(sid for sid, t in teams.items() if t.entity_scope == "FBS_MEMBER")
    }
    validation = _validate_tier(
        teams=teams,
        paths=season_paths,
        champion_probabilities=champion_probabilities,
        team_summary=summary,
    )

    result = TierResult(
        tier=tier.name,
        paths=paths,
        base_seed=tier_config.base_seed,
        configuration_version=tier_config.configuration_version,
        parameter_set_hash=parameter_set_hash(tier_config),
        input_manifest_hash=_canonical_digest(
            build_input_manifest(tier_config, blockers)["input_files"]
        ),
        team_summary=tuple(summary),
        champion_probabilities=champion_probabilities,
        output_hash=_canonical_digest(
            {
                "team_summary": summary,
                "champion_probabilities": champion_probabilities,
            }
        ),
        validation=validation,
    )
    if output_dir is not None:
        _write_tier_outputs(result, output_dir, report)
    return result


def _aac_divisions(config: V3Config) -> dict[str, str]:
    path, _digest = require_governed_aac_divisions_csv(config.inputs.aac_divisions_csv)
    import csv

    out: dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            out[row["schedule_id"]] = row["division"]
    return out


def _write_tier_outputs(
    result: TierResult, output_dir: Path, preflight: Mapping[str, object]
) -> Path:
    """Emit a tier's evidence, LF-pinned throughout.

    The team summary is written as JSON rather than through
    :func:`outputs.write_csv`. That function emits :mod:`csv`'s CRLF terminator
    and documents that it may not be changed, while ``.gitattributes`` pins
    ``*.csv`` to ``eol=lf``. A committed run artifact that is rewritten with
    different bytes than it is checked out with would leave the working tree
    dirty after every re-run, which is the opposite of what a reproducibility
    artifact is for. Neither rule is bent: the artifact is simply not a CSV.
    """
    from .textio import write_json_lf

    destination = output_dir / result.tier
    destination.mkdir(parents=True, exist_ok=True)
    write_json_lf(
        destination / "team_summary.json",
        {
            "scope": mvp_control.MVP_SCOPE,
            "tier": result.tier,
            "paths": result.paths,
            "fields": list(result.team_summary[0]) if result.team_summary else [],
            "rows": [dict(row) for row in result.team_summary],
        },
    )
    write_json_lf(destination / "tier_result.json", result.as_dict())
    write_json_lf(
        destination / "championship_probabilities.json",
        {
            "scope": mvp_control.MVP_SCOPE,
            "calibration_evidence": mvp_control.MVP_CALIBRATION_STATUS,
            "real_world_validation": mvp_control.REAL_WORLD_VALIDATION_STATUS,
            "value_bearing": False,
            "probabilities": result.champion_probabilities,
        },
    )
    write_json_lf(destination / "preflight_report.json", dict(preflight))
    return destination
