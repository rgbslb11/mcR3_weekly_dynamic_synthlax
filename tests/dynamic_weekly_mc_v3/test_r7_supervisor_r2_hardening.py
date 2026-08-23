"""R2 hardening of the autonomous supervisor.

Three things changed and each is a claim that has to be provable rather than
argued. The primary-domain gate now reads a frozen manifest keyed on source byte
digests, so renaming a file must not move it into the estimation domain. A
parameter no longer has to be fitted for the run to reach its human, so a vector
of mixed epistemic dispositions must be constructible, approvable, and still
fail closed where production needs a number nobody has. And the run has exactly
one human stop, so the tier gates must decide convergence from the run samples
themselves -- passing normal Monte Carlo fluctuation, failing systematic
divergence, and doing neither on the strength of a tolerance somebody picked.

The evidence authority in these tests is a real git repository with real
commits, because reading the object store rather than a working tree is the
property the gate exists for. No calibration runs here, no season is simulated,
and no parameter is promoted.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
import supervisor_support as SUP

from ncaaf_engine.simulation.dynamic_weekly_mc_v3.errors import (
    GovernanceBlock,
    InputValidationError,
)
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.supervisor import (
    authority as AU,
    convergence as CV,
    dispositions as D,
    domain_manifest as DM,
    evidence as EV,
    gates,
    states as S,
    wave1 as W1,
)
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.supervisor.recommendation import (
    ParameterRecommendation,
)
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.supervisor.supervisor import (
    Supervisor,
)
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.supervisor import search as SEARCH
from test_r6_autonomous_supervisor import (  # noqa: E402 - sibling test fixtures
    FakeExecutor,
    _fit,
    _fixed,
    _tier_report,
    make_config,
    manifest_payload,
)


class MixedExecutor(FakeExecutor):
    """A fake whose objective can distinguish any scalar axis, not just two.

    The R1 fake discriminated only the two weekly parameters, which was enough
    when they were the only things ever fitted. Under R2 they are typically
    circular and the fitted axes are the Wave-1 pair, so an objective that was
    flat in those would report them boundary-bound -- a property of the fake, not
    of the supervisor.
    """

    name = "FAKE_MIXED"

    def scoring_oracle(self) -> SEARCH.ScoringOracle:
        def _fn(candidate, split):
            base = 0.0
            for name in (
                "weekly_performance_residual_coefficient",
                "weekly_movement_cap_points",
                "blowout_treatment",
                "sample_size_regularization",
            ):
                value = candidate.get(name)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    base += (float(value) - self.optimum) ** 2
            return 1.0 + base

        return SEARCH.ScoringOracle(
            oracle_id="FAKE_RMSE_MIXED", fn=_fn, implementation_digest="o" * 64
        )


# --- helpers -----------------------------------------------------------------

REAL_2023_BYTES = b'{"season": "2023", "games": [{"home": "Michigan", "margin": 21}]}'
SYNTH_2024_BYTES = b'{"season": "SYNTHETIC_2024", "games": [{"a": 1, "margin": 3}]}'


def _write(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _domain_manifest(**overrides) -> DM.EvidenceDomainManifest:
    payload = SUP.authority_manifest_payload(**overrides)
    return DM.parse_domain_manifest(
        json.dumps(payload, sort_keys=True).encode("utf-8"), authority_commit="0" * 40
    )


def _drive(tmp_path, manifest=None, authority=None, executor=None, **overrides):
    config = make_config(tmp_path, manifest, authority, **overrides)
    supervisor = Supervisor(config, executor or MixedExecutor(), run_id="RUN_R7")
    return supervisor, supervisor.run()


def _mixed_manifest_payload():
    """The likely final V3 matrix: five epistemic classes in one vector.

    Circular where the evidence is the mechanism's own output, unidentified from
    synthetic evidence where the manifest says so in as many words, fitted where
    Wave 1 can identify it, fixed where a governed value already exists, and
    missing where no adapter has been produced at all.
    """
    circular = {
        "eligibility": EV.CIRCULAR_NOT_IDENTIFIABLE,
        "circularity": EV.GENERATED_BY_MECHANISM_UNDER_ESTIMATION,
        "evidence_fields": ["synthetic_2024.weekly_rating_delta"],
        "rationale": (
            "The weekly deltas were produced by the rerating mechanism under "
            "estimation, so fitting them recovers the generator's own setting."
        ),
    }
    return manifest_payload(
        point_scale={
            "resolution": EV.POINT_SCALE_CIRCULAR_NOT_IDENTIFIABLE,
            "rationale": "The scale cannot be recovered from outputs its own value produced.",
        },
        parameters={
            "weekly_performance_residual_coefficient": dict(circular),
            "weekly_movement_cap_points": dict(circular),
            "point_scale": dict(circular),
            "recent_form_weights": {
                "eligibility": EV.MISSING,
                "circularity": EV.INDEPENDENT_OF_MECHANISM,
                "evidence_fields": [],
                "rationale": "No synthetic field distinguishes one decay profile from another.",
                "declared_disposition": D.UNIDENTIFIED,
                "disposition_reason": D.RECENT_FORM_UNIDENTIFIED_REASON,
            },
            "blowout_treatment": _fit(),
            "sample_size_regularization": _fit(),
            "game_sd_points": _fixed(16.8),
            "fcs_point_adapter": {
                "eligibility": EV.MISSING,
                "circularity": EV.INDEPENDENT_OF_MECHANISM,
                "evidence_fields": [],
                "rationale": "No admissible FBS-vs-FCS observation exists to estimate from.",
            },
        },
    )


# --- 1-3: manifest-based domain enforcement ----------------------------------


def test_renamed_real_source_cannot_bypass_manifest_domain_classification(tmp_path):
    manifest = _domain_manifest(
        sources=[
            SUP.source(
                "REAL_2023_OBSERVATIONS",
                REAL_2023_BYTES,
                lineage=DM.REAL_OBSERVED,
                season="REAL_2023",
                domain=DM.EXTERNAL_WITNESS_ONLY,
                split="",
                rationale="Real 2021-2024 football. Witness only.",
            )
        ]
    )
    # The file is named as innocuously as anything in this repository could be.
    renamed = _write(tmp_path / "synthetic_2025_estimation_table.json", REAL_2023_BYTES)

    with pytest.raises(GovernanceBlock, match="REAL_OBSERVED_2021_2024"):
        manifest.require_primary_estimation_source(renamed)

    # The classification did not move: the same bytes, under any name.
    record = manifest.classify_path(renamed)
    assert record.source_id == "REAL_2023_OBSERVATIONS"
    assert record.domain == DM.EXTERNAL_WITNESS_ONLY
    assert record.primary_eligible is False

    # And the naming check alone would have let it through, which is exactly why
    # it is not the authority.
    EV.require_synthetic_only_primary_estimation_domain(("SYNTHETIC_2025",))
    assert EV.FILENAME_CHECKS_ROLE == DM.FILENAME_CHECKS_ROLE
    assert "NEVER_AUTHORITATIVE" in EV.FILENAME_CHECKS_ROLE


def test_a_manifest_cannot_admit_real_lineage_to_the_primary_domain():
    with pytest.raises(GovernanceBlock, match="EXTERNAL_WITNESS_ONLY"):
        _domain_manifest(
            sources=[
                SUP.source(
                    "REAL_AS_PRIMARY",
                    REAL_2023_BYTES,
                    lineage=DM.REAL_OBSERVED,
                    season="SYNTHETIC_2024",
                    domain=DM.PRIMARY_ESTIMATION,
                )
            ]
        )


def test_source_sha_drift_fails(tmp_path):
    manifest = _domain_manifest(
        sources=[SUP.source("SYN_2024_TABLE", SYNTH_2024_BYTES, season="SYNTHETIC_2024")]
    )
    admitted = _write(tmp_path / "syn.json", SYNTH_2024_BYTES)
    assert manifest.require_primary_estimation_source(admitted).source_id == "SYN_2024_TABLE"

    # One byte later it is a different source, and there is no entry for it.
    drifted = _write(tmp_path / "syn.json", SYNTH_2024_BYTES + b" ")
    with pytest.raises(GovernanceBlock, match="No source in evidence manifest"):
        manifest.require_primary_estimation_source(drifted)

    # Named explicitly, the drift is reported as drift rather than as absence.
    with pytest.raises(GovernanceBlock, match="has drifted"):
        manifest.require_source_bytes_match("SYN_2024_TABLE", "9" * 64)


def test_forbidden_field_fails_even_with_a_synthetic_filename(tmp_path):
    manifest = _domain_manifest(
        sources=[
            SUP.source(
                "SYN_2024_TABLE",
                SYNTH_2024_BYTES,
                fields={"margin": DM.ADMITTED, "public_money_pct": DM.FORBIDDEN},
            )
        ]
    )
    record = manifest.require_primary_estimation_source(
        _write(tmp_path / "synthetic_2024_admitted.json", SYNTH_2024_BYTES)
    )
    manifest.require_field_admitted(record, "margin")
    with pytest.raises(GovernanceBlock, match="forbidden list"):
        manifest.require_field_admitted(record, "public_money_pct")
    # An unclassified field is refused rather than assumed admitted.
    with pytest.raises(GovernanceBlock, match="not classified"):
        manifest.require_field_admitted(record, "neutral_site")


def test_a_manifest_cannot_admit_a_globally_forbidden_field():
    with pytest.raises(GovernanceBlock, match="globally forbidden"):
        _domain_manifest(
            sources=[
                SUP.source(
                    "SYN_2024_TABLE",
                    SYNTH_2024_BYTES,
                    fields={"public_money_pct": DM.ADMITTED},
                )
            ]
        )


def test_the_forbidden_list_may_not_be_narrower_than_the_calibration_contract():
    with pytest.raises(GovernanceBlock, match="forbidden-field list omits"):
        _domain_manifest(forbidden_fields=["public_money"])


def test_the_supervisor_records_which_gate_is_authoritative(tmp_path):
    supervisor, report = _drive(tmp_path)
    detail = json.loads(
        next(
            (supervisor.run_dir / "stage_results").glob("*_synthetic_evidence.json")
        ).read_text("utf-8")
    )["detail"]
    assert detail["manifest_domain_enforcement"] == "AUTHORITATIVE_BY_SOURCE_SHA256"
    assert detail["filename_checks_role"] == "DEFENSE_IN_DEPTH_SECONDARY_NEVER_AUTHORITATIVE"
    assert detail["authority"]["generation"] == AU.CURRENT_AUTHORITY_GENERATION
    assert len(detail["authority"]["manifest_sha256"]) == 64


def test_a_run_with_no_declared_authority_fails_closed(tmp_path):
    config = replace(make_config(tmp_path), evidence_authority=None)
    supervisor = Supervisor(config, FakeExecutor(), run_id="NO_AUTHORITY")
    report = supervisor.run()
    assert report["state"] == S.HALTED_FAILED
    assert "evidence authority" in report["halt_reason"].lower()


def test_an_authority_that_moved_off_its_pin_is_refused(tmp_path):
    repo, binding = SUP.binding_for()
    moved = replace(binding, commit="a" * 40)
    with pytest.raises(GovernanceBlock, match="pinned to"):
        AU.resolve_authority(moved, repo)


# --- 4-9: mixed parameter dispositions ---------------------------------------


def _recommendation(**overrides):
    entry = {
        "parameter": "blowout_treatment",
        "eligibility": EV.FIT_ALLOWED,
        "identification_status": "IDENTIFIED",
        "prior_value": None,
        "current_value": None,
        "recommended_value": 0.4,
        "boundary_status": "INTERIOR",
        "disposition": D.FIT_RESULT,
        "rationale": "Identified on admissible synthetic evidence.",
    }
    entry.update(overrides)
    return ParameterRecommendation(**entry)


def test_fit_result_is_accepted():
    entry = _recommendation()
    assert entry.disposition == D.FIT_RESULT
    assert entry.recommended_value == 0.4
    # A fit result with no number is not a fit result.
    with pytest.raises(GovernanceBlock, match="carries a value"):
        _recommendation(recommended_value=None, identification_status="PARAMETER_UNIDENTIFIED")
    # And a fit result nobody had permission to produce is refused.
    with pytest.raises(GovernanceBlock, match="requires permission"):
        _recommendation(eligibility=EV.FIXED, current_value=0.4)


def test_fixed_prior_is_accepted():
    entry = _recommendation(
        parameter="game_sd_points",
        eligibility=EV.FIXED,
        identification_status=EV.FIXED,
        current_value=16.8,
        recommended_value=16.8,
        disposition=D.FIXED_PRIOR,
        boundary_status="NOT_SEARCHED",
    )
    assert entry.disposition == D.FIXED_PRIOR
    assert entry.recommended_value == 16.8
    assert D.FIXED_PRIOR in D.CARRIES_VALUE
    assert D.FIXED_PRIOR in D.NON_FIT_DISPOSITIONS


def test_circular_not_identifiable_cannot_enter_an_estimator(tmp_path):
    with pytest.raises(GovernanceBlock, match="must not enter an estimator"):
        D.require_estimator_admissible("point_scale", D.CIRCULAR_NOT_IDENTIFIABLE)
    # It also cannot carry a number.
    with pytest.raises(GovernanceBlock, match="absence"):
        D.require_value_consistent("point_scale", D.CIRCULAR_NOT_IDENTIFIABLE, 14.0)

    # End to end: the axis is not offered to the search at all.
    supervisor, report = _drive(tmp_path, _mixed_manifest_payload())
    assert report["state"] == S.AWAITING_HUMAN_APPROVAL
    searched = [a.parameter for a in supervisor._manifest_axes()]
    assert "weekly_performance_residual_coefficient" not in searched
    assert "weekly_movement_cap_points" not in searched
    assert sorted(searched) == ["blowout_treatment", "sample_size_regularization"]


def test_human_selection_required_reaches_the_one_human_gate(tmp_path):
    payload = _mixed_manifest_payload()
    payload["parameters"]["sample_size_regularization"] = {
        "eligibility": EV.BLOCKED,
        "circularity": EV.INDEPENDENT_OF_MECHANISM,
        "evidence_fields": [],
        "rationale": "Governance has not ruled on the regularization family for this run.",
    }
    supervisor, report = _drive(tmp_path, payload)
    assert report["state"] == S.AWAITING_HUMAN_APPROVAL

    artifact = json.loads(
        (supervisor.run_dir / "recommendation" / "recommendation.json").read_text("utf-8")
    )
    assert artifact["disposition_vector"]["sample_size_regularization"] == (
        D.HUMAN_SELECTION_REQUIRED
    )
    asked = {r["parameter"] for r in artifact["human_disposition_requests"]}
    assert "sample_size_regularization" in asked
    # The question arrives at the gate, not at a second stop invented later.
    assert report["halt_reason"] == ""
    assert report["awaiting_human_approval"] is True


def test_missing_fail_closed_is_an_epistemic_state_that_still_blocks_execution(tmp_path):
    supervisor, report = _drive(tmp_path, _mixed_manifest_payload())
    assert report["state"] == S.AWAITING_HUMAN_APPROVAL
    artifact = json.loads(
        (supervisor.run_dir / "recommendation" / "recommendation.json").read_text("utf-8")
    )
    assert artifact["disposition_vector"]["fcs_point_adapter"] == D.MISSING_FAIL_CLOSED

    answers = _answers_for(artifact)
    # The FCS adapter is left absent on purpose: its use sites fail closed, and
    # the run may still execute, because production does not read it on every
    # path.
    answers["fcs_point_adapter"] = {"value": None, "status": D.MISSING_FAIL_CLOSED}
    granted = supervisor.approve(
        recommendation_sha256=supervisor.state.recommendation_sha256,
        approver="chairman",
        dispositions=answers,
    )
    assert granted["execution_obstacles"] == []
    assert any("fcs_point_adapter" in n for n in granted["use_site_fail_closed"])

    # A parameter production reads on every path is a different matter: approving
    # its absence records what is known and does not manufacture the number.
    second, _ = _drive(tmp_path / "blocked", _mixed_manifest_payload())
    artifact2 = json.loads(
        (second.run_dir / "recommendation" / "recommendation.json").read_text("utf-8")
    )
    answers2 = _answers_for(artifact2)
    answers2["recent_form_weights"] = {"value": None, "status": D.MISSING_FAIL_CLOSED}
    second.approve(
        recommendation_sha256=second.state.recommendation_sha256,
        approver="chairman",
        dispositions=answers2,
    )
    resumed = Supervisor(second.config, second.executor, run_id=second.run_id)
    final = resumed.resume()
    assert final["state"] == S.HALTED_FAILED
    assert "reads it on every path" in final["halt_reason"]
    assert resumed.executor.tier_calls == []


def _answers_for(artifact, **overrides):
    """Answer every question the recommendation raises, with a usable value."""
    defaults = {
        "point_scale": 14.0,
        "weekly_performance_residual_coefficient": 0.35,
        "weekly_movement_cap_points": 6.0,
        "recent_form_weights": [0.5, 0.3, 0.2],
        "blowout_treatment": {"cap_margin": 28},
        "sample_size_regularization": {"k": 4},
        "game_sd_points": 16.8,
        "fcs_point_adapter": 2.5,
    }
    answers = {
        request["parameter"]: {
            "value": defaults[request["parameter"]],
            "status": D.HUMAN_SELECTION_REQUIRED,
        }
        for request in artifact["human_disposition_requests"]
    }
    answers.update(overrides)
    return answers


def test_a_mixed_parameter_vector_reaches_parameter_recommendation_ready(tmp_path):
    supervisor, report = _drive(tmp_path, _mixed_manifest_payload())
    assert report["state"] == S.AWAITING_HUMAN_APPROVAL

    artifact = json.loads(
        (supervisor.run_dir / "recommendation" / "recommendation.json").read_text("utf-8")
    )
    vector = artifact["disposition_vector"]
    assert vector == {
        "weekly_performance_residual_coefficient": D.CIRCULAR_NOT_IDENTIFIABLE,
        "weekly_movement_cap_points": D.CIRCULAR_NOT_IDENTIFIABLE,
        "recent_form_weights": D.UNIDENTIFIED,
        "blowout_treatment": D.FIT_RESULT,
        "sample_size_regularization": D.FIT_RESULT,
        "game_sd_points": D.FIXED_PRIOR,
        "point_scale": D.CIRCULAR_NOT_IDENTIFIABLE,
        "fcs_point_adapter": D.MISSING_FAIL_CLOSED,
    }
    # Five distinct epistemic classes in one approvable artifact.
    assert len(set(vector.values())) == 5
    recent_form = next(
        p for p in artifact["parameters"] if p["parameter"] == "recent_form_weights"
    )
    assert recent_form["disposition_reason"] == D.RECENT_FORM_UNIDENTIFIED_REASON
    assert recent_form["recommended_value"] is None
    # Nothing was invented for the parameters that carry no measurement.
    for name, disposition in vector.items():
        value = artifact["recommended_vector"][name]
        assert (value is not None) == (disposition in D.CARRIES_VALUE), name


# --- 10: approval binds values and epistemic statuses ------------------------


def test_approval_binds_both_values_and_epistemic_statuses(tmp_path):
    supervisor, _ = _drive(tmp_path, _mixed_manifest_payload())
    artifact = json.loads(
        (supervisor.run_dir / "recommendation" / "recommendation.json").read_text("utf-8")
    )
    answers = _answers_for(artifact)

    # An approval that ignores the questions is refused, not silently accepted.
    with pytest.raises(GovernanceBlock, match="asks for a human disposition"):
        supervisor.approve(
            recommendation_sha256=supervisor.state.recommendation_sha256,
            approver="chairman",
        )
    # A status nobody recognises is refused.
    with pytest.raises(InputValidationError, match="unknown disposition"):
        supervisor.approve(
            recommendation_sha256=supervisor.state.recommendation_sha256,
            approver="chairman",
            dispositions={**answers, "point_scale": {"value": 14.0, "status": "PROBABLY_FINE"}},
        )
    # A value under a status that cannot carry one is refused.
    with pytest.raises(GovernanceBlock, match="must not also report"):
        supervisor.approve(
            recommendation_sha256=supervisor.state.recommendation_sha256,
            approver="chairman",
            dispositions={
                **answers,
                "point_scale": {"value": 14.0, "status": D.CIRCULAR_NOT_IDENTIFIABLE},
            },
        )
    # Answering for a parameter that was not asked about would overwrite a
    # measured value at the one moment nobody is watching for a substitution.
    with pytest.raises(GovernanceBlock, match="did not ask about"):
        supervisor.approve(
            recommendation_sha256=supervisor.state.recommendation_sha256,
            approver="chairman",
            dispositions={**answers, "blowout_treatment": {"value": 9.9, "status": D.FIT_RESULT}},
        )

    granted = supervisor.approve(
        recommendation_sha256=supervisor.state.recommendation_sha256,
        approver="chairman",
        dispositions=answers,
    )
    record = json.loads(
        (supervisor.run_dir / "approval" / "approval.json").read_text("utf-8")
    )
    assert record["approved_vector"]["point_scale"] == 14.0
    assert record["approved_dispositions"]["point_scale"] == D.HUMAN_SELECTION_REQUIRED
    assert record["approved_dispositions"]["blowout_treatment"] == D.FIT_RESULT
    assert set(record["approved_dispositions"]) == set(EV.GOVERNED_PARAMETERS)

    # The digest covers the statuses as well as the values: changing only a
    # status produces a different approval.
    from ncaaf_engine.simulation.dynamic_weekly_mc_v3.supervisor.approval import (
        ApprovalRecord,
    )
    from ncaaf_engine.simulation.dynamic_weekly_mc_v3.supervisor.recommendation import (
        RunBindings,
    )

    rebuilt = ApprovalRecord(
        run_id=record["run_id"],
        action=record["action"],
        recommendation_sha256=record["recommendation_sha256"],
        approver=record["approver"],
        approved_at=record["approved_at"],
        bindings=RunBindings(**record["bindings"]),
        approved_vector=dict(record["approved_vector"]),
        approved_dispositions=dict(record["approved_dispositions"]),
        human_answers=dict(record["human_answers"]),
        note=record["note"],
    )
    assert rebuilt.approval_digest == granted["approval_digest"]
    restated = replace(
        rebuilt,
        approved_dispositions={**rebuilt.approved_dispositions, "point_scale": D.PRIOR_ONLY},
    )
    assert restated.approval_digest != granted["approval_digest"]


# --- 11-12: one gate, and structural failure still blocks --------------------


def test_no_second_human_gate_exists_between_500_2000_and_10000(tmp_path):
    # Structural: after the approval there is no edge to a human stop at all.
    for state in S.POST_APPROVAL_STATES:
        assert S.HALTED_FOR_HUMAN_REVIEW not in S.LEGAL_TRANSITIONS[state]
    assert S.transition_summary()["human_gate_count"] == 1

    supervisor, _ = _drive(tmp_path)
    supervisor.approve(
        recommendation_sha256=supervisor.state.recommendation_sha256, approver="chairman"
    )
    resumed = Supervisor(supervisor.config, supervisor.executor, run_id=supervisor.run_id)
    final = resumed.resume()
    assert final["state"] == S.COMPLETE
    assert resumed.executor.tier_calls == ["DEV", "ANALYSIS", "PUBLISH"]
    # One approval traversal, and no stop for a human anywhere after it.
    transitions = [h["to"] for h in final["history"]]
    assert transitions.count(S.PARAMETERS_APPROVED) == 1
    assert S.HALTED_FOR_HUMAN_REVIEW not in transitions


def test_a_500_structural_failure_blocks_2000(tmp_path):
    supervisor, _ = _drive(tmp_path, executor=MixedExecutor(fail_tier="DEV"))
    supervisor.approve(
        recommendation_sha256=supervisor.state.recommendation_sha256, approver="chairman"
    )
    resumed = Supervisor(supervisor.config, supervisor.executor, run_id=supervisor.run_id)
    final = resumed.resume()
    assert final["state"] == S.HALTED_FAILED
    assert resumed.executor.tier_calls == ["DEV"]
    assert not (resumed.run_dir / "analysis_2000" / "report.json").exists()
    detail = json.loads(
        next((resumed.run_dir / "stage_results").glob("*_dev_500.json")).read_text("utf-8")
    )
    failed = [c["check"] for c in detail["detail"]["checks"] if c["status"] == S.FAIL]
    assert failed == ["no_failed_assertions"]


# --- 13-17: convergence, and many outputs at once ----------------------------


def _sample(tier, paths, values, **kinds):
    return CV.TierSample(
        tier=tier,
        paths=paths,
        quantities={
            name: CV.Quantity(
                name=name,
                value=value,
                kind=kinds.get(name, CV.BERNOULLI_PROBABILITY),
                paths=paths,
            )
            for name, value in values.items()
        },
    )


def test_normal_monte_carlo_fluctuation_passes_the_500_2000_comparison():
    # 0.10 at 500 paths has SE 0.0134; 0.108 at 2,000 has SE 0.0069. The runs are
    # about half a combined standard error apart, which is what agreement looks
    # like when the two runs are honest.
    dev = _sample("DEV", 500, {"champion_p": 0.10, "cfp_p": 0.42})
    analysis = _sample("ANALYSIS", 2000, {"champion_p": 0.108, "cfp_p": 0.404})
    result = CV.diagnose(dev, analysis, policy=CV.ConvergencePolicy(headline=("champion_p",)))
    assert result["classification"] == "PASS"
    assert result["reasons"] == []
    row = next(r for r in result["comparisons"] if r["name"] == "champion_p")
    assert row["classification"] == CV.WITHIN_MONTE_CARLO_NOISE
    assert row["z"] < 1.0
    assert pytest.approx(row["baseline_se"], rel=1e-6) == CV.binomial_se(0.10, 500)


def test_systematic_divergence_fails():
    dev = _sample("DEV", 500, {f"team_{i}_p": 0.20 for i in range(200)})
    # Every output moved the same way. One at a time each would be unremarkable;
    # two hundred at once is a different model, not a different sample.
    analysis = _sample("ANALYSIS", 2000, {f"team_{i}_p": 0.28 for i in range(200)})
    result = CV.diagnose(dev, analysis)
    assert result["classification"] == "FAIL"
    assert result["wide_family"]["exceeds_expected_rate"] is True
    assert any("systematic" in r for r in result["reasons"])


def test_pass_with_advisory_continues_through_every_tier(tmp_path):
    # A run-level mean with no reported standard error cannot be diagnosed. It is
    # recorded as undiagnosed -- never silently passed -- and the run continues,
    # because an undiagnosable quantity is not evidence of divergence.
    dev = _tier_report(500, {}, {"champion_probability_top1": 0.10})
    analysis = _tier_report(2000, {}, {"champion_probability_top1": 0.104})
    for report in (dev, analysis):
        report["quantities"]["expected_wins_top1"] = {
            "kind": CV.RUN_LEVEL_MEAN,
            "value": 9.4,
        }
    result = gates.gate_analysis_2000(analysis, dev_report=dev)
    assert result.status == S.PASS_WITH_ADVISORY
    assert any("no variance was invented" in a.lower() for a in result.advisories)
    assert result.detail["convergence"]["not_diagnosed"] == ["expected_wins_top1"]

    class UndiagnosableExecutor(MixedExecutor):
        def execute_tier(self, tier_name, vector, *, bindings, basetemp=None):
            report = super().execute_tier(tier_name, vector, bindings=bindings)
            report["quantities"]["expected_wins_top1"] = {
                "kind": CV.RUN_LEVEL_MEAN,
                "value": 9.4,
            }
            return report

    supervisor, _ = _drive(tmp_path, executor=UndiagnosableExecutor())
    supervisor.approve(
        recommendation_sha256=supervisor.state.recommendation_sha256, approver="chairman"
    )
    resumed = Supervisor(supervisor.config, supervisor.executor, run_id=supervisor.run_id)
    final = resumed.resume()
    assert final["state"] == S.COMPLETE
    assert (resumed.run_dir / "freeze" / "freeze.json").exists()


def test_one_expected_stochastic_outlier_among_hundreds_does_not_fail():
    values = {f"team_{i}_p": 0.20 for i in range(300)}
    dev = _sample("DEV", 500, values)
    moved = dict(values)
    # One output sits about 3.6 combined standard errors out -- past the
    # per-output flag, and inside the rate that flag fires at by chance when
    # three hundred outputs are inspected at once.
    moved["team_7_p"] = 0.2695
    analysis = _sample("ANALYSIS", 2000, moved)
    result = CV.diagnose(dev, analysis)
    assert result["classification"] == "PASS_WITH_ADVISORY"
    assert [o["name"] for o in result["wide_family"]["outliers"]] == ["team_7_p"]
    assert result["wide_family"]["exceeds_expected_rate"] is False
    # Flagged, never hidden.
    assert any("team_7_p" in a for a in result["advisories"])
    row = next(r for r in result["comparisons"] if r["name"] == "team_7_p")
    assert row["classification"] == CV.OUTLIER_WITHIN_EXPECTED_RATE
    assert CV.OUTLIER_Z < row["z"] < CV.CATASTROPHIC_Z


def test_a_catastrophic_single_outlier_still_fails():
    values = {f"team_{i}_p": 0.20 for i in range(300)}
    dev = _sample("DEV", 500, values)
    moved = dict(values)
    moved["team_7_p"] = 0.42
    analysis = _sample("ANALYSIS", 2000, moved)
    result = CV.diagnose(dev, analysis)
    assert result["classification"] == "FAIL"
    assert result["catastrophic"]["breaches"] == ["team_7_p"]
    row = next(r for r in result["comparisons"] if r["name"] == "team_7_p")
    assert row["classification"] == CV.CATASTROPHIC_DIVERGENCE
    assert row["z"] >= CV.CATASTROPHIC_Z


def test_a_headline_quantity_is_held_to_a_family_wise_threshold():
    dev = _sample("DEV", 500, {"champion_p": 0.20, "cfp_p": 0.30})
    analysis = _sample("ANALYSIS", 2000, {"champion_p": 0.2695, "cfp_p": 0.30})
    policy = CV.ConvergencePolicy(headline=("champion_p",))
    result = CV.diagnose(dev, analysis, policy=policy)
    # The same 3.6-sigma move that is forgivable among three hundred outputs is
    # not forgivable in a predeclared family of one.
    assert result["classification"] == "FAIL"
    assert result["headline"]["breaches"] == ["champion_p"]
    assert result["headline"]["threshold_z"] == pytest.approx(CV.family_wise_z(1), rel=1e-9)


def test_a_headline_quantity_that_cannot_be_diagnosed_is_not_a_pass():
    dev = _sample("DEV", 500, {"champion_p": 0.20})
    analysis = _sample("ANALYSIS", 2000, {"champion_p": 0.20})
    result = CV.diagnose(dev, analysis, policy=CV.ConvergencePolicy(headline=("cfp_p",)))
    assert result["classification"] == "FAIL"
    assert result["headline"]["not_diagnosable"] == ["cfp_p"]


def test_the_publish_gate_compares_stability_against_the_analysis_tier():
    analysis = _tier_report(2000, {"a": "1"}, {"champion_probability_top1": 0.10})
    publish = _tier_report(10000, {"a": "1"}, {"champion_probability_top1": 0.104})
    assert (
        gates.gate_publish_10000(
            publish, expected_bindings={"a": "1"}, analysis_report=analysis
        ).status
        == S.PASS
    )
    diverged = _tier_report(10000, {"a": "1"}, {"champion_probability_top1": 0.40})
    assert (
        gates.gate_publish_10000(
            diverged, expected_bindings={"a": "1"}, analysis_report=analysis
        ).status
        == S.FAIL
    )
    # A freeze cannot be earned by having nothing to compare against.
    assert gates.gate_publish_10000(publish, expected_bindings={"a": "1"}).status == S.FAIL


# --- 18: supersession ---------------------------------------------------------


def test_stale_superseded_evidence_cannot_override_current_r2_eligibility(tmp_path):
    stale = AU.EligibilityClaim(
        generation="AGENT12_R5_DISCOVERY",
        subject="blowout_treatment",
        claim=EV.FIT_ALLOWED,
        source="V3_CALIBRATION_EVIDENCE_DISCOVERY_R5.json",
        rationale="Blocked on an unratified P-to-strength transform.",
    )
    current = AU.EligibilityClaim(
        generation=AU.CURRENT_AUTHORITY_GENERATION,
        subject="blowout_treatment",
        claim=EV.CIRCULAR_NOT_IDENTIFIABLE,
        source="V3_AGENT12_R2_EVIDENCE_MANIFEST.json",
    )
    winner, superseded = AU.resolve_claim("blowout_treatment", [stale, current])
    assert winner.claim == EV.CIRCULAR_NOT_IDENTIFIABLE
    assert [c.generation for c in superseded] == ["AGENT12_R5_DISCOVERY"]

    # A superseded generation cannot act as the authority at all.
    with pytest.raises(GovernanceBlock, match="superseded by"):
        AU.require_current_authority("AGENT12_R5_DISCOVERY", subject="test")
    with pytest.raises(GovernanceBlock, match="superseded by"):
        _domain_manifest(generation="AGENT12_R5_DISCOVERY")
    # And a generation nobody recognises has no authority, rather than the least.
    with pytest.raises(GovernanceBlock, match="Unknown evidence authority"):
        AU.authority_rank("AGENT12_R99")

    # End to end: the run-local manifest says fit it, the current authority says
    # it is circular, and no search runs.
    authority = SUP.authority_manifest_payload(
        supersedes=["AGENT12_R5_DISCOVERY"],
        parameter_eligibility={"blowout_treatment": EV.CIRCULAR_NOT_IDENTIFIABLE},
    )
    supervisor, report = _drive(tmp_path, authority=authority)
    assert report["state"] == S.AWAITING_HUMAN_APPROVAL
    assert supervisor.eligibility_of("blowout_treatment") == EV.CIRCULAR_NOT_IDENTIFIABLE
    artifact = json.loads(
        (supervisor.run_dir / "recommendation" / "recommendation.json").read_text("utf-8")
    )
    assert artifact["disposition_vector"]["blowout_treatment"] == (
        D.CIRCULAR_NOT_IDENTIFIABLE
    )
    assert artifact["recommended_vector"]["blowout_treatment"] is None
    detail = json.loads(
        next(
            (supervisor.run_dir / "stage_results").glob("*_synthetic_evidence.json")
        ).read_text("utf-8")
    )["detail"]
    assert detail["authority_overrides"] == ["blowout_treatment"]
    resolved = detail["supersession"]["subjects"]["blowout_treatment"]
    assert resolved["authority"] == AU.CURRENT_AUTHORITY_GENERATION
    # The older claim is recorded, not erased.
    assert [c["generation"] for c in resolved["superseded"]] == ["AGENT12_R5_DISCOVERY"]


# --- 19-20: Wave-1 ingestion --------------------------------------------------


def _expectation(**overrides):
    fields = {
        "execution_commit": "0" * 40,
        "execution_tree": "tree" + "0" * 60,
        "evidence_manifest_sha256": "m" * 64,
        "dataset_sha256": SUP.DATASET_SHA256,
        "split_sha256": SUP.SPLIT_SHA256,
        "candidate_universe_digest": "u" * 64,
        "scoring_oracle_digest": "o" * 64,
        "experiment_config_sha256": "e" * 64,
        "field_admission_sha256": "f" * 64,
    }
    fields.update(overrides)
    return W1.Wave1Expectation(**fields)


def test_a_wave1_package_with_the_wrong_sha_is_refused():
    package = W1.parse_package(
        json.dumps(SUP.wave1_package_payload()).encode("utf-8"), read_from_commit="0" * 40
    )
    assert package.verify(_expectation())["status"] == W1.WAVE1_ACCEPTED

    for wrong in (
        {"dataset_sha256": "9" * 64},
        {"split_sha256": "9" * 64},
        {"candidate_universe_digest": "9" * 64},
        {"scoring_oracle_digest": "9" * 64},
        {"experiment_config_sha256": "9" * 64},
        {"field_admission_sha256": "9" * 64},
        {"evidence_manifest_sha256": "9" * 64},
        {"execution_commit": "1" * 40},
        {"execution_tree": "moved"},
    ):
        with pytest.raises(GovernanceBlock, match="different world"):
            package.verify(_expectation(**wrong))

    # A package that declares its own digest and does not match it is refused
    # before any binding is compared.
    payload = SUP.wave1_package_payload(package_sha256="c" * 64)
    with pytest.raises(GovernanceBlock, match="different artifact"):
        W1.parse_package(json.dumps(payload).encode("utf-8"))

    # Wave 1 is scoped, and a package claiming more than its scope is refused.
    out_of_scope = SUP.wave1_package_payload(
        results={"game_sd_points": {"status": "FIT_RESULT", "value": 16.8}}
    )
    with pytest.raises(GovernanceBlock, match="not\\s+scoped to settle"):
        W1.parse_package(json.dumps(out_of_scope).encode("utf-8"))

    # A non-fit status that also carries a measurement is refused.
    contradictory = SUP.wave1_package_payload(
        results={"blowout_treatment": {"status": "UNIDENTIFIED", "value": 0.4}}
    )
    with pytest.raises(GovernanceBlock, match="must not also report"):
        W1.parse_package(json.dumps(contradictory).encode("utf-8"))


def test_a_wave1_package_may_be_absent_during_plan_mode(tmp_path):
    config = make_config(tmp_path)
    supervisor = Supervisor(config, FakeExecutor(), run_id="PLAN_WAVE1")
    plan = supervisor.plan()
    assert plan["mode"] == "PLAN_ONLY"
    assert plan["wave1"]["status"] == W1.WAVE1_NOT_PRESENT
    assert plan["wave1"]["verified"] is False
    assert plan["wave1"]["parameters"] == list(W1.WAVE1_PARAMETERS)
    assert not supervisor.run_dir.exists()

    # Declared but not yet published is also absence, reported with the commit
    # that was looked in so the operator can see where it looked.
    repo, commit = SUP.publish_bytes(
        "reference/evidence/placeholder.txt", b"wave 1 has not published yet\n"
    )
    declared = replace(
        config,
        wave1=W1.Wave1Binding(ref=commit, path="wave1/result.json", commit=commit, repo=repo),
        repo=repo,
    )
    absent = Supervisor(declared, FakeExecutor(), run_id="PLAN_WAVE1_DECLARED").plan()
    assert absent["wave1"]["status"] == W1.WAVE1_NOT_PRESENT
    assert absent["wave1"]["resolved_commit"] == commit
    assert "has not published a result yet" in absent["wave1"]["reason"]


def test_an_absent_wave1_package_changes_nothing_about_the_run(tmp_path):
    supervisor, report = _drive(tmp_path, _mixed_manifest_payload())
    assert report["state"] == S.AWAITING_HUMAN_APPROVAL
    coarse = json.loads(
        next(
            (supervisor.run_dir / "stage_results").glob("*_coarse_search.json")
        ).read_text("utf-8")
    )["detail"]
    assert coarse["wave1"]["status"] == W1.WAVE1_NOT_PRESENT
    assert coarse["wave1_settled"] == []
    # The interface was consulted and found nothing, and the run fitted the two
    # Wave-1 parameters itself. Absence authorised nothing and blocked nothing.
    artifact = json.loads(
        (supervisor.run_dir / "recommendation" / "recommendation.json").read_text("utf-8")
    )
    assert artifact["disposition_vector"]["blowout_treatment"] == D.FIT_RESULT
    assert artifact["disposition_vector"]["sample_size_regularization"] == D.FIT_RESULT


# --- doctrine -----------------------------------------------------------------


def test_the_supervisor_supports_every_declared_disposition():
    assert set(D.DISPOSITIONS) == {
        "FIT_RESULT",
        "FIXED_PRIOR",
        "PRIOR_ONLY",
        "UNIDENTIFIED",
        "CIRCULAR_NOT_IDENTIFIABLE",
        "HUMAN_SELECTION_REQUIRED",
        "RESIDUAL_DERIVED",
        "MISSING_FAIL_CLOSED",
        "WITNESS_ONLY",
    }
    assert D.ESTIMATOR_ADMISSIBLE == (D.FIT_RESULT,)
    assert set(D.PRODUCTION_VALUE_SEMANTICS) == set(EV.GOVERNED_PARAMETERS)
    assert (
        D.PRODUCTION_VALUE_SEMANTICS["fcs_point_adapter"] == D.VALUE_REQUIRED_AT_USE_SITE
    )


def test_no_parameter_is_promoted_and_no_season_is_simulated(tmp_path):
    supervisor, _ = _drive(tmp_path, _mixed_manifest_payload())
    canonical = json.loads(
        Path("config/dynamic_weekly_mc_v3/v3_experimental.json").read_text("utf-8")
    )
    assert all(value is None for value in canonical["calibration"].values())
    artifact = json.loads(
        (supervisor.run_dir / "recommendation" / "recommendation.json").read_text("utf-8")
    )
    assert artifact["writes_canonical_config"] is False
    assert supervisor.executor.tier_calls == []
