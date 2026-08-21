from __future__ import annotations

from collections import defaultdict
from statistics import fmean

from .models import TeamSeasonOutcome, WeeklyStrengthSnapshot

TEAM_SUMMARY_FIELDS = [
    "schedule_id",
    "preseason_strength",
    "average_final_strength",
    "average_regular_season_wins",
    "ccg_appearance_pct",
    "conference_title_pct",
    "cfp_pct",
    "cfp_bye_pct",
    "quarterfinal_pct",
    "semifinal_pct",
    "national_title_appearance_pct",
    "national_title_win_pct",
    "average_final_committee_rank",
]


def aggregate_team_outcomes(outcomes: list[TeamSeasonOutcome]) -> list[dict[str, object]]:
    by_team: dict[str, list[TeamSeasonOutcome]] = defaultdict(list)
    for x in outcomes:
        by_team[x.schedule_id].append(x)
    rows: list[dict[str, object]] = []
    for sid in sorted(by_team):
        xs = by_team[sid]
        n = len(xs)
        ranks = [x.final_committee_rank for x in xs if x.final_committee_rank is not None]
        rows.append({
            "schedule_id": sid,
            "preseason_strength": None,  # joined from team input at output assembly
            "average_final_strength": fmean(x.final_strength_points for x in xs),
            "average_regular_season_wins": fmean(x.regular_season_wins for x in xs),
            "ccg_appearance_pct": sum(x.ccg_appearance for x in xs) / n,
            "conference_title_pct": sum(x.conference_title for x in xs) / n,
            "cfp_pct": sum(x.cfp_selected for x in xs) / n,
            "cfp_bye_pct": sum(x.cfp_bye for x in xs) / n,
            "quarterfinal_pct": sum(x.quarterfinal for x in xs) / n,
            "semifinal_pct": sum(x.semifinal for x in xs) / n,
            "national_title_appearance_pct": sum(x.national_title_game for x in xs) / n,
            "national_title_win_pct": sum(x.national_champion for x in xs) / n,
            "average_final_committee_rank": fmean(ranks) if ranks else None,
        })
    return rows


def aggregate_weekly_strength(snapshots: list[WeeklyStrengthSnapshot]) -> list[dict[str, object]]:
    buckets: dict[tuple[str, int], list[WeeklyStrengthSnapshot]] = defaultdict(list)
    for x in snapshots:
        buckets[(x.schedule_id, x.week_completed)].append(x)
    rows = []
    for (sid, week), xs in sorted(buckets.items()):
        rows.append({
            "schedule_id": sid,
            "week_completed": week,
            "average_strength": fmean(x.frozen_strength_points for x in xs),
            "preseason_strength": xs[0].preseason_strength_points,
            "prior_weight": xs[0].prior_weight,
            "audit_only": xs[0].audit_only,
            "paths": len(xs),
        })
    return rows


def conference_team_probability_rows(
    team_summary: list[dict[str, object]],
    conference_of: dict[str, str],
) -> list[dict[str, object]]:
    rows = []
    by_conf: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in team_summary:
        conf = conference_of[row["schedule_id"]]
        by_conf[conf].append(row)
    for conf in sorted(by_conf):
        xs = by_conf[conf]
        title_favorite = max(xs, key=lambda x: float(x["national_title_win_pct"] or 0.0))["schedule_id"]
        app_favorite = max(xs, key=lambda x: float(x["national_title_appearance_pct"] or 0.0))["schedule_id"]
        for x in sorted(xs, key=lambda r: r["schedule_id"]):
            rows.append({
                "conference": conf,
                "schedule_id": x["schedule_id"],
                "conference_title_pct": x["conference_title_pct"],
                "cfp_pct": x["cfp_pct"],
                "national_title_appearance_pct": x["national_title_appearance_pct"],
                "national_title_win_pct": x["national_title_win_pct"],
                "favorite_to_reach_national_title_game": x["schedule_id"] == app_favorite,
                "favorite_to_win_national_title": x["schedule_id"] == title_favorite,
            })
    return rows
