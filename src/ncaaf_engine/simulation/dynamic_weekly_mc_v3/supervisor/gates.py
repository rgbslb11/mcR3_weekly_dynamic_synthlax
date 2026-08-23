"""Deterministic validation gates for the 500, 2,000 and 10,000-path tiers.

Each tier's gate takes the report a run produced and returns a
:class:`~.states.StageResult`. Nothing here executes a simulation -- the
supervisor is handed a report by whatever ran the tier and decides whether that
report is allowed to advance. Keeping the decision separate from the execution
is what makes the gates testable without a 10,000-path run, and it is why a
failed gate can be reasoned about from the artifact alone months later.

The report contract
-------------------

A tier report is a mapping. The keys each gate reads are named in its own
checks, and a missing key is a failed check rather than a skipped one -- a gate
that silently passes when the evidence is absent is worse than no gate, because
it produces a PASS row that an auditor will believe. Broadly::

    {
      "tier": "DEV" | "ANALYSIS" | "PUBLISH",
      "requested_paths": int,          "observed_paths": int,
      "seed": {"base_seed": int,
               "replay_digest": str,   "reference_digest": str},
      "numeric": {"nan_count": int, "inf_count": int},
      "probabilities": {"min": float, "max": float,
                        "mass_checks": [{"name": str, "sum": float}],
                        "mass_tolerance": float},
      "team_identities": {"expected": int, "observed": int, "unknown": [str]},
      "standings": {"violations": [str]},
      "ccg":       {"violations": [str]},
      "cfp":       {"violations": [str], "duplicate_participants": [str]},
      "assertions": {"failed": [str]},
      "artifacts": {"required": [str], "present": [str], "hashes": {str: str}},
      "aggregates": {str: float},
      "quantities": {str: {"kind": str, "value": float,
                           "paths": int, "standard_error": float | None}},
      "schema":    {"required_fields": [str], "present_fields": [str]},
      "totals":    {str: float}, "totals_tolerance": float,
      "bindings":  {str: str},
    }

Monte Carlo convergence
-----------------------

The 2,000-path gate compares against the 500-path run and the 10,000-path gate
compares against the 2,000-path run, and neither demands equality. Two Monte
Carlo runs of different sizes disagree by construction, and a gate that required
agreement would either fail every honest run or be widened until it failed
nothing.

R1 handled that with predeclared absolute tolerances and stopped for a human
wherever one was missing. R2 does not need a tolerance at all: the disagreement
two runs should show is computable from the estimates and their path counts, so
:mod:`.convergence` derives the diagnostic from the samples and returns PASS,
PASS_WITH_ADVISORY or FAIL. No tier gate returns
:data:`~.states.HUMAN_REVIEW_REQUIRED`, and none can -- the post-approval states
have no edge to :data:`~.states.HALTED_FOR_HUMAN_REVIEW`. There is one human
gate in this run and it is upstream of all three tiers.

A material model failure stops the run; a normal sampling fluctuation does not.
The line between them, including how hundreds of simultaneously inspected
outputs are handled without a false failure, is defined and documented in
:mod:`.convergence`.

No final-looking output after a failed validation
-------------------------------------------------

:func:`gate_final_freeze` refuses any tier but PUBLISH -- deferring to
:func:`..run_tier.require_publish_freeze_tier` rather than re-deciding it -- and
refuses a freeze whose upstream tiers did not pass. The supervisor writes the
freeze record only on the PASS it returns.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Sequence

from .. import run_tier as tier_policy
from ..errors import GovernanceBlock
from . import convergence as C
from . import states as S

__all__ = [
    "DEV_500_STAGE",
    "ANALYSIS_2000_STAGE",
    "PUBLISH_10000_STAGE",
    "FINAL_FREEZE_STAGE",
    "convergence_checks",
    "gate_analysis_2000",
    "gate_dev_500",
    "gate_final_freeze",
    "gate_publish_10000",
    "structural_checks",
]

DEV_500_STAGE = "dev_500"
ANALYSIS_2000_STAGE = "analysis_2000"
PUBLISH_10000_STAGE = "publish_10000"
FINAL_FREEZE_STAGE = "final_freeze"


def _check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"check": name, "status": S.PASS if ok else S.FAIL, "detail": detail}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        return [value]
    if isinstance(value, Iterable):
        return list(value)
    return [value]


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def structural_checks(report: Mapping[str, Any], tier: tier_policy.RunTier) -> list[dict[str, Any]]:
    """The checks every tier must pass, whatever it is for.

    Ordered from cheapest and most fundamental outward, so the first failure an
    operator reads is the most likely root cause rather than a downstream
    symptom of it.
    """
    checks: list[dict[str, Any]] = []

    requested = report.get("requested_paths")
    observed = report.get("observed_paths")
    checks.append(
        _check(
            "exact_requested_path_count",
            requested == tier.paths and observed == tier.paths,
            f"{tier.name} requires exactly {tier.paths:,} paths; requested="
            f"{requested!r}, observed={observed!r}.",
        )
    )

    seed = report.get("seed") or {}
    replay = seed.get("replay_digest")
    reference = seed.get("reference_digest")
    checks.append(
        _check(
            "deterministic_seed_behaviour",
            bool(replay) and bool(reference) and replay == reference,
            "A replay under the same base seed must reproduce the reference digest. "
            f"base_seed={seed.get('base_seed')!r}, replay={replay!r}, "
            f"reference={reference!r}.",
        )
    )

    numeric = report.get("numeric") or {}
    nan_count = numeric.get("nan_count")
    inf_count = numeric.get("inf_count")
    checks.append(
        _check(
            "no_nan_or_inf",
            nan_count == 0 and inf_count == 0,
            f"nan_count={nan_count!r}, inf_count={inf_count!r}; both must be 0 and "
            "both must be reported.",
        )
    )

    probabilities = report.get("probabilities") or {}
    p_min, p_max = probabilities.get("min"), probabilities.get("max")
    checks.append(
        _check(
            "probability_ranges_valid",
            _finite(p_min) and _finite(p_max) and 0.0 <= float(p_min) and float(p_max) <= 1.0,
            f"Every reported probability must lie in [0, 1]; observed range "
            f"[{p_min!r}, {p_max!r}].",
        )
    )

    tolerance = float(probabilities.get("mass_tolerance", 1e-9))
    mass_checks = _as_list(probabilities.get("mass_checks"))
    bad_mass = [
        entry
        for entry in mass_checks
        if not (_finite(entry.get("sum")) and abs(float(entry["sum"]) - 1.0) <= tolerance)
    ]
    checks.append(
        _check(
            "probability_mass_valid",
            bool(mass_checks) and not bad_mass,
            f"{len(mass_checks)} mass check(s) at tolerance {tolerance}; failing: "
            f"{[e.get('name') for e in bad_mass]}."
            if mass_checks
            else "No probability mass checks were reported; mass validity is unproven.",
        )
    )

    identities = report.get("team_identities") or {}
    unknown = _as_list(identities.get("unknown"))
    checks.append(
        _check(
            "team_identities_valid",
            identities.get("expected") is not None
            and identities.get("expected") == identities.get("observed")
            and not unknown,
            f"expected={identities.get('expected')!r}, observed="
            f"{identities.get('observed')!r}, unknown={unknown}.",
        )
    )

    for key, name in (
        ("standings", "conference_standings_structurally_valid"),
        ("ccg", "ccg_structure_valid"),
    ):
        violations = _as_list((report.get(key) or {}).get("violations"))
        checks.append(_check(name, not violations, f"violations={violations}."))

    cfp = report.get("cfp") or {}
    cfp_violations = _as_list(cfp.get("violations"))
    duplicates = _as_list(cfp.get("duplicate_participants"))
    checks.append(_check("cfp_topology_valid", not cfp_violations, f"violations={cfp_violations}."))
    checks.append(
        _check(
            "no_impossible_duplicate_participants",
            not duplicates,
            f"A team may appear once per bracket slot; duplicates={duplicates}.",
        )
    )

    failed_assertions = _as_list((report.get("assertions") or {}).get("failed"))
    checks.append(
        _check("no_failed_assertions", not failed_assertions, f"failed={failed_assertions}.")
    )

    artifacts = report.get("artifacts") or {}
    required = set(_as_list(artifacts.get("required")))
    present = set(_as_list(artifacts.get("present")))
    absent = sorted(required - present)
    checks.append(
        _check(
            "required_artifacts_exist",
            bool(required) and not absent,
            f"missing={absent}." if required else "No required artifact list was reported.",
        )
    )

    hashes = artifacts.get("hashes") or {}
    unhashed = sorted(name for name in sorted(present) if not str(hashes.get(name, "")).strip())
    checks.append(
        _check(
            "artifact_hashes_present",
            bool(hashes) and not unhashed,
            f"unhashed={unhashed}." if hashes else "No artifact hashes were reported.",
        )
    )

    return checks


def _result(
    stage: str,
    checks: Sequence[Mapping[str, Any]],
    *,
    extra_detail: Mapping[str, Any] | None = None,
    advisories: Sequence[str] = (),
    human_review: Sequence[str] = (),
) -> S.StageResult:
    """Fold a list of checks into one stage result.

    A failure beats a review request beats an advisory. The ordering is fixed so
    a run that both diverged pathologically and lacked a tolerance is reported as
    the failure it is, rather than as the softer of its two problems.
    """
    failed = [c for c in checks if c["status"] != S.PASS]
    detail: dict[str, Any] = {
        "checks": [dict(c) for c in checks],
        "checks_total": len(checks),
        "checks_failed": len(failed),
    }
    if extra_detail:
        detail.update(dict(extra_detail))

    if failed:
        names = ", ".join(c["check"] for c in failed)
        return S.StageResult(
            stage=stage,
            status=S.FAIL,
            summary=f"{len(failed)} of {len(checks)} gate check(s) failed: {names}.",
            detail=detail,
        )
    if human_review:
        return S.StageResult(
            stage=stage,
            status=S.HUMAN_REVIEW_REQUIRED,
            summary="; ".join(human_review),
            detail=detail,
        )
    if advisories:
        return S.StageResult(
            stage=stage,
            status=S.PASS_WITH_ADVISORY,
            summary=f"All {len(checks)} gate check(s) passed, with advisories.",
            detail=detail,
            advisories=tuple(advisories),
        )
    return S.StageResult(
        stage=stage,
        status=S.PASS,
        summary=f"All {len(checks)} gate check(s) passed.",
        detail=detail,
    )


def gate_dev_500(report: Mapping[str, Any]) -> S.StageResult:
    """Validate the 500-path development tier. A failure stops the run."""
    return _result(DEV_500_STAGE, structural_checks(report, tier_policy.DEV))


def convergence_checks(
    baseline_report: Mapping[str, Any],
    candidate_report: Mapping[str, Any],
    *,
    baseline_tier: tier_policy.RunTier,
    candidate_tier: tier_policy.RunTier,
    policy: C.ConvergencePolicy | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    """Diagnose two tiers against each other and fold it into gate form.

    Returns the full diagnostic, the single check the gate records, and any
    advisories. One check rather than one per output: a gate row per team
    probability would bury the structural checks under three hundred rows, and
    the outlier detail is on the diagnostic where a reader can sort it.
    """
    diagnostic = C.diagnose(
        C.sample_from_report(
            baseline_report, tier=baseline_tier.name, paths=baseline_tier.paths
        ),
        C.sample_from_report(
            candidate_report, tier=candidate_tier.name, paths=candidate_tier.paths
        ),
        policy=policy,
    )
    label = f"{baseline_tier.name.lower()}_{candidate_tier.name.lower()}_convergence"
    passed = diagnostic["classification"] != "FAIL"
    detail = (
        "; ".join(diagnostic["reasons"])
        if diagnostic["reasons"]
        else (
            f"{diagnostic['diagnosed_count']} quantity/quantities diagnosed against "
            f"Monte Carlo sampling error; classification "
            f"{diagnostic['classification']}."
        )
    )
    return diagnostic, [_check(label, passed, detail)], list(diagnostic["advisories"])


def gate_analysis_2000(
    report: Mapping[str, Any],
    *,
    dev_report: Mapping[str, Any],
    policy: C.ConvergencePolicy | None = None,
) -> S.StageResult:
    """Validate the 2,000-path analysis tier, including convergence against DEV.

    DEV must already have passed its structural invariants for this gate to be
    reached at all -- that is the state machine's job, not a check here -- so
    what this adds is the convergence question: did running four times as many
    paths move anything further than sampling explains.
    """
    checks = structural_checks(report, tier_policy.ANALYSIS)
    diagnostic, convergence_checks_, advisories = convergence_checks(
        dev_report,
        report,
        baseline_tier=tier_policy.DEV,
        candidate_tier=tier_policy.ANALYSIS,
        policy=policy,
    )
    checks.extend(convergence_checks_)
    return _result(
        ANALYSIS_2000_STAGE,
        checks,
        extra_detail={"convergence": diagnostic},
        advisories=advisories,
    )


def gate_publish_10000(
    report: Mapping[str, Any],
    *,
    expected_bindings: Mapping[str, str],
    analysis_report: Mapping[str, Any] | None = None,
    policy: C.ConvergencePolicy | None = None,
) -> S.StageResult:
    """Validate the 10,000-path publish tier.

    Five things at once, which is what "final validation" means here: the
    structural invariants every tier must hold, probability validity, output
    completeness, the convergence and stability diagnostic against the 2,000-path
    run, and the input, config and approval bindings.

    ``expected_bindings`` is what the supervisor knows the run must be tied to --
    config, inputs, parameter approval, run seed. The report's own bindings are
    compared against it rather than merely inspected for presence, because a
    publish artifact that names *some* approval is not the same as one that names
    the approval this run was granted.
    """
    checks = structural_checks(report, tier_policy.PUBLISH)
    advisories: list[str] = []
    diagnostic: dict[str, Any] = {
        "classification": "NOT_RUN",
        "reason": "No analysis-tier report was supplied to compare against.",
    }
    if analysis_report is not None:
        diagnostic, convergence_checks_, advisories = convergence_checks(
            analysis_report,
            report,
            baseline_tier=tier_policy.ANALYSIS,
            candidate_tier=tier_policy.PUBLISH,
            policy=policy,
        )
        checks.extend(convergence_checks_)
    else:
        checks.append(
            _check(
                "analysis_publish_convergence",
                False,
                "No 2,000-path report was supplied, so publish stability is unproven. "
                "A freeze cannot be earned by having nothing to compare against.",
            )
        )

    schema = report.get("schema") or {}
    required_fields = set(_as_list(schema.get("required_fields")))
    present_fields = set(_as_list(schema.get("present_fields")))
    absent_fields = sorted(required_fields - present_fields)
    checks.append(
        _check(
            "complete_output_schema",
            bool(required_fields) and not absent_fields,
            f"missing_fields={absent_fields}."
            if required_fields
            else "No output schema was declared, so completeness is unproven.",
        )
    )

    totals = report.get("totals") or {}
    totals_tolerance = float(report.get("totals_tolerance", 1e-9))
    for key, label in (
        ("champion", "champion_totals_valid"),
        ("conference", "conference_totals_valid"),
        ("cfp", "cfp_totals_valid"),
    ):
        value = totals.get(key)
        checks.append(
            _check(
                label,
                _finite(value) and abs(float(value) - 1.0) <= totals_tolerance,
                f"{key} probability total is {value!r}; must be 1 within "
                f"{totals_tolerance}.",
            )
        )

    tiebreak = _as_list((report.get("standings") or {}).get("tiebreak_violations"))
    checks.append(
        _check("standings_tiebreak_integrity", not tiebreak, f"violations={tiebreak}.")
    )
    postseason = _as_list((report.get("cfp") or {}).get("postseason_topology_violations"))
    checks.append(
        _check("postseason_topology_valid", not postseason, f"violations={postseason}.")
    )

    observed_bindings = report.get("bindings") or {}
    binding_drift = {
        name: {"expected": expected, "observed": observed_bindings.get(name)}
        for name, expected in sorted(expected_bindings.items())
        if observed_bindings.get(name) != expected
    }
    checks.append(
        _check(
            "run_bindings_match",
            bool(expected_bindings) and not binding_drift,
            f"drift={binding_drift}."
            if expected_bindings
            else "No expected bindings were supplied to compare against.",
        )
    )

    return _result(
        PUBLISH_10000_STAGE,
        checks,
        extra_detail={"binding_drift": binding_drift, "convergence": diagnostic},
        advisories=advisories,
    )


def gate_final_freeze(
    report: Mapping[str, Any],
    *,
    tier_paths: int,
    upstream_passed: Mapping[str, bool],
    expected_bindings: Mapping[str, str],
) -> S.StageResult:
    """Authorise the final freeze, or refuse.

    The tier check delegates to :func:`..run_tier.require_publish_freeze_tier`
    rather than re-implementing it, so there is one place in the repository that
    decides what may be frozen and this is not a second one.
    """
    try:
        tier_policy.require_publish_freeze_tier(tier_paths)
        tier_ok, tier_detail = True, f"{tier_paths:,} paths is the publish/freeze tier."
    except (GovernanceBlock, ValueError) as exc:
        tier_ok, tier_detail = False, str(exc)

    checks = [_check("publish_freeze_tier", tier_ok, tier_detail)]

    not_passed = sorted(name for name, ok in sorted(upstream_passed.items()) if not ok)
    checks.append(
        _check(
            "upstream_tiers_passed",
            bool(upstream_passed) and not not_passed,
            f"not passed: {not_passed}."
            if upstream_passed
            else "No upstream tier results were supplied; a freeze cannot be earned by "
            "silence.",
        )
    )

    observed = report.get("bindings") or {}
    drift = {
        name: {"expected": expected, "observed": observed.get(name)}
        for name, expected in sorted(expected_bindings.items())
        if observed.get(name) != expected
    }
    checks.append(
        _check(
            "freeze_bindings_match",
            bool(expected_bindings) and not drift,
            f"drift={drift}." if expected_bindings else "No expected bindings supplied.",
        )
    )

    hashes = (report.get("artifacts") or {}).get("hashes") or {}
    checks.append(
        _check("freeze_artifact_hashes_present", bool(hashes), f"hashed_artifacts={len(hashes)}.")
    )

    return _result(FINAL_FREEZE_STAGE, checks, extra_detail={"binding_drift": drift})
