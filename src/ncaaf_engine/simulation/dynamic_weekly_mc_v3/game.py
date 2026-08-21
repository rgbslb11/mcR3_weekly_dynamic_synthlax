from __future__ import annotations

from .models import GameObservation, ScheduledGame, TeamPathState
from .rng import deterministic_normal


def simulate_game(
    *,
    base_seed: int,
    path_id: int,
    game: ScheduledGame,
    home: TeamPathState,
    away: TeamPathState,
    hfa_baseline_points: float,
    home_hfa_modifier: float,
    game_sd_points: float,
    rating_state_version: str,
) -> GameObservation:
    if game.home_team is None or game.away_team is None:
        raise ValueError("Cannot simulate an unresolved game template")
    hfa = 0.0 if game.venue == "NEUTRAL" else hfa_baseline_points * home_hfa_modifier
    expected = home.current_strength_points - away.current_strength_points + hfa
    simulated = deterministic_normal(
        base_seed,
        expected,
        game_sd_points,
        "REG_OR_POST",
        path_id,
        game.week,
        game.game_id,
    )
    # Deterministic no-tie resolution for continuous draws; exact zero is assigned home.
    home_won = simulated >= 0.0
    residual_home = simulated - expected
    return GameObservation(
        path_id=path_id,
        week=game.week,
        game_id=game.game_id,
        home_team=game.home_team,
        away_team=game.away_team,
        venue=game.venue,
        home_strength_points=home.current_strength_points,
        away_strength_points=away.current_strength_points,
        home_field_points=hfa,
        expected_home_margin=expected,
        simulated_home_margin=simulated,
        home_won=home_won,
        performance_residual_home=residual_home,
        performance_residual_away=-residual_home,
        rating_state_version=rating_state_version,
    )
