from __future__ import annotations

from pathlib import Path

from . import fcs as fcs_policy
from . import aac_divisions, board_of_record, ccg, hfa as hfa_policy, ordering, schedule_exceptions, sos
from .config import V3Config
from .errors import GovernanceBlock, InputValidationError
from .game import simulate_game
from .inputs import load_fcs_operator_rows, load_schedule, load_teams, validate_schedule
from .manifest import write_manifest
from .governance import (
    governance_blockers,
    inspect_bracket,
    inspect_fcs_authority,
    inspect_model_parameters,
    inspect_playoff_calendar,
)
from .phase_plan import validate_phase_plan
from .rulings import R2_RULINGS
from .models import GameObservation, Team, TeamPathState, WeeklyStrengthSnapshot
from .rerating import BlockedGovernedRerater, WeeklyRerater


class DynamicWeeklyMCV3:
    def __init__(self, config: V3Config, rerater: WeeklyRerater | None = None) -> None:
        self.config = config
        self.rerater = rerater or BlockedGovernedRerater()

    def preflight(self) -> dict[str, object]:
        self.config.validate_architecture()
        required_paths = [
            self.config.inputs.canonical_master_md,
            self.config.inputs.unified_preseason_ratings_xlsx,
            self.config.inputs.schedule_xlsx,
            self.config.inputs.model_parameters_xlsx,
            self.config.inputs.bracket_regime_xlsx,
            self.config.inputs.playoff_calendar_xlsx,
            self.config.inputs.fcs_reconciled_master_xlsx,
            self.config.inputs.v2_1_control_xlsx,
        ]
        missing = [str(p) for p in required_paths if not p.exists()]
        if missing:
            raise InputValidationError("Missing required mounted inputs: " + ", ".join(missing))

        teams = load_teams(
            self.config.inputs.canonical_master_md,
            self.config.inputs.unified_preseason_ratings_xlsx,
        )
        schedule_report = validate_schedule(self.config.inputs.schedule_xlsx, teams)
        schedule = load_schedule(self.config.inputs.schedule_xlsx)
        fcs = load_fcs_operator_rows(self.config.inputs.fcs_reconciled_master_xlsx)
        if set(fcs) != {sid for sid, t in teams.items() if t.entity_scope == "SCHEDULE_ONLY_FCS"}:
            raise InputValidationError("FCS operator source does not match canonical 13-team exception set")

        validate_phase_plan()
        phase_counts = {
            "preselection_regular_w1_w14": sum(g.game_type == "REG" and 1 <= g.week <= 14 for g in schedule),
            "conference_championship_templates_w15": sum(g.game_type == "CCG" and g.week == 15 for g in schedule),
            "postselection_regular_w16": sum(g.game_type == "REG" and g.week == 16 for g in schedule),
        }
        week16 = [g for g in schedule if g.game_type == "REG" and g.week == 16]
        if len(week16) != 1 or {week16[0].home_team, week16[0].away_team} != {"ARMY", "NAVY"}:
            raise InputValidationError("Week 16 post-selection phase must contain exactly Army-Navy")

        governed = {
            "model_parameters": inspect_model_parameters(self.config.inputs.model_parameters_xlsx),
            "bracket": inspect_bracket(self.config.inputs.bracket_regime_xlsx),
            "playoff_calendar": inspect_playoff_calendar(self.config.inputs.playoff_calendar_xlsx),
            "fcs_authority": inspect_fcs_authority(self.config.inputs.fcs_reconciled_master_xlsx),
        }

        # R2 convergence evidence. Every flag is the result of a deterministic
        # check against the mounted artifacts, never of a ruling being quoted.
        thirteen_game = schedule_exceptions.validate_13_game_exceptions(schedule)
        ccg_report = ccg.verify_seven_ccgs(schedule)
        aac_status = aac_divisions.aac_artifact_status(self.config.inputs.aac_divisions_csv)
        board_status = board_of_record.board_of_record_status(
            self.config.inputs.board_of_record_xlsx
        )
        r2_evidence = {
            "rulings_applied": [r.convergence_id for r in R2_RULINGS],
            "hfa": hfa_policy.as_dict(),
            "fcs": fcs_policy.GOVERNED_FCS_POLICY.as_dict(),
            "thirteen_game_exceptions": thirteen_game,
            "seven_ccgs": ccg_report,
            "aac_divisions_artifact": aac_status,
            "board_of_record": board_status,
            "a8_ecl_ordering": ordering.resolution_as_dict(),
            "sos_semantics_governed": sos.GOVERNED_SOS_SEMANTICS is not None,
        }

        blockers = self.config.execution_blockers() + [
            f"provenance.{x}" for x in schedule_report.get("blocking_provenance_anomalies", [])
        ] + governance_blockers(
            model_parameters=governed["model_parameters"],
            bracket=governed["bracket"],
            playoff_calendar=governed["playoff_calendar"],
            fcs=governed["fcs_authority"],
            hfa_ruling_applied=hfa_policy.hfa_conflict_resolved(self.config.hfa_baseline_points),
            fcs_ruling_applied=(
                self.config.fcs_translation_policy == fcs_policy.FCS_FIXED_ELO_POLICY
            ),
            thirteen_game_exceptions_validated=bool(thirteen_game["validated"]),
            a8_ecl_ordering_resolved=ordering.a8_ecl_ordering_resolved(),
            sos_semantics_governed=sos.GOVERNED_SOS_SEMANTICS is not None,
            fcs_unified_scale_governed=(
                fcs_policy.GOVERNED_FCS_POLICY.unified_points_equivalent is not None
            ),
        )
        if aac_status["blocker"]:
            blockers.append(str(aac_status["blocker"]))
        # Stable order, no duplicate control labels.
        blockers = list(dict.fromkeys(blockers))
        return {
            "status": "STRUCTURAL_PREFLIGHT_PASS",
            "model": self.config.model_name,
            "model_version": self.config.model_version,
            "configuration_version": self.config.configuration_version,
            "paths": self.config.paths,
            "base_seed": self.config.base_seed,
            "team_entities": len(teams),
            "fbs_members": sum(t.entity_scope == "FBS_MEMBER" for t in teams.values()),
            "schedule_only_fcs": sum(t.entity_scope == "SCHEDULE_ONLY_FCS" for t in teams.values()),
            "schedule": schedule_report,
            "schedule_phases": phase_counts,
            "governed_evidence": governed,
            "r2_governance": r2_evidence,
            "execution_blockers": blockers,
            "authority": "EXPERIMENTAL / NOT CANONICAL / V2.1 CONTROL UNCHANGED",
        }


    def require_execution_ready(self) -> dict[str, object]:
        report = self.preflight()
        blockers = report["execution_blockers"]
        if blockers:
            raise GovernanceBlock("V3 execution blocked: " + ", ".join(str(x) for x in blockers))
        return report

    def _initialize_states(self, teams: dict[str, Team]) -> dict[str, TeamPathState]:
        states: dict[str, TeamPathState] = {}
        for sid, team in teams.items():
            if team.preseason_strength_points is None:
                raise GovernanceBlock(
                    f"{sid} has no unified preseason strength points. Exact governed FCS-to-unified translation must be configured."
                )
            states[sid] = TeamPathState(
                schedule_id=sid,
                preseason_strength_points=team.preseason_strength_points,
                current_strength_points=team.preseason_strength_points,
                promoted_strength_points=team.preseason_strength_points,
            )
        return states

    def simulate_preselection_regular_season_path(
        self,
        *,
        path_id: int,
        teams: dict[str, Team],
        schedule: list,
    ) -> tuple[list[GameObservation], list[WeeklyStrengthSnapshot]]:
        self.config.require_executable()
        assert self.config.hfa_baseline_points is not None
        assert self.config.calibration.game_sd_points is not None
        states = self._initialize_states(teams)
        observations: list[GameObservation] = []
        snapshots: list[WeeklyStrengthSnapshot] = []
        regular = [g for g in schedule if g.game_type == "REG"]

        # Production phase contract: this helper stops at W14. W15 CCGs are
        # governed separately; selection freezes football strength; W16 Army-Navy
        # is simulated post-selection without a rerating promotion.
        for week in range(1, 15):
            weekly_games = [g for g in regular if g.week == week]
            weekly_residuals: dict[str, list[float]] = {sid: [] for sid in states}
            state_version = f"path-{path_id:05d}:week-{week:02d}:OPEN"

            for game in weekly_games:
                if game.home_team is None or game.away_team is None:
                    raise InputValidationError(f"Regular game {game.game_id} has unresolved participants")
                home = states[game.home_team]
                away = states[game.away_team]
                home_team = teams[game.home_team]
                obs = simulate_game(
                    base_seed=self.config.base_seed,
                    path_id=path_id,
                    game=game,
                    home=home,
                    away=away,
                    hfa_baseline_points=self.config.hfa_baseline_points,
                    home_hfa_modifier=float(home_team.hfa_modifier or 1.0),
                    game_sd_points=self.config.calibration.game_sd_points,
                    rating_state_version=state_version,
                )
                observations.append(obs)
                weekly_residuals[obs.home_team].append(obs.performance_residual_home)
                weekly_residuals[obs.away_team].append(obs.performance_residual_away)

                winner = home if obs.home_won else away
                loser = away if obs.home_won else home
                winner.wins += 1
                loser.losses += 1
                home.games_played += 1
                away.games_played += 1
                if game.conference_game:
                    winner.conference_wins += 1
                    loser.conference_losses += 1

            for sid, state in states.items():
                vals = weekly_residuals[sid]
                state.residual_history.append(sum(vals) / len(vals) if vals else 0.0)

            candidate = self.rerater.rerate(week_completed=week, states=states, config=self.config)
            audit_only = self.config.audit_only_after_week(week)
            prior_weight = self.config.prior_weight_after_week(week)
            for sid, new_strength in candidate.items():
                snapshots.append(
                    WeeklyStrengthSnapshot(
                        path_id=path_id,
                        week_completed=week,
                        schedule_id=sid,
                        preseason_strength_points=states[sid].preseason_strength_points,
                        frozen_strength_points=new_strength,
                        promoted=not audit_only,
                        prior_weight=prior_weight,
                        games_played=states[sid].games_played,
                        audit_only=audit_only,
                        state_version=f"path-{path_id:05d}:after-week-{week:02d}",
                    )
                )
                if not audit_only:
                    states[sid].promoted_strength_points = new_strength
                    states[sid].current_strength_points = new_strength
                # W1 remains preseason opening strength for W2 by governance.

        return observations, snapshots

    def simulate_regular_season_path(
        self,
        *,
        path_id: int,
        teams: dict[str, Team],
        schedule: list,
    ) -> tuple[list[GameObservation], list[WeeklyStrengthSnapshot]]:
        """Compatibility alias for the pre-selection W1-W14 test harness.

        It intentionally does not simulate W15 CCGs, selection, W16 Army-Navy,
        or playoffs. The production CLI remains fail-closed until those governed
        phases and calibration inputs are fully activated.
        """
        return self.simulate_preselection_regular_season_path(
            path_id=path_id, teams=teams, schedule=schedule
        )

    def validate_to_directory(self, output_dir: Path) -> dict[str, object]:
        report = self.preflight()
        write_manifest(self.config, output_dir, report["execution_blockers"])
        import json
        (output_dir / "preflight_report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
        )
        return report
