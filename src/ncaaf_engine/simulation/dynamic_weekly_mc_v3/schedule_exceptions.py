"""Deterministic validation of the approved 13-game regular-season schedules.

Ruling R2-SCHED-13GAME approves ARK, GAST, UK, VAN and WVU to play 13 regular
season games. The ruling is the authority; this module is the check that the
mounted schedule actually contains what was approved, and nothing else.

Approving an exception is not the same as trusting the rows. Four failure modes
would each produce a "13-game team" that the Chairman did not approve, so each
is tested for separately:

* a team reaching 13 by counting a W15 CCG template row, which has no participants;
* a duplicated ``game_id``;
* the same opponent on the same date twice;
* any *other* team drifting to 13 games without an approval.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .errors import GovernanceBlock, InputValidationError
from .rulings import R2_THIRTEEN_GAME_EXCEPTIONS

#: FACT — 12_OPEN_ITEMS OI-SCHED-13, and the set approved by R2-SCHED-13GAME.
APPROVED_13_GAME_TEAMS: tuple[str, ...] = ("ARK", "GAST", "UK", "VAN", "WVU")

APPROVED_REGULAR_SEASON_GAMES = 13
STANDARD_REGULAR_SEASON_GAMES = 12

#: Regular-season weeks. W15 is CCG templates; W16 is the post-selection
#: Army-Navy game and is not part of the 13-game question.
REGULAR_SEASON_WEEKS = range(1, 15)


@dataclass(frozen=True)
class TeamScheduleAudit:
    schedule_id: str
    regular_season_games: int
    game_ids: tuple[str, ...]
    opponents: tuple[str, ...]
    approved: bool

    @property
    def is_thirteen_game(self) -> bool:
        return self.regular_season_games == APPROVED_REGULAR_SEASON_GAMES


def audit_regular_season_counts(schedule: list) -> dict[str, TeamScheduleAudit]:
    """Count W1-W14 REG appearances per team, ignoring CCG templates entirely."""
    rows: dict[str, list] = {}
    for game in schedule:
        if game.game_type != "REG" or game.week not in REGULAR_SEASON_WEEKS:
            continue
        for side in (game.home_team, game.away_team):
            if side:
                rows.setdefault(side, []).append(game)

    audits: dict[str, TeamScheduleAudit] = {}
    for sid, games in rows.items():
        ordered = sorted(games, key=lambda g: g.game_id)
        opponents = tuple(
            (g.away_team if g.home_team == sid else g.home_team) or "" for g in ordered
        )
        audits[sid] = TeamScheduleAudit(
            schedule_id=sid,
            regular_season_games=len(ordered),
            game_ids=tuple(g.game_id for g in ordered),
            opponents=opponents,
            approved=sid in APPROVED_13_GAME_TEAMS,
        )
    return audits


def validate_13_game_exceptions(schedule: list) -> dict[str, object]:
    """Validate the five approved schedules deterministically.

    Raises rather than returning a soft verdict: a 13-game schedule that does not
    validate must not be able to reach the ruling's clearance path.
    """
    ccg_rows = [g for g in schedule if g.game_type == "CCG"]
    for game in ccg_rows:
        if game.home_team is not None or game.away_team is not None:
            raise InputValidationError(
                f"CCG template {game.game_id} carries resolved participants; a template row "
                "must never be countable as a regular-season game"
            )

    # Duplicate opponent/date artefacts, checked across the whole schedule so a
    # doubled row cannot hide behind a team that was not part of the exception.
    seen: dict[tuple[str, str, str], str] = {}
    for game in schedule:
        if game.game_type != "REG" or game.week not in REGULAR_SEASON_WEEKS:
            continue
        if not game.home_team or not game.away_team:
            continue
        key = (game.date, *sorted((game.home_team, game.away_team)))
        if key in seen:
            raise InputValidationError(
                f"Duplicate opponent/date artefact: {game.game_id} repeats {seen[key]} "
                f"({key[1]} vs {key[2]} on {key[0]})"
            )
        seen[key] = game.game_id

    audits = audit_regular_season_counts(schedule)

    missing = [t for t in APPROVED_13_GAME_TEAMS if t not in audits]
    if missing:
        raise InputValidationError(f"Approved 13-game teams absent from the schedule: {missing}")

    wrong_count = {
        t: audits[t].regular_season_games
        for t in APPROVED_13_GAME_TEAMS
        if audits[t].regular_season_games != APPROVED_REGULAR_SEASON_GAMES
    }
    if wrong_count:
        raise InputValidationError(
            f"Approved 13-game teams do not carry exactly {APPROVED_REGULAR_SEASON_GAMES} "
            f"regular-season rows: {wrong_count}"
        )

    # No team may reach 13 without an approval.
    unapproved = sorted(
        a.schedule_id
        for a in audits.values()
        if a.regular_season_games > STANDARD_REGULAR_SEASON_GAMES and not a.approved
    )
    if unapproved:
        raise InputValidationError(
            f"Teams exceed {STANDARD_REGULAR_SEASON_GAMES} regular-season games without an "
            f"approved exception: {unapproved}"
        )

    for team in APPROVED_13_GAME_TEAMS:
        audit = audits[team]
        duplicate_ids = sorted({g for g, n in Counter(audit.game_ids).items() if n > 1})
        if duplicate_ids:
            raise InputValidationError(f"{team} has duplicate game_id rows: {duplicate_ids}")

    return {
        "ruling": R2_THIRTEEN_GAME_EXCEPTIONS.convergence_id,
        "approved_teams": list(APPROVED_13_GAME_TEAMS),
        "regular_season_games_each": APPROVED_REGULAR_SEASON_GAMES,
        "ccg_template_rows_excluded": len(ccg_rows),
        "teams_at_thirteen_games": sorted(
            a.schedule_id for a in audits.values() if a.is_thirteen_game
        ),
        "duplicate_game_ids": [],
        "duplicate_opponent_date_artifacts": [],
        "validated": True,
    }


def thirteen_game_exceptions_cleared(schedule: list) -> bool:
    """True only when the ruling is present *and* the schedule validates."""
    try:
        validate_13_game_exceptions(schedule)
    except (InputValidationError, GovernanceBlock):
        return False
    return True
