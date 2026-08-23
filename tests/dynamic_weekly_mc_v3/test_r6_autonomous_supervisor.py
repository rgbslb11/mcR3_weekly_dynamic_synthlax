"""R6 -- the autonomous V3 model-run supervisor.

The supervisor's job is to be trusted to run unattended, so what these tests
prove is mostly what it *refuses*: a stage it cannot skip, a holdout it cannot
peek at or re-score, an approval it cannot reuse, a parameter it cannot fit, a
witness that cannot move the answer, and a tier that cannot proceed on the
failure of the one before it.

Everything numerical is driven through a deterministic fake executor. That is
the design, not a testing shortcut: the supervisor implements no model
mathematics, so a fake that returns fixed answers exercises exactly the code
that will run in production. No real calibration and no season simulation
happens here, and none may.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import supervisor_support as SUP

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import run_tier as tier_policy
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.errors import (
    GovernanceBlock,
    InputValidationError,
)
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.supervisor import (
    cli,
    convergence as CV,
    evidence as EV,
    gates,
    holdout as HO,
    retry as RETRY,
    search as SEARCH,
    states as S,
    witness as W,
)
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.supervisor.approval import (
    APPROVAL_ACTION,
)
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.supervisor.execution import (
    DatasetBinding,
    ModelRunExecutor,
    UnmountedEvidenceExecutor,
)
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.supervisor.runstore import (
    RunLock,
    RunState,
    atomic_write_json,
)
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.supervisor.supervisor import (
    STAGE_COARSE_SEARCH,
    STAGE_FOR_STATE,
    Supervisor,
    SupervisorConfig,
)

# --- fixtures ----------------------------------------------------------------

_SCALAR_AXIS = {
    "lower": 0.0,
    "upper": 1.0,
    "points": 5,
    "max_expansions": 2,
    "expansion_factor": 2.0,
    "refinement_rounds": 1,
    "refinement_points": 3,
}


def _fit(**overrides):
    entry = {
        "eligibility": EV.FIT_ALLOWED,
        "circularity": EV.INDEPENDENT_OF_MECHANISM,
        "evidence_fields": ["synthetic_2024.margin", "synthetic_2025.margin"],
        "rationale": "Independent of the mechanism under estimation.",
        "search_space": dict(_SCALAR_AXIS),
    }
    entry.update(overrides)
    return entry


def _fixed(value, **overrides):
    entry = {
        "eligibility": EV.FIXED,
        "circularity": EV.INDEPENDENT_OF_MECHANISM,
        "evidence_fields": [],
        "rationale": "Governed value carried forward.",
        "current_value": value,
    }
    entry.update(overrides)
    return entry


def manifest_payload(**overrides):
    """A valid frozen evidence manifest, as a plain dict, for a test to edit."""
    payload = {
        "manifest_id": "V3-SYNTHETIC-EVIDENCE-TEST-R6",
        "primary_estimation_domain": list(EV.PRIMARY_ESTIMATION_DOMAIN),
        "projection_season": EV.PRIMARY_PROJECTION_SEASON,
        "real_witness": {
            "sha256": EV.REAL_WITNESS_CORPUS_SHA256,
            "role": EV.EXTERNAL_WITNESS_ONLY,
        },
        "point_scale": {
            "resolution": EV.POINT_SCALE_FIXED_EXISTING_VALUE,
            "value": EV.GOVERNED_POINT_SCALE_POINTS_PER_SD,
            "rationale": "Governed unified-axis scale carried forward unchanged.",
        },
        "parameters": {
            "weekly_performance_residual_coefficient": _fit(),
            "weekly_movement_cap_points": _fit(),
            "recent_form_weights": _fixed([0.5, 0.3, 0.2]),
            "blowout_treatment": _fixed({"cap_margin": 28}),
            "sample_size_regularization": _fixed({"k": 4}),
            "game_sd_points": _fit(),
            "point_scale": _fixed(EV.GOVERNED_POINT_SCALE_POINTS_PER_SD),
            "fcs_point_adapter": _fit(),
        },
    }
    payload.update(overrides)
    return payload


def write_manifest(tmp_path: Path, payload=None) -> Path:
    path = tmp_path / "synthetic_evidence_manifest.json"
    atomic_write_json(path, payload or manifest_payload())
    return path


def _tier_report(paths: int, bindings, aggregates=None, **overrides):
    report = {
        "requested_paths": paths,
        "observed_paths": paths,
        "seed": {
            "base_seed": 20260101,
            "replay_digest": "seedreplay",
            "reference_digest": "seedreplay",
        },
        "numeric": {"nan_count": 0, "inf_count": 0},
        "probabilities": {
            "min": 0.0,
            "max": 1.0,
            "mass_checks": [{"name": "champion", "sum": 1.0}],
            "mass_tolerance": 1e-9,
        },
        "team_identities": {"expected": 134, "observed": 134, "unknown": []},
        "standings": {"violations": [], "tiebreak_violations": []},
        "ccg": {"violations": []},
        "cfp": {
            "violations": [],
            "duplicate_participants": [],
            "postseason_topology_violations": [],
        },
        "assertions": {"failed": []},
        "artifacts": {
            "required": ["summary.json"],
            "present": ["summary.json"],
            "hashes": {"summary.json": "a" * 64},
        },
        # R2 reports say what each number is. A binomial standard error is only
        # correct for a path fraction, so the kind is declared rather than
        # guessed from the value.
        "quantities": {
            name: {"kind": CV.BERNOULLI_PROBABILITY, "value": value, "paths": paths}
            for name, value in dict(
                aggregates or {"champion_probability_top1": 0.10}
            ).items()
        },
        "schema": {
            "required_fields": ["team", "champion_probability"],
            "present_fields": ["team", "champion_probability"],
        },
        "totals": {"champion": 1.0, "conference": 1.0, "cfp": 1.0},
        "totals_tolerance": 1e-9,
        "bindings": dict(bindings),
    }
    report.update(overrides)
    return report


class FakeExecutor(ModelRunExecutor):
    """Deterministic stand-in for the governed model interfaces.

    The objective is a strictly convex quadratic with an interior minimum, so a
    coarse grid finds a non-boundary optimum and the boundary machinery is
    exercised only by tests that deliberately ask for it.
    """

    name = "FAKE"

    def __init__(
        self,
        *,
        optimum=0.5,
        cap_binding_events=3,
        witness_divergence=0.01,
        fail_tier=None,
        holdout_peek=False,
        witness_mutates=False,
        fcs_identified=True,
        aggregates=None,
    ) -> None:
        self.optimum = optimum
        self.cap_binding_events = cap_binding_events
        self.witness_divergence = witness_divergence
        self.fail_tier = fail_tier
        self.holdout_peek = holdout_peek
        self.witness_mutates = witness_mutates
        self.fcs_identified = fcs_identified
        self.aggregates = aggregates or {}
        self.tier_calls: list[str] = []
        self.bound_oracle: SEARCH.ScoringOracle | None = None

    def calibration_dataset(self) -> DatasetBinding:
        return DatasetBinding(
            dataset_id="SYNTHETIC_2024_2025_ESTIMATION_TABLE",
            sha256="d" * 64,
            split_sha256="s" * 64,
            experiment_config_sha256="e" * 64,
            input_manifest_digest="i" * 64,
            rows=2400,
            distinct_seasons=3,
            holdout_rows=420,
            minimum_weeks_per_team_per_season=10,
            estimation_domain=EV.PRIMARY_ESTIMATION_DOMAIN,
        )

    def preflight(self):
        return {
            "status": "STRUCTURAL_PREFLIGHT_PASS",
            "execution_blockers": ["calibration.game_sd_points"],
        }

    def bind_oracle(self, oracle):
        self.bound_oracle = oracle

    def scoring_oracle(self) -> SEARCH.ScoringOracle:
        def _fn(candidate, split):
            base = 0.0
            for name in ("weekly_performance_residual_coefficient", "weekly_movement_cap_points"):
                value = candidate.get(name)
                if value is not None:
                    base += (float(value) - self.optimum) ** 2
            return 1.0 + base

        return SEARCH.ScoringOracle(
            oracle_id="FAKE_RMSE", fn=_fn, implementation_digest="o" * 64
        )

    def finalists(self, vector):
        if self.holdout_peek:
            # A worker scoring its own candidates against the holdout while
            # selection is still running.
            self.bound_oracle.score(vector, split="holdout")
        return [
            SEARCH.FinalistObservation(
                candidate_id=f"C{i}",
                score=1.0,
                constraint_value=0.5 + i,
                constraint_binding_events=self.cap_binding_events,
            )
            for i in range(3)
        ]

    def sensitivity(self, vector):
        return {name: {"local_curvature": 2.0} for name in vector}

    def validate(self, vector):
        return {"split": "validation", "out_of_sample_baxter_rating_rmse": 1.20}

    def score_holdout(self, vector):
        return {"split": "holdout", "out_of_sample_baxter_rating_rmse": 1.24}

    def game_sd(self, vector, holdout_evidence):
        return {"identification_status": SEARCH.IDENTIFIED, "value": 16.8}

    def fcs_adapter(self, vector):
        if self.fcs_identified:
            return {"identification_status": SEARCH.IDENTIFIED, "value": 2.5}
        return {
            "identification_status": SEARCH.PARAMETER_UNIDENTIFIED,
            "rationale": "No admissible route from Elo 1250 onto the unified axis.",
        }

    def witness(self, vector):
        if self.witness_mutates:
            vector["weekly_performance_residual_coefficient"] = 0.99
        return [
            W.WitnessObservation(
                comparison=name,
                synthetic_value=1.0,
                real_value=1.0 + self.witness_divergence,
                divergence=self.witness_divergence,
            )
            for name in W.WITNESS_COMPARISONS
        ]

    def execute_tier(self, tier_name, vector, *, bindings, basetemp=None):
        self.tier_calls.append(tier_name)
        tier = {t.name: t for t in tier_policy.GOVERNED_TIERS}[tier_name]
        report = _tier_report(
            tier.paths, bindings, self.aggregates.get(tier_name)
        )
        if self.fail_tier == tier_name:
            report["assertions"] = {"failed": ["deliberate test failure"]}
        return report

    def freeze(self, vector, bindings):
        return {
            "bindings": dict(bindings),
            "artifacts": {"hashes": {"freeze.json": "f" * 64}},
        }


def make_config(tmp_path: Path, manifest=None, authority=None, **overrides) -> SupervisorConfig:
    repo, binding = SUP.binding_for(authority)
    kwargs = {
        "evidence_manifest_path": write_manifest(tmp_path, manifest),
        "evidence_authority": binding,
        "repo": repo,
        "run_root": tmp_path / "runs",
        "base_seed": 20260101,
        "headline_quantities": ("champion_probability_top1",),
        "equivalence_tolerance": 1e-6,
    }
    kwargs.update(overrides)
    return SupervisorConfig(**kwargs)


def drive(tmp_path: Path, executor=None, config=None, **config_overrides):
    """Run a supervisor to its first stop and return it with its report."""
    config = config or make_config(tmp_path, **config_overrides)
    supervisor = Supervisor(config, executor or FakeExecutor(), run_id="RUN_R6")
    return supervisor, supervisor.run()


# --- state machine -----------------------------------------------------------


def test_state_machine_is_a_linear_spine_with_two_halt_states():
    assert len(S.SPINE) == 35
    assert len(S.STATES) == 37
    assert S.HALT_STATES == (S.HALTED_FAILED, S.HALTED_FOR_HUMAN_REVIEW)
    # Every live spine state has exactly one successor plus the two halts.
    for name in S.SPINE:
        if name in S.TERMINAL_STATES:
            assert S.LEGAL_TRANSITIONS[name] == frozenset()
            continue
        if name in S.POST_APPROVAL_STATES:
            # After the approval there is no human left to stop for, so the only
            # halt available is failure. One human gate, enforced by the edge set
            # rather than by every gate remembering not to ask.
            assert S.LEGAL_TRANSITIONS[name] == frozenset(
                {_successor(name), S.HALTED_FAILED}
            )
            continue
        assert len(S.LEGAL_TRANSITIONS[name]) == 3
    for halt in S.HALT_STATES:
        assert S.LEGAL_TRANSITIONS[halt] == frozenset()


def _successor(state):
    return S.SPINE[S.SPINE.index(state) + 1]


def test_illegal_transitions_are_refused():
    # Skipping the human gate outright.
    with pytest.raises(GovernanceBlock):
        S.require_legal_transition(S.PARAMETER_RECOMMENDATION_READY, S.DEV_500_REQUIRED)
    # Jumping straight to publish.
    with pytest.raises(GovernanceBlock):
        S.require_legal_transition(S.DEV_500_REQUIRED, S.PUBLISH_10000_REQUIRED)
    # Going backwards.
    with pytest.raises(GovernanceBlock):
        S.require_legal_transition(S.HOLDOUT_RELEASED, S.HOLDOUT_LOCKED)
    # Leaving a terminal state at all.
    with pytest.raises(GovernanceBlock):
        S.require_legal_transition(S.COMPLETE, S.FINAL_FREEZE_REQUIRED)
    with pytest.raises(GovernanceBlock):
        S.require_legal_transition(S.HALTED_FAILED, S.DEV_500_REQUIRED)


def test_stage_result_refuses_advisory_status_mismatch():
    with pytest.raises(GovernanceBlock):
        S.StageResult(stage="x", status=S.PASS, summary="", advisories=("note",))
    with pytest.raises(GovernanceBlock):
        S.StageResult(stage="x", status=S.PASS_WITH_ADVISORY, summary="")
    with pytest.raises(GovernanceBlock):
        S.StageResult(stage="x", status="MOSTLY_FINE", summary="")


# --- evidence and eligibility ------------------------------------------------


def test_real_seasons_are_refused_in_the_primary_estimation_domain(tmp_path):
    for domain in (
        ["SYNTHETIC_2024", "REAL_2023"],
        ["SYNTHETIC_2024", "2022"],
        ["SYNTHETIC_2024", "OBSERVED_2021"],
        ["SYNTHETIC_2024", "HISTORICAL_2024"],
    ):
        payload = manifest_payload(primary_estimation_domain=domain)
        with pytest.raises(GovernanceBlock, match="EXTERNAL_WITNESS_ONLY|estimation domain"):
            EV.load_evidence_manifest(write_manifest(tmp_path, payload))


def test_real_corpus_is_admitted_only_as_witness(tmp_path):
    payload = manifest_payload()
    payload["real_witness"]["role"] = "CALIBRATION_INPUT"
    with pytest.raises(GovernanceBlock, match="EXTERNAL_WITNESS_ONLY"):
        EV.load_evidence_manifest(write_manifest(tmp_path, payload))

    payload = manifest_payload()
    payload["real_witness"]["sha256"] = "0" * 64
    with pytest.raises(GovernanceBlock, match="accepted corpus"):
        EV.load_evidence_manifest(write_manifest(tmp_path, payload))


def test_circular_evidence_cannot_be_declared_fittable(tmp_path):
    payload = manifest_payload()
    payload["parameters"]["weekly_performance_residual_coefficient"] = _fit(
        circularity=EV.GENERATED_BY_MECHANISM_UNDER_ESTIMATION
    )
    with pytest.raises(GovernanceBlock, match="not independent evidence"):
        EV.load_evidence_manifest(write_manifest(tmp_path, payload))


def test_unclassified_circularity_cannot_support_a_fit(tmp_path):
    payload = manifest_payload()
    payload["parameters"]["weekly_performance_residual_coefficient"] = _fit(
        circularity=EV.UNCLASSIFIED
    )
    with pytest.raises(GovernanceBlock, match="UNCLASSIFIED"):
        EV.load_evidence_manifest(write_manifest(tmp_path, payload))


def test_fit_is_blocked_when_evidence_says_circular_not_identifiable(tmp_path):
    payload = manifest_payload()
    payload["parameters"]["weekly_performance_residual_coefficient"] = {
        "eligibility": EV.CIRCULAR_NOT_IDENTIFIABLE,
        "circularity": EV.GENERATED_BY_MECHANISM_UNDER_ESTIMATION,
        "evidence_fields": ["synthetic_2025.weekly_rating_delta"],
        "rationale": "Produced by the weekly rerating mechanism being estimated.",
    }
    manifest = EV.load_evidence_manifest(write_manifest(tmp_path, payload))
    with pytest.raises(GovernanceBlock, match="CIRCULAR_NOT_IDENTIFIABLE"):
        EV.require_fit_permitted(manifest, "weekly_performance_residual_coefficient")


def test_fixed_values_bypass_fitting_and_are_carried_forward(tmp_path):
    payload = manifest_payload()
    payload["parameters"]["weekly_performance_residual_coefficient"] = _fixed(0.42)
    supervisor, report = drive(tmp_path, manifest=payload)
    assert report["state"] == S.AWAITING_HUMAN_APPROVAL
    artifact = json.loads(
        (supervisor.run_dir / "recommendation" / "recommendation.json").read_text("utf-8")
    )
    entry = next(
        p for p in artifact["parameters"]
        if p["parameter"] == "weekly_performance_residual_coefficient"
    )
    assert entry["eligibility"] == EV.FIXED
    assert entry["recommended_value"] == 0.42
    assert entry["boundary_status"] == "NOT_SEARCHED"
    # It was never an axis, so nothing searched it.
    coarse = json.loads(
        next((supervisor.run_dir / "stage_results").glob(f"*_{STAGE_COARSE_SEARCH}.json")).read_text("utf-8")
    )
    assert "weekly_performance_residual_coefficient" not in coarse["detail"]["outcomes"]


def test_point_scale_supports_all_four_resolutions(tmp_path):
    fixed = EV.load_evidence_manifest(write_manifest(tmp_path, manifest_payload()))
    assert fixed.point_scale.resolution == EV.POINT_SCALE_FIXED_EXISTING_VALUE
    assert fixed.point_scale.value == EV.GOVERNED_POINT_SCALE_POINTS_PER_SD

    for resolution, eligibility, extra in (
        (EV.POINT_SCALE_FIT_ALLOWED, EV.FIT_ALLOWED, {"search_space": dict(_SCALAR_AXIS)}),
        (
            EV.POINT_SCALE_CIRCULAR_NOT_IDENTIFIABLE,
            EV.CIRCULAR_NOT_IDENTIFIABLE,
            {},
        ),
        (EV.POINT_SCALE_BLOCKED, EV.BLOCKED, {}),
    ):
        payload = manifest_payload()
        payload["point_scale"] = {
            "resolution": resolution,
            "rationale": "declared",
            **extra,
        }
        entry = {
            "eligibility": eligibility,
            "circularity": (
                EV.GENERATED_BY_MECHANISM_UNDER_ESTIMATION
                if eligibility == EV.CIRCULAR_NOT_IDENTIFIABLE
                else EV.INDEPENDENT_OF_MECHANISM
            ),
            "evidence_fields": [],
            "rationale": "declared",
            "required": False,
        }
        if eligibility == EV.FIT_ALLOWED:
            entry["search_space"] = dict(_SCALAR_AXIS)
        payload["parameters"]["point_scale"] = entry
        manifest = EV.load_evidence_manifest(
            write_manifest(tmp_path / resolution, payload)
        )
        assert manifest.point_scale.resolution == resolution


def test_point_scale_resolution_and_eligibility_must_agree(tmp_path):
    payload = manifest_payload()
    payload["parameters"]["point_scale"] = _fit()
    with pytest.raises(GovernanceBlock, match="implies parameter eligibility"):
        EV.load_evidence_manifest(write_manifest(tmp_path, payload))


# --- search ------------------------------------------------------------------


def _oracle(fn):
    return SEARCH.ScoringOracle(oracle_id="T", fn=fn, implementation_digest="x" * 8)


def test_boundary_optimum_expands_the_declared_range():
    axis = SEARCH.SearchAxis(
        parameter="p", lower=0.0, upper=1.0, points=5, max_expansions=3
    )
    # The true optimum is at 2.0, outside the declared range.
    outcome = SEARCH.coarse_search(
        axis, _oracle(lambda c, s: (c["p"] - 2.0) ** 2), split="training"
    )
    assert outcome.identification_status == SEARCH.IDENTIFIED
    assert outcome.boundary_status == SEARCH.BOUNDARY_EXPANDED_THEN_INTERIOR
    assert outcome.expansions_used > 0
    assert outcome.final_upper > axis.upper
    assert outcome.best_value == pytest.approx(2.0, abs=0.5)


def test_boundary_bound_after_max_expansion_is_unidentified_not_a_value():
    axis = SEARCH.SearchAxis(
        parameter="p", lower=0.0, upper=1.0, points=5, max_expansions=1
    )
    outcome = SEARCH.coarse_search(
        axis, _oracle(lambda c, s: -float(c["p"])), split="training"
    )
    assert outcome.boundary_status == SEARCH.BOUNDARY_BOUND_AT_MAX_EXPANSION
    assert outcome.identification_status == SEARCH.PARAMETER_UNIDENTIFIED
    assert outcome.best_value is None


def test_hard_limit_is_reported_separately_from_budget_exhaustion():
    axis = SEARCH.SearchAxis(
        parameter="p",
        lower=0.0,
        upper=1.0,
        points=5,
        max_expansions=5,
        hard_upper=1.0,
    )
    outcome = SEARCH.coarse_search(
        axis, _oracle(lambda c, s: -float(c["p"])), split="training"
    )
    assert outcome.boundary_status == SEARCH.BOUNDARY_BOUND_AT_DECLARED_LIMIT
    assert outcome.best_value is None


def test_search_is_deterministic_and_ties_break_to_the_lowest_index():
    axis = SEARCH.SearchAxis(parameter="p", lower=0.0, upper=1.0, points=5, max_expansions=0)
    flat = _oracle(lambda c, s: 1.0)
    first = SEARCH.coarse_search(axis, flat, split="training")
    second = SEARCH.coarse_search(axis, flat, split="training")
    assert first.as_dict() == second.as_dict()
    # A flat objective wins at index 0, which is a boundary, so it is refused.
    assert first.identification_status == SEARCH.PARAMETER_UNIDENTIFIED


def test_nonbinding_cap_is_classified_unidentified_with_no_value():
    finalists = [
        SEARCH.FinalistObservation(
            candidate_id=f"C{i}", score=1.0, constraint_value=5.0 + i,
            constraint_binding_events=0,
        )
        for i in range(4)
    ]
    result = SEARCH.classify_movement_cap(finalists, equivalence_tolerance=1e-9)
    assert result["identification_status"] == SEARCH.UNIDENTIFIED_NONBINDING
    assert result["recommended_value"] is None
    assert result["equivalent_finalist_count"] == 4


def test_binding_cap_is_classified_identified():
    finalists = [
        SEARCH.FinalistObservation(
            candidate_id="C0", score=1.0, constraint_value=5.0, constraint_binding_events=7
        ),
        SEARCH.FinalistObservation(
            candidate_id="C1", score=1.0, constraint_value=6.0, constraint_binding_events=0
        ),
    ]
    result = SEARCH.classify_movement_cap(finalists, equivalence_tolerance=1e-9)
    assert result["identification_status"] == SEARCH.IDENTIFIED_BINDING
    assert result["recommended_value"] == 5.0


# --- holdout -----------------------------------------------------------------


def _seal(**overrides):
    fields = {
        "dataset_sha256": "d",
        "split_sha256": "s",
        "experiment_config_sha256": "e",
        "candidate_universe_digest": "c",
        "scoring_oracle_digest": "o",
    }
    fields.update(overrides)
    return HO.HoldoutSeal(**fields)


def test_holdout_cannot_be_released_early():
    guard = HO.HoldoutGuard(seal=_seal())
    for state in (S.COARSE_SEARCH_REQUIRED, S.VALIDATION_REQUIRED, S.VALIDATION_COMPLETE):
        with pytest.raises(GovernanceBlock, match="not yet frozen"):
            guard.release(current_state=state, observed=_seal(), released_at="t")
    assert guard.released is False


def test_holdout_release_is_one_way_and_scoring_happens_once():
    guard = HO.HoldoutGuard(seal=_seal())
    guard.release(current_state=S.HOLDOUT_LOCKED, observed=_seal(), released_at="t1")
    with pytest.raises(GovernanceBlock, match="already been released"):
        guard.release(current_state=S.HOLDOUT_LOCKED, observed=_seal(), released_at="t2")
    guard.record_score({"rmse": 1.0})
    with pytest.raises(GovernanceBlock, match="already been scored"):
        guard.record_score({"rmse": 0.5})
    assert guard.outcome == {"rmse": 1.0}


def test_holdout_release_refuses_every_kind_of_binding_drift():
    for field in (
        "dataset_sha256",
        "split_sha256",
        "experiment_config_sha256",
        "candidate_universe_digest",
        "scoring_oracle_digest",
    ):
        guard = HO.HoldoutGuard(seal=_seal())
        with pytest.raises(GovernanceBlock, match=field):
            guard.release(
                current_state=S.HOLDOUT_LOCKED,
                observed=_seal(**{field: "moved"}),
                released_at="t",
            )


def test_no_worker_may_inspect_the_holdout_during_candidate_generation():
    guard = HO.HoldoutGuard(seal=_seal())
    oracle = HO.guarded_oracle(
        SEARCH.ScoringOracle(oracle_id="T", fn=lambda c, s: 1.0, implementation_digest="x"),
        guard,
    )
    assert oracle.score({}, split="training") == 1.0
    with pytest.raises(GovernanceBlock, match="during candidate generation"):
        oracle.score({}, split="holdout")
    # Wrapping must not change the oracle identity the seal binds.
    assert oracle.digest == SEARCH.ScoringOracle(
        oracle_id="T", fn=lambda c, s: 1.0, implementation_digest="x"
    ).digest


def test_a_peeking_worker_fails_the_run_rather_than_scoring(tmp_path):
    _, report = drive(tmp_path, FakeExecutor(holdout_peek=True))
    assert report["state"] == S.HALTED_FAILED
    assert "during candidate generation" in report["halt_reason"]


# --- witness -----------------------------------------------------------------


def test_witness_cannot_mutate_the_selected_parameter_vector(tmp_path):
    _, report = drive(tmp_path, FakeExecutor(witness_mutates=True))
    assert report["state"] == S.HALTED_FAILED
    assert "EXTERNAL_WITNESS_ONLY" in report["halt_reason"]


def test_require_vector_unchanged_distinguishes_none_from_absent():
    W.require_vector_unchanged({"a": None}, {"a": None})
    with pytest.raises(GovernanceBlock):
        W.require_vector_unchanged({"a": None}, {})
    with pytest.raises(GovernanceBlock):
        W.require_vector_unchanged({"a": 1.0}, {"a": 1.5})


def test_witness_failure_is_classified_by_a_declared_threshold():
    thresholds = (
        W.WitnessThreshold(
            comparison="residual_scale",
            advisory_at=0.1,
            failure_at=0.5,
            on_failure=W.ON_FAILURE_FAIL,
            required=True,
        ),
    )
    breach = [
        W.WitnessObservation(comparison="residual_scale", divergence=0.9)
    ]
    assert classify_status(breach, thresholds) == S.FAIL
    advisory = [W.WitnessObservation(comparison="residual_scale", divergence=0.2)]
    assert classify_status(advisory, thresholds) == S.PASS_WITH_ADVISORY
    clean = [W.WitnessObservation(comparison="residual_scale", divergence=0.01)]
    assert classify_status(clean, thresholds) == S.PASS


def classify_status(observations, thresholds):
    return W.classify_witness(observations, thresholds)["status"]


def test_optional_witness_unavailable_continues_but_required_does_not():
    optional = (
        W.WitnessThreshold(comparison="fcs_witness", advisory_at=0.1, failure_at=0.5),
    )
    unavailable = [W.WitnessObservation(comparison="fcs_witness", available=False)]
    result = W.classify_witness(unavailable, optional)
    assert result["status"] == S.PASS_WITH_ADVISORY
    assert result["comparisons"][0]["classification"] == W.WITNESS_UNAVAILABLE

    required = (
        W.WitnessThreshold(
            comparison="fcs_witness", advisory_at=0.1, failure_at=0.5, required=True
        ),
    )
    assert W.classify_witness(unavailable, required)["status"] == S.FAIL
    # A required comparison that was never reported at all is also missing evidence.
    assert W.classify_witness([], required)["status"] == S.FAIL


# --- gates -------------------------------------------------------------------


def test_dev_gate_checks_every_declared_structural_property():
    report = _tier_report(500, {})
    assert gates.gate_dev_500(report).status == S.PASS

    for mutation in (
        {"observed_paths": 499},
        {"numeric": {"nan_count": 1, "inf_count": 0}},
        {"probabilities": {"min": -0.1, "max": 1.0, "mass_checks": [{"name": "c", "sum": 1.0}]}},
        {"team_identities": {"expected": 134, "observed": 133, "unknown": ["X"]}},
        {"cfp": {"violations": [], "duplicate_participants": ["Ohio State"]}},
        {"assertions": {"failed": ["boom"]}},
        {"seed": {"base_seed": 1, "replay_digest": "a", "reference_digest": "b"}},
        {"artifacts": {"required": ["x.json"], "present": [], "hashes": {}}},
    ):
        broken = _tier_report(500, {})
        broken.update(mutation)
        assert gates.gate_dev_500(broken).status == S.FAIL, mutation


def test_analysis_gate_diagnoses_convergence_without_any_declared_tolerance():
    dev = _tier_report(500, {}, {"k": 0.10})
    analysis = _tier_report(2000, {}, {"k": 0.11})
    # No tolerance is supplied anywhere, and the gate still decides: 0.10 at 500
    # paths and 0.11 at 2,000 are well inside their combined sampling error.
    assert gates.gate_analysis_2000(analysis, dev_report=dev).status == S.PASS
    # Divergence far past what sampling explains fails.
    diverged = _tier_report(2000, {}, {"k": 0.90})
    assert gates.gate_analysis_2000(diverged, dev_report=dev).status == S.FAIL
    # And it never asks a human, because after the approval there is none.
    for report in (analysis, diverged):
        assert (
            gates.gate_analysis_2000(report, dev_report=dev).status
            != S.HUMAN_REVIEW_REQUIRED
        )


def test_freeze_refuses_a_non_publish_tier_and_unpassed_upstream():
    report = {"bindings": {"a": "1"}, "artifacts": {"hashes": {"f": "h"}}}
    assert gates.gate_final_freeze(
        report,
        tier_paths=tier_policy.PUBLISH.paths,
        upstream_passed={"dev_500": True, "analysis_2000": True, "publish_10000": True},
        expected_bindings={"a": "1"},
    ).status == S.PASS
    assert gates.gate_final_freeze(
        report,
        tier_paths=tier_policy.DEV.paths,
        upstream_passed={"dev_500": True},
        expected_bindings={"a": "1"},
    ).status == S.FAIL
    assert gates.gate_final_freeze(
        report,
        tier_paths=tier_policy.PUBLISH.paths,
        upstream_passed={"dev_500": True, "publish_10000": False},
        expected_bindings={"a": "1"},
    ).status == S.FAIL


# --- retry -------------------------------------------------------------------


def test_temp_root_race_retries_exactly_once_on_a_fresh_basetemp():
    attempts: list[Path | None] = []

    def flaky(basetemp):
        attempts.append(basetemp)
        if len(attempts) == 1:
            raise OSError(5, "Access is denied", r"C:\Temp\pytest-of-user\basetemp")
        return "ok"

    outcome = RETRY.run_with_temp_root_retry(flaky)
    assert outcome.value == "ok"
    assert outcome.retried is True
    assert len(attempts) == 2
    assert attempts[0] is None
    assert attempts[1] is not None and attempts[1].exists()
    assert not any(attempts[1].iterdir())


def test_a_second_temp_root_failure_is_not_retried_again():
    def always(basetemp):
        raise OSError(5, "Access is denied", "pytest-of-user")

    with pytest.raises(OSError):
        RETRY.run_with_temp_root_retry(always)


def test_model_failures_are_never_retried():
    calls = []

    def model_failure(basetemp):
        calls.append(basetemp)
        raise OSError(2, "No such file or directory", "governed_input.xlsx")

    with pytest.raises(OSError):
        RETRY.run_with_temp_root_retry(model_failure)
    assert len(calls) == 1


# --- run directory, locking, resume ------------------------------------------


def test_only_one_supervisor_may_own_a_run_directory(tmp_path):
    run_dir = tmp_path / "run"
    with RunLock(run_dir):
        with pytest.raises(GovernanceBlock, match="already owned"):
            RunLock(run_dir).acquire()
    # Released on exit, so a later owner succeeds.
    RunLock(run_dir).acquire().release()


def test_state_persistence_is_atomic_and_leaves_no_partial_file(tmp_path):
    state = RunState.create("RUN", tmp_path / "run")
    state.advance(S.SYNTHETIC_EVIDENCE_REQUIRED, reason="start")
    reloaded = RunState.load(tmp_path / "run")
    assert reloaded.state == S.SYNTHETIC_EVIDENCE_REQUIRED
    assert reloaded.history[-1]["to"] == S.SYNTHETIC_EVIDENCE_REQUIRED
    assert not list((tmp_path / "run").glob(".*.tmp"))
    for name in ("inputs", "stage_results", "recommendation", "approval", "freeze"):
        assert (tmp_path / "run" / name).is_dir()


def test_a_stage_result_is_not_silently_replaced(tmp_path):
    state = RunState.create("RUN", tmp_path / "run")
    result = S.StageResult(stage="s", status=S.PASS, summary="one")
    state.record_stage(result)
    # Identical content replays cleanly; different content is a conflict.
    from ncaaf_engine.simulation.dynamic_weekly_mc_v3.supervisor.runstore import (
        write_stage_result,
    )

    write_stage_result(tmp_path / "run", 0, result)
    with pytest.raises(GovernanceBlock, match="different content"):
        write_stage_result(
            tmp_path / "run", 0, S.StageResult(stage="s", status=S.PASS, summary="two")
        )


def test_resume_refuses_code_drift(tmp_path):
    state = RunState.create("RUN", tmp_path / "run")
    state.advance(S.SYNTHETIC_EVIDENCE_REQUIRED, reason="start")
    state.code_tree_digest = "a-different-supervisor"
    state.save()
    with pytest.raises(GovernanceBlock, match="supervisor code"):
        RunState.load(tmp_path / "run").require_resumable()


def test_resume_refuses_input_drift(tmp_path):
    state = RunState.create("RUN", tmp_path / "run")
    state.input_digest = "original-inputs"
    state.advance(S.SYNTHETIC_EVIDENCE_REQUIRED, reason="start")
    with pytest.raises(GovernanceBlock, match="inputs"):
        RunState.load(tmp_path / "run").require_resumable(
            observed_input_digest="edited-inputs"
        )


def test_resume_continues_from_the_last_valid_state(tmp_path):
    config = make_config(tmp_path)
    first = Supervisor(config, FakeExecutor(), run_id="RESUMABLE")
    first.start()
    # Walk only part of the way, then stop where a crash would have.
    state = first.state
    for _ in range(6):
        current = state.state
        stage = STAGE_FOR_STATE.get(current)
        if stage is None:
            state.advance(S.SPINE[S.state_index(current) + 1], reason="marker")
        else:
            first._step(stage)
    partial = state.state
    assert partial not in S.TERMINAL_STATES

    second = Supervisor(config, FakeExecutor(), run_id="RESUMABLE")
    report = second.resume()
    assert report["state"] == S.AWAITING_HUMAN_APPROVAL
    # The resumed run kept everything the first one had already recorded.
    assert S.state_index(partial) < S.state_index(S.AWAITING_HUMAN_APPROVAL)
    assert report["history"][0]["from"] == S.INITIALIZED


# --- approval ----------------------------------------------------------------


def _approve(supervisor, **overrides):
    kwargs = {
        "recommendation_sha256": supervisor.state.recommendation_sha256,
        "approver": "chairman",
        "action": APPROVAL_ACTION,
    }
    kwargs.update(overrides)
    return supervisor.approve(**kwargs)


def test_the_run_stops_at_the_single_human_gate(tmp_path):
    supervisor, report = drive(tmp_path)
    assert report["state"] == S.AWAITING_HUMAN_APPROVAL
    assert report["awaiting_human_approval"] is True
    assert len(report["recommendation_sha256"]) == 64
    assert (supervisor.run_dir / "recommendation" / "recommendation.json").exists()
    assert not (supervisor.run_dir / "approval" / "approval.json").exists()
    # Nothing downstream of the gate ran.
    assert supervisor.executor.tier_calls == []


def test_approval_requires_the_exact_recommendation_sha(tmp_path):
    supervisor, _ = drive(tmp_path)
    with pytest.raises(GovernanceBlock, match="SHA mismatch"):
        _approve(supervisor, recommendation_sha256="b" * 64)
    with pytest.raises(InputValidationError, match="hexadecimal"):
        _approve(supervisor, recommendation_sha256="not-a-sha")
    with pytest.raises(GovernanceBlock, match="Unknown approval action"):
        _approve(supervisor, action="APPROVE_EVERYTHING")
    with pytest.raises(GovernanceBlock, match="named approver"):
        _approve(supervisor, approver="   ")


def test_approval_refuses_changed_code(tmp_path, monkeypatch):
    supervisor, _ = drive(tmp_path)
    import ncaaf_engine.simulation.dynamic_weekly_mc_v3.supervisor.supervisor as SUP

    monkeypatch.setattr(SUP, "code_tree_digest", lambda *a, **k: "moved-code")
    with pytest.raises(GovernanceBlock, match="world moved"):
        _approve(supervisor)


def test_approval_refuses_a_changed_dataset_or_scoring_oracle(tmp_path):
    supervisor, _ = drive(tmp_path)

    class MovedDataset(FakeExecutor):
        def calibration_dataset(self):
            from dataclasses import replace

            return replace(super().calibration_dataset(), sha256="9" * 64)

    supervisor.executor = MovedDataset()
    # The bindings are re-derived at approval time from the recorded dataset
    # stage result, so drift is injected the way it would really arrive: by the
    # stage result on disk no longer matching.
    path = next((supervisor.run_dir / "stage_results").glob("*_calibration_dataset.json"))
    payload = json.loads(path.read_text("utf-8"))
    payload["detail"]["sha256"] = "9" * 64
    path.write_text(json.dumps(payload), encoding="utf-8", newline="")
    with pytest.raises(GovernanceBlock, match="world moved"):
        _approve(supervisor)


def test_approval_refuses_a_stale_recommendation(tmp_path):
    supervisor, _ = drive(tmp_path)
    stale = supervisor.state.recommendation_sha256
    # A regenerated recommendation supersedes the one an approver is holding.
    supervisor.state.recommendation_sha256 = "c" * 64
    supervisor.state.save()
    with pytest.raises(GovernanceBlock, match="[Ss]tale recommendation"):
        supervisor.approve(recommendation_sha256=stale, approver="chairman")


def test_approval_is_never_automatic(tmp_path):
    supervisor, _ = drive(tmp_path)
    # Driving again from the gate changes nothing; the supervisor has no path
    # that grants its own approval.
    again = supervisor.resume()
    assert again["state"] == S.AWAITING_HUMAN_APPROVAL
    assert again["approval_digest"] == ""


def test_approval_is_refused_outside_the_gate_state(tmp_path):
    config = make_config(tmp_path)
    supervisor = Supervisor(config, FakeExecutor(), run_id="EARLY")
    supervisor.start()
    with pytest.raises(GovernanceBlock):
        supervisor.approve(recommendation_sha256="a" * 64, approver="chairman")


# --- post-approval autonomy --------------------------------------------------


def test_approved_run_proceeds_500_to_2000_to_10000_to_freeze(tmp_path):
    supervisor, _ = drive(tmp_path)
    approval = _approve(supervisor)
    assert approval["state"] == S.PARAMETERS_APPROVED

    executor = supervisor.executor
    resumed = Supervisor(supervisor.config, executor, run_id=supervisor.run_id)
    final = resumed.resume()
    assert final["state"] == S.COMPLETE
    assert executor.tier_calls == ["DEV", "ANALYSIS", "PUBLISH"]
    for name in ("dev_500", "analysis_2000", "publish_10000"):
        assert (resumed.run_dir / name / "report.json").exists()
    assert (resumed.run_dir / "freeze" / "freeze.json").exists()
    # One human gate, and it was traversed exactly once.
    approvals = [h for h in final["history"] if h["to"] == S.PARAMETERS_APPROVED]
    assert len(approvals) == 1


def test_dev_failure_blocks_analysis(tmp_path):
    supervisor, _ = drive(tmp_path, FakeExecutor(fail_tier="DEV"))
    _approve(supervisor)
    executor = supervisor.executor
    resumed = Supervisor(supervisor.config, executor, run_id=supervisor.run_id)
    final = resumed.resume()
    assert final["state"] == S.HALTED_FAILED
    assert executor.tier_calls == ["DEV"]
    assert not (resumed.run_dir / "analysis_2000" / "report.json").exists()


def test_analysis_failure_blocks_publish(tmp_path):
    supervisor, _ = drive(tmp_path, FakeExecutor(fail_tier="ANALYSIS"))
    _approve(supervisor)
    executor = supervisor.executor
    resumed = Supervisor(supervisor.config, executor, run_id=supervisor.run_id)
    final = resumed.resume()
    assert final["state"] == S.HALTED_FAILED
    assert executor.tier_calls == ["DEV", "ANALYSIS"]
    assert not (resumed.run_dir / "publish_10000" / "report.json").exists()
    assert not (resumed.run_dir / "freeze" / "freeze.json").exists()


def test_publish_failure_produces_no_freeze_artifact(tmp_path):
    supervisor, _ = drive(tmp_path, FakeExecutor(fail_tier="PUBLISH"))
    _approve(supervisor)
    resumed = Supervisor(supervisor.config, supervisor.executor, run_id=supervisor.run_id)
    final = resumed.resume()
    assert final["state"] == S.HALTED_FAILED
    assert not (resumed.run_dir / "freeze" / "freeze.json").exists()


def test_approval_is_required_before_dev(tmp_path):
    supervisor, _ = drive(tmp_path)
    state = supervisor.state
    # Force the machine into the post-approval state without an approval record.
    state.advance(S.PARAMETERS_APPROVED, reason="test forces the edge")
    resumed = Supervisor(supervisor.config, supervisor.executor, run_id=supervisor.run_id)
    final = resumed.resume()
    assert final["state"] == S.HALTED_FAILED
    assert "no parameter approval" in final["halt_reason"].lower()
    assert resumed.executor.tier_calls == []


# --- advisories --------------------------------------------------------------


def test_pass_with_advisory_continues(tmp_path):
    supervisor, report = drive(tmp_path, FakeExecutor(cap_binding_events=0))
    assert report["state"] == S.AWAITING_HUMAN_APPROVAL
    refinement = json.loads(
        next((supervisor.run_dir / "stage_results").glob("*_refinement.json")).read_text("utf-8")
    )
    assert refinement["status"] == S.PASS_WITH_ADVISORY
    assert refinement["detail"]["constraint_classification"]["identification_status"] == (
        SEARCH.UNIDENTIFIED_NONBINDING
    )
    # The advisory did not stop the run, and the non-binding cap recommends no value.
    artifact = json.loads(
        (supervisor.run_dir / "recommendation" / "recommendation.json").read_text("utf-8")
    )
    cap = next(
        p for p in artifact["parameters"] if p["parameter"] == "weekly_movement_cap_points"
    )
    assert cap["recommended_value"] is None
    assert cap["identification_status"] == SEARCH.UNIDENTIFIED_NONBINDING


def test_an_advisory_marked_required_by_policy_stops_the_run(tmp_path):
    executor = FakeExecutor(cap_binding_events=0)
    probe, _ = drive(tmp_path / "probe", executor)
    refinement = json.loads(
        next((probe.run_dir / "stage_results").glob("*_refinement.json")).read_text("utf-8")
    )
    advisory = refinement["advisories"][0]

    _, report = drive(
        tmp_path / "policy",
        FakeExecutor(cap_binding_events=0),
        required_advisories=(advisory,),
    )
    assert report["state"] == S.HALTED_FOR_HUMAN_REVIEW
    assert "marked required" in report["halt_reason"]


def test_fcs_adapter_may_complete_explicitly_unidentified(tmp_path):
    supervisor, report = drive(tmp_path, FakeExecutor(fcs_identified=False))
    assert report["state"] == S.AWAITING_HUMAN_APPROVAL
    artifact = json.loads(
        (supervisor.run_dir / "recommendation" / "recommendation.json").read_text("utf-8")
    )
    fcs = next(p for p in artifact["parameters"] if p["parameter"] == "fcs_point_adapter")
    assert fcs["recommended_value"] is None
    assert fcs["identification_status"] == SEARCH.PARAMETER_UNIDENTIFIED


# --- default executor and plan mode ------------------------------------------


def test_the_default_executor_refuses_and_the_run_halts(tmp_path):
    config = make_config(tmp_path)
    supervisor = Supervisor(config, UnmountedEvidenceExecutor(), run_id="UNMOUNTED")
    report = supervisor.run()
    assert report["state"] == S.HALTED_FAILED
    assert "not mounted" in report["halt_reason"]
    # The evidence stage still passed; it is the dataset that is missing.
    assert "synthetic_evidence" in report["stages_completed"]


def test_plan_has_no_side_effects_and_resolves_the_run(tmp_path):
    config = make_config(tmp_path)
    supervisor = Supervisor(config, FakeExecutor(), run_id="PLANNED")
    plan = supervisor.plan()
    assert plan["mode"] == "PLAN_ONLY"
    assert plan["side_effects"] == "NONE"
    assert not supervisor.run_dir.exists()
    # Canonical parameter order, not alphabetical.
    assert plan["parameters_fitted"] == [
        "weekly_performance_residual_coefficient",
        "weekly_movement_cap_points",
        "game_sd_points",
        "fcs_point_adapter",
    ]
    assert set(plan["parameters_fixed"]) == {
        "blowout_treatment",
        "point_scale",
        "recent_form_weights",
        "sample_size_regularization",
    }
    assert plan["human_gates"][0]["action"] == APPROVAL_ACTION
    assert plan["run_tiers"]["approved_path_counts"] == [500, 2000, 10000]
    assert "point_scale" in plan["stages_skipped"]
    assert plan["output_locations"]["freeze"].endswith("freeze")
    assert plan["real_world_role"] == EV.EXTERNAL_WITNESS_ONLY


# --- CLI ---------------------------------------------------------------------


def _authority_config():
    """The evidence-authority keys a CLI configuration needs, as JSON would."""
    repo, binding = SUP.binding_for()
    return {
        "repo": str(repo),
        "evidence_authority": {
            "ref": binding.ref,
            "path": binding.path,
            "generation": binding.generation,
            "commit": binding.commit,
        },
    }


def test_cli_plan_run_status_and_approve(tmp_path, capsys):
    manifest = write_manifest(tmp_path)
    config_path = tmp_path / "supervisor.json"
    atomic_write_json(
        config_path,
        {
            "label": "CLI_TEST",
            "evidence_manifest": str(manifest),
            "run_root": str(tmp_path / "runs"),
            "base_seed": 20260101,
            "headline_quantities": ["champion_probability_top1"],
            **_authority_config(),
        },
    )
    assert cli.main(["plan", "--config", str(config_path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "PLAN_ONLY"

    # A real run needs an executor, which the CLI cannot supply; the unmounted
    # default refuses, and that is reported as a governance stop rather than a
    # crash.
    assert cli.main(["run", "--config", str(config_path)]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["state"] == S.HALTED_FAILED

    assert (
        cli.main(["status", "--config", str(config_path), "--run-id", report["run_id"]])
        == 0
    )
    status = json.loads(capsys.readouterr().out)
    assert status["state"] == S.HALTED_FAILED
    assert status["next_action"].startswith("Investigate")


def build_fake_executor(config):
    """Executor factory, resolved by ``executor`` in the supervisor config.

    Module-level so the CLI's import path can actually reach it -- which is the
    point of the test that uses it.
    """
    return FakeExecutor()


def test_cli_drives_a_full_lifecycle_through_the_configured_executor(tmp_path, capsys):
    manifest = write_manifest(tmp_path)
    config_path = tmp_path / "supervisor.json"
    atomic_write_json(
        config_path,
        {
            "label": "CLI_LIFECYCLE",
            "evidence_manifest": str(manifest),
            "run_root": str(tmp_path / "runs"),
            "base_seed": 20260101,
            "headline_quantities": ["champion_probability_top1"],
            "executor": f"{__name__}:build_fake_executor",
            **_authority_config(),
        },
    )

    # run stops at the one human gate, and exits 0 because stopping there is the
    # design rather than a failure of it.
    assert cli.main(["run", "--config", str(config_path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["state"] == S.AWAITING_HUMAN_APPROVAL
    run_id, sha = report["run_id"], report["recommendation_sha256"]

    # A wrong SHA is refused, and the run is left exactly where it was.
    assert (
        cli.main(
            [
                "approve",
                "--config",
                str(config_path),
                "--run-id",
                run_id,
                "--recommendation-sha",
                "f" * 64,
                "--approver",
                "chairman",
            ]
        )
        == 2
    )
    assert "SHA mismatch" in capsys.readouterr().out
    assert cli.main(["status", "--config", str(config_path), "--run-id", run_id]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == S.AWAITING_HUMAN_APPROVAL

    assert (
        cli.main(
            [
                "approve",
                "--config",
                str(config_path),
                "--run-id",
                run_id,
                "--recommendation-sha",
                sha,
                "--approver",
                "chairman",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert cli.main(["resume", "--config", str(config_path), "--run-id", run_id]) == 0
    final = json.loads(capsys.readouterr().out)
    assert final["state"] == S.COMPLETE
    assert (tmp_path / "runs" / run_id / "freeze" / "freeze.json").exists()


def test_cli_refuses_a_config_without_an_evidence_manifest(tmp_path, capsys):
    config_path = tmp_path / "bad.json"
    atomic_write_json(config_path, {"label": "NO_MANIFEST"})
    assert cli.main(["plan", "--config", str(config_path)]) == 2
    assert "evidence_manifest" in capsys.readouterr().out


# --- doctrine end to end -----------------------------------------------------


def test_recommendation_records_the_full_evidence_and_binds_to_its_digest(tmp_path):
    supervisor, _ = drive(tmp_path)
    artifact = json.loads(
        (supervisor.run_dir / "recommendation" / "recommendation.json").read_text("utf-8")
    )
    assert artifact["writes_canonical_config"] is False
    assert set(artifact["recommended_vector"]) == set(EV.GOVERNED_PARAMETERS)
    assert artifact["real_world_witness"]["may_change_parameter_vector"] is False
    for entry in artifact["parameters"]:
        assert set(entry) >= {
            "eligibility",
            "identification_status",
            "boundary_status",
            "prior_value",
            "current_value",
            "recommended_value",
            "objective_evidence",
            "validation_evidence",
            "holdout_evidence",
            "sensitivity",
            "synthetic_domain_evidence",
            "real_world_witness",
        }
    bindings = artifact["bindings"]
    assert set(bindings) == {
        "evidence_manifest_digest",
        "dataset_sha256",
        "split_sha256",
        "experiment_config_sha256",
        "candidate_universe_digest",
        "scoring_oracle_digest",
        "input_manifest_digest",
        "code_tree_digest",
        "holdout_seal_digest",
    }
    assert all(v for v in bindings.values())


def test_supervisor_never_promotes_parameters_or_writes_canonical_config(tmp_path):
    supervisor, _ = drive(tmp_path)
    _approve(supervisor)
    resumed = Supervisor(supervisor.config, supervisor.executor, run_id=supervisor.run_id)
    resumed.resume()
    canonical = Path("config/dynamic_weekly_mc_v3/v3_experimental.json")
    raw = json.loads(canonical.read_text(encoding="utf-8"))
    # Every calibration field is still null in the canonical configuration.
    assert all(value is None for value in raw["calibration"].values())
    approval = json.loads(
        (resumed.run_dir / "approval" / "approval.json").read_text("utf-8")
    )
    assert approval["writes_canonical_config"] is False
