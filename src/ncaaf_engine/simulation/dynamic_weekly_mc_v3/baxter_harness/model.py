"""The experimental Baxter rerating model the harness scores regimes against.

This is an evaluation instrument, not a production rerater. Production weekly
rerating stays fail-closed in :mod:`..rerating` and this module is never loaded
by the V3 engine or CLI; it exists so a candidate regime can be given a number.

The recursion, week by week, in the only order it is ever run:

1. Predict every observation in the week from the rating state carried in from
   strictly earlier weeks. Nothing in the current week informs its own
   prediction, which is what makes a scored week out-of-sample.
2. Take each team's raw residual (observed team-relative margin minus predicted),
   pass it through the regime's blowout treatment, and average the week's
   treated residuals for that team.
3. Blend that against the team's earlier weekly residuals with the regime's
   recent-form weights, most recent first, renormalised over the weeks that
   actually exist so a team's third game is not scored as if it had twelve.
4. Scale by the residual coefficient and the sample-size shrink, clamp to the
   movement cap, and apply.

Ratings are seeded from ``pregame_team_rating`` at a team's first appearance and
evolve from there. A dataset without that column cannot seed, and the harness
blocks rather than inventing a starting rating.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

from ..errors import GovernanceBlock
from .observations import Observation, ObservationSet, _row_key
from .regime import ResolvedRegime


@dataclass(frozen=True)
class Prediction:
    """One out-of-sample prediction and what actually happened."""

    game_id: str
    season: int
    week: int
    team: str
    opponent: str
    split: str
    venue: str
    rating_team: float
    rating_opponent: float
    home_field_points: float
    predicted_margin: float
    actual_margin: float
    residual: float
    win_probability: float
    actual_win: bool | None
    baseline_expected_margin: float | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "game_id": self.game_id,
            "season": self.season,
            "week": self.week,
            "team": self.team,
            "opponent": self.opponent,
            "split": self.split,
            "predicted_margin": self.predicted_margin,
            "actual_margin": self.actual_margin,
            "residual": self.residual,
            "win_probability": self.win_probability,
        }


@dataclass(frozen=True)
class Movement:
    """One applied weekly rating change, for the movement diagnostic."""

    season: int
    week: int
    team: str
    delta: float
    uncapped_delta: float
    cap_binding: bool
    games_played: int
    shrink: float


@dataclass
class _TeamState:
    rating: float
    seed_rating: float
    games_played: int = 0
    weekly_residuals: list[float] = field(default_factory=list)


@dataclass(frozen=True)
class ModelRun:
    """Everything one regime produced over one observation set."""

    regime_id: str
    predictions: tuple[Prediction, ...]
    movements: tuple[Movement, ...]
    final_ratings: dict[str, float]
    seeded_teams: int
    home_field_points: float
    #: Directed rows per game. 2 means both sides of each game update; 1 means the
    #: dataset states one side only, so only that side's rating moves.
    directed_rows_per_game: float = 0.0

    def for_split(self, split: str) -> tuple[Prediction, ...]:
        return tuple(p for p in self.predictions if p.split == split)


def _standard_normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _venue_term(venue: str, home_field_points: float) -> float:
    if venue == "HOME":
        return home_field_points
    if venue == "AWAY":
        return -home_field_points
    return 0.0


def _weighted_recent(residuals: Sequence[float], weights: Sequence[float]) -> float:
    """Weight the most recent weeks first, renormalised over what exists."""
    available = min(len(residuals), len(weights))
    if available == 0:
        return 0.0
    used = [weights[i] for i in range(available)]
    total = math.fsum(used)
    if total <= 0.0:
        return 0.0
    return math.fsum(
        weight * residuals[-1 - i] for i, weight in enumerate(used)
    ) / total


def _seed_rating(observation: Observation, subject: str) -> float | None:
    if subject == observation.team:
        return observation.pregame_team_rating
    if subject == observation.opponent:
        return observation.pregame_opponent_rating
    return None


def run_model(
    observation_set: ObservationSet,
    regime: ResolvedRegime,
    *,
    home_field_points: float,
) -> ModelRun:
    """Run one regime over one observation set, deterministically.

    There is no randomness here and no dependence on wall-clock time or dict
    iteration order: observations are consumed in ``(season, week, game_id,
    team)`` order and every accumulation is over that fixed sequence.
    """
    observations = observation_set.observations
    if not observations:
        raise GovernanceBlock("Cannot run the Baxter model over an empty observation set.")

    states: dict[str, _TeamState] = {}
    unseedable: dict[str, int] = {}

    def ensure(subject: str, observation: Observation) -> _TeamState | None:
        state = states.get(subject)
        if state is not None:
            return state
        seed = _seed_rating(observation, subject)
        if seed is None:
            unseedable[subject] = unseedable.get(subject, 0) + 1
            return None
        states[subject] = _TeamState(rating=float(seed), seed_rating=float(seed))
        return states[subject]

    weights = regime.normalized_recent_form_weights
    predictions: list[Prediction] = []
    movements: list[Movement] = []

    week_keys: list[tuple[int, int]] = []
    for observation in observations:
        if not week_keys or week_keys[-1] != observation.time_key:
            week_keys.append(observation.time_key)

    skipped = 0
    index = 0
    for week_key in week_keys:
        week_rows: list[Observation] = []
        while index < len(observations) and observations[index].time_key == week_key:
            week_rows.append(observations[index])
            index += 1

        treated_by_team: dict[str, list[float]] = {}
        games_this_week: dict[str, int] = {}

        for observation in week_rows:
            team_state = ensure(observation.team, observation)
            opponent_state = ensure(observation.opponent, observation)
            if team_state is None or opponent_state is None:
                skipped += 1
                continue

            venue_points = _venue_term(observation.venue, home_field_points)
            predicted = team_state.rating - opponent_state.rating + venue_points
            residual = observation.actual_margin - predicted
            probability = _standard_normal_cdf(predicted / regime.game_sd_points)

            predictions.append(
                Prediction(
                    game_id=observation.game_id,
                    season=observation.season,
                    week=observation.week,
                    team=observation.team,
                    opponent=observation.opponent,
                    split=observation_set.split_of[_row_key(observation)],
                    venue=observation.venue,
                    rating_team=team_state.rating,
                    rating_opponent=opponent_state.rating,
                    home_field_points=venue_points,
                    predicted_margin=predicted,
                    actual_margin=observation.actual_margin,
                    residual=residual,
                    win_probability=probability,
                    actual_win=observation.actual_win,
                    baseline_expected_margin=observation.expected_margin,
                )
            )

            treated_by_team.setdefault(observation.team, []).append(
                regime.blowout_treatment.treat(residual)
            )
            games_this_week[observation.team] = games_this_week.get(observation.team, 0) + 1

        for team in sorted(treated_by_team):
            state = states[team]
            state.games_played += games_this_week[team]
            state.weekly_residuals.append(
                math.fsum(treated_by_team[team]) / len(treated_by_team[team])
            )

            blended = _weighted_recent(state.weekly_residuals, weights)
            shrink = regime.sample_size_regularization.shrink(state.games_played)
            uncapped = regime.residual_coefficient * shrink * blended
            delta = max(-regime.movement_cap_points, min(regime.movement_cap_points, uncapped))

            state.rating += delta
            movements.append(
                Movement(
                    season=week_key[0],
                    week=week_key[1],
                    team=team,
                    delta=delta,
                    uncapped_delta=uncapped,
                    cap_binding=abs(uncapped) > regime.movement_cap_points,
                    games_played=state.games_played,
                    shrink=shrink,
                )
            )

    if skipped:
        raise GovernanceBlock(
            f"{skipped} observation(s) could not be predicted because a team carried no "
            f"pregame rating at its first appearance (teams: {sorted(unseedable)[:5]}). "
            "Scoring the remainder would report a metric over a silently reduced sample, so "
            "the run is refused rather than partially reported."
        )
    if not predictions:
        raise GovernanceBlock("No observation could be predicted from this observation set.")

    return ModelRun(
        regime_id=regime.regime_id,
        predictions=tuple(predictions),
        movements=tuple(movements),
        final_ratings={team: state.rating for team, state in sorted(states.items())},
        seeded_teams=len(states),
        home_field_points=home_field_points,
        directed_rows_per_game=len(predictions) / len({p.game_id for p in predictions}),
    )
