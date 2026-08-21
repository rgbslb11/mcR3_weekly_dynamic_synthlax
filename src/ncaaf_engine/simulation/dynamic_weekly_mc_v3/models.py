from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Venue = Literal["HOME", "NEUTRAL"]
EntityScope = Literal["FBS_MEMBER", "SCHEDULE_ONLY_FCS"]


@dataclass(frozen=True)
class Team:
    schedule_id: str
    team_name: str
    conference: str | None
    entity_scope: EntityScope
    championship_eligible: bool
    preseason_power_index: float | None
    preseason_strength_points: float | None
    hfa_modifier: float | None = None


@dataclass(frozen=True)
class ScheduledGame:
    game_id: str
    week: int
    date: str
    game_type: str
    home_team: str | None
    away_team: str | None
    home_conf: str | None
    away_conf: str | None
    venue: Venue
    conference_game: bool
    fcs_game: bool
    flex_rematch: bool
    venue_rule: str | None = None


@dataclass(frozen=True)
class GameObservation:
    path_id: int
    week: int
    game_id: str
    home_team: str
    away_team: str
    venue: Venue
    home_strength_points: float
    away_strength_points: float
    home_field_points: float
    expected_home_margin: float
    simulated_home_margin: float
    home_won: bool
    performance_residual_home: float
    performance_residual_away: float
    rating_state_version: str


@dataclass
class TeamPathState:
    schedule_id: str
    preseason_strength_points: float
    current_strength_points: float
    promoted_strength_points: float
    games_played: int = 0
    wins: int = 0
    losses: int = 0
    conference_wins: int = 0
    conference_losses: int = 0
    residual_history: list[float] = field(default_factory=list)


@dataclass(frozen=True)
class WeeklyStrengthSnapshot:
    path_id: int
    week_completed: int
    schedule_id: str
    preseason_strength_points: float
    frozen_strength_points: float
    promoted: bool
    prior_weight: float
    games_played: int
    audit_only: bool
    state_version: str


@dataclass(frozen=True)
class TeamSeasonOutcome:
    path_id: int
    schedule_id: str
    regular_season_wins: int
    ccg_appearance: bool
    conference_title: bool
    cfp_selected: bool
    cfp_bye: bool
    quarterfinal: bool
    semifinal: bool
    national_title_game: bool
    national_champion: bool
    final_committee_rank: int | None
    final_strength_points: float
