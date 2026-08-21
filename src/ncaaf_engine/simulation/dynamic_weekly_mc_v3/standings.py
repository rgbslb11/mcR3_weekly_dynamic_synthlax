from __future__ import annotations

from dataclasses import dataclass

from .errors import GovernanceBlock
from .models import GameObservation, ScheduledGame


@dataclass(frozen=True)
class Standing:
    team: str
    conference_wins: int
    conference_losses: int

    @property
    def conference_win_pct(self) -> float:
        games = self.conference_wins + self.conference_losses
        return self.conference_wins / games if games else 0.0


def build_conference_standings(
    conference: str,
    team_ids: list[str],
    schedule_by_game: dict[str, ScheduledGame],
    observations: list[GameObservation],
) -> dict[str, Standing]:
    w = {t: 0 for t in team_ids}
    l = {t: 0 for t in team_ids}
    for obs in observations:
        game = schedule_by_game[obs.game_id]
        if not game.conference_game or game.game_type != "REG":
            continue
        if game.home_conf != conference or game.away_conf != conference:
            continue
        winner = obs.home_team if obs.home_won else obs.away_team
        loser = obs.away_team if obs.home_won else obs.home_team
        if winner in w and loser in l:
            w[winner] += 1
            l[loser] += 1
    return {t: Standing(t, w[t], l[t]) for t in team_ids}


def _head_to_head_score(team: str, tied: set[str], observations: list[GameObservation], schedule_by_game: dict[str, ScheduledGame]) -> tuple[int, int]:
    wins = losses = 0
    for obs in observations:
        if {obs.home_team, obs.away_team}.issubset(tied):
            game = schedule_by_game[obs.game_id]
            if not game.conference_game:
                continue
            winner = obs.home_team if obs.home_won else obs.away_team
            loser = obs.away_team if obs.home_won else obs.home_team
            if winner == team:
                wins += 1
            elif loser == team:
                losses += 1
    return wins, losses


def rank_tied_group_current_rule(
    tied: list[str],
    observations: list[GameObservation],
    schedule_by_game: dict[str, ScheduledGame],
    terminal_board_rank: dict[str, int],
) -> list[str]:
    """Implements the currently locked minimal chain: H2H -> mini-RR -> terminal board.

    This deliberately does not implement the open ACC restart/sweep proposal.
    """
    tied_set = set(tied)
    scores = {t: _head_to_head_score(t, tied_set, observations, schedule_by_game) for t in tied}
    # TB-1: for a two-team tie, direct H2H is decisive if played.
    if len(tied) == 2:
        a, b = tied
        aw, al = scores[a]
        bw, bl = scores[b]
        if aw + al == 1 and bw + bl == 1 and aw != bw:
            return [a, b] if aw > bw else [b, a]
    # TB-2: mini-round-robin win percentage among tied teams.
    def mini_pct(t: str) -> float:
        ww, ll = scores[t]
        n = ww + ll
        return ww / n if n else -1.0
    pcts = {t: mini_pct(t) for t in tied}
    if len(set(pcts.values())) > 1:
        return sorted(tied, key=lambda t: (-pcts[t], terminal_board_rank[t]))
    # TB-3: terminal committee board.
    missing = [t for t in tied if t not in terminal_board_rank]
    if missing:
        raise GovernanceBlock(f"Terminal board rank missing for tiebreak teams: {missing}")
    return sorted(tied, key=lambda t: terminal_board_rank[t])


def select_top_two_current_rule(
    standings: dict[str, Standing],
    observations: list[GameObservation],
    schedule_by_game: dict[str, ScheduledGame],
    pre_ccg_board_rank: dict[str, int],
) -> list[str]:
    by_pct: dict[float, list[str]] = {}
    for t, s in standings.items():
        by_pct.setdefault(s.conference_win_pct, []).append(t)
    ordered: list[str] = []
    for pct in sorted(by_pct, reverse=True):
        group = by_pct[pct]
        if len(group) == 1:
            ordered.extend(group)
        else:
            ordered.extend(rank_tied_group_current_rule(group, observations, schedule_by_game, pre_ccg_board_rank))
    return ordered[:2]
