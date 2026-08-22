"""R5 — byte-bound calibration evidence (CAL-R2 closure).

The first test in this file is a probe, not a regression guard: it demonstrates
the CAL-R2 weakness still present on the R2 path, so the rest of the file is
testing a fix for something that is shown to be real rather than asserted.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from ncaaf_engine.simulation.dynamic_weekly_mc_v3.calibration import (
    CalibrationDataset,
    CandidateRegime,
    ExperimentRecord,
    PRIMARY_CALIBRATION_METRIC,
    REQUIRED_OBSERVATION_COLUMNS,
    bind_promotion_evidence,
)
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.calibration_evidence import (
    ADMISSIBLE_SOURCE_AUTHORITY_CLASSES,
    EVIDENCE_BOUND_BYTE_VERIFIED,
    EvidenceEnvelope,
    IdentityReconciliation,
    MountReceipt,
    MountedDataset,
    REQUIRED_ENVELOPE_BINDINGS,
    bind_canonical_promotion_evidence,
    bind_evidence_envelope,
    mount_raw_source,
    register_governed_dataset,
    require_byte_bound_dataset,
    require_minimum_volume,
    verify_mount_receipt,
)
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.errors import (
    GovernanceBlock,
    InputValidationError,
)

GOOD_AUTHORITY = dict(
    source_authority="TEST_GOVERNED_RESULT_SOURCE",
    source_authority_class="GOVERNED_RESULT_SOURCE",
    retrieval_method="fixture write",
    retrieved_at="2026-08-21T00:00:00+00:00",
    declared_provenance="Observed final scores certified by the named result source.",
)


def _write_observations(path: Path, rows: int, *, seasons: int = 3) -> Path:
    """Write a conforming observation CSV.

    Splits are laid out temporally: the first third trains, the second validates,
    the last is holdout, and ``event_time`` increases monotonically so the
    partition is provably ordered rather than merely disjoint.
    """
    header = list(REQUIRED_OBSERVATION_COLUMNS) + ["event_time", "split"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for i in range(rows):
            season = 2020 + (i * seasons) // rows
            if i < rows // 3:
                split = "training"
            elif i < (2 * rows) // 3:
                split = "validation"
            else:
                split = "holdout"
            writer.writerow(
                [
                    f"G{i:05d}",
                    season,
                    (i % 12) + 1,
                    f"TEAM_{i % 40:03d}",
                    f"TEAM_{(i + 7) % 40:03d}",
                    3.5,
                    7.0,
                    "2026-01-01T00:00:00+00:00",
                    "2026-01-02T00:00:00+00:00",
                    _stamp(i),
                    split,
                ]
            )
    return path


def _stamp(i: int) -> str:
    """Monotonic ISO instants, one per observation."""
    day = 1 + i // 24
    hour = i % 24
    return f"2020-{1 + (day - 1) // 28:02d}-{1 + (day - 1) % 28:02d}T{hour:02d}:00:00+00:00"


def _ordered_events(path: Path) -> dict[str, tuple[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return {
            r["game_id"]: (r["split"], r["event_time"]) for r in csv.DictReader(fh)
        }


def _identity(names: int = 40, resolved: int | None = None, unresolved=()):
    return IdentityReconciliation(
        authority="2026_TEAM_CANONICAL_MASTER_v2_LLM_GROUNDING.md",
        authority_sha256="fd8fcb1bec40e26168d600e9cdb8fbf2de6a421fe13218face588a48c48a83a0",
        source_names=names,
        resolved=names if resolved is None else resolved,
        unresolved=tuple(unresolved),
    )


def _regime() -> CandidateRegime:
    return CandidateRegime(
        regime_id="R_TEST",
        values={"game_sd_points": 17.0},
        rationale="Fixture regime for evidence-binding tests. Never promoted.",
    )


def _experiment(dataset: CalibrationDataset, rmse: float = 11.5) -> ExperimentRecord:
    return ExperimentRecord(
        experiment_id="E_TEST",
        model_version="3.0.0-experimental-harness",
        configuration_version="V3-PLACEHOLDER-2026-08-21-R2-001",
        seed=1,
        regime_id="R_TEST",
        candidate_values={"game_sd_points": 17.0},
        dataset_id=dataset.dataset_id,
        dataset_sha256=dataset.sha256,
        objective_id="R2-CAL-PRIMARY",
        run_timestamp="2026-08-21T00:00:00+00:00",
        metrics={PRIMARY_CALIBRATION_METRIC: rmse},
        v2_1_control_comparison={},
        split="holdout",
    )


# --------------------------------------------------------------------------
# CAL-R2: the weakness, demonstrated
# --------------------------------------------------------------------------


def test_cal_r2_self_attesting_dataset_still_binds_on_the_r2_path(tmp_path):
    """A dataset that was never read binds successfully under the R2 gate.

    This is the defect. No file is opened anywhere in this test, yet the result
    is ``evidence_bound: True``.
    """
    typed = CalibrationDataset(
        dataset_id="HISTORICAL_GAME_RESULT_OBSERVATION_SET",
        path=tmp_path / "never-written.csv",
        sha256="00" * 32,
        rows=1500,
        columns=REQUIRED_OBSERVATION_COLUMNS,
    )
    bound = bind_promotion_evidence(
        _regime(),
        evidence={PRIMARY_CALIBRATION_METRIC: 0.0001},
        experiment=_experiment(typed, rmse=0.0001),
        dataset=typed,
    )
    assert bound["evidence_bound"] is True
    assert not typed.path.exists()


def test_byte_bound_path_refuses_the_same_self_attesting_dataset(tmp_path):
    typed = CalibrationDataset(
        dataset_id="HISTORICAL_GAME_RESULT_OBSERVATION_SET",
        path=tmp_path / "never-written.csv",
        sha256="00" * 32,
        rows=1500,
        columns=REQUIRED_OBSERVATION_COLUMNS,
    )
    receipt = MountReceipt(
        path=typed.path,
        sha256="00" * 32,
        byte_length=1,
        **GOOD_AUTHORITY,
    )
    with pytest.raises(GovernanceBlock, match="no longer exists|not found"):
        require_byte_bound_dataset(MountedDataset(dataset=typed, receipt=receipt))


# --------------------------------------------------------------------------
# Mount gates
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cls", [c for c in ("RESEARCH_ONLY", "ENGINE_OUTPUT", "SIMULATED_OR_SYNTHETIC", "UNKNOWN")]
)
def test_mount_refuses_every_inadmissible_authority_class(tmp_path, cls):
    p = _write_observations(tmp_path / "obs.csv", 30)
    kwargs = dict(GOOD_AUTHORITY, source_authority_class=cls)
    with pytest.raises(GovernanceBlock, match="classified"):
        mount_raw_source(p, **kwargs)


def test_only_one_authority_class_is_admissible():
    assert ADMISSIBLE_SOURCE_AUTHORITY_CLASSES == ("GOVERNED_RESULT_SOURCE",)


def test_mount_refuses_the_declared_provenance_found_in_the_local_corpus(tmp_path):
    """The refusal string is the one the discovered 2025 workbook actually carries."""
    p = _write_observations(tmp_path / "obs.csv", 30)
    kwargs = dict(
        GOOD_AUTHORITY,
        declared_provenance=(
            "SCHEDULE SYNTHETIC. SCORES SIMULATED. NCG result user-specified. "
            "Bowl names fictional."
        ),
    )
    with pytest.raises(GovernanceBlock, match="simulated"):
        mount_raw_source(p, **kwargs)


def test_mount_refuses_missing_and_empty_files(tmp_path):
    with pytest.raises(GovernanceBlock, match="not found"):
        mount_raw_source(tmp_path / "absent.csv", **GOOD_AUTHORITY)
    empty = tmp_path / "empty.csv"
    empty.write_bytes(b"")
    with pytest.raises(GovernanceBlock, match="empty"):
        mount_raw_source(empty, **GOOD_AUTHORITY)


def test_receipt_requires_named_authority_and_zoned_timestamp(tmp_path):
    p = _write_observations(tmp_path / "obs.csv", 30)
    good = mount_raw_source(p, **GOOD_AUTHORITY)
    with pytest.raises(InputValidationError, match="name its source authority"):
        MountReceipt(**{**good.as_dict(), "path": p, "source_authority": "  "})
    with pytest.raises(InputValidationError, match="ISO-8601"):
        MountReceipt(**{**good.as_dict(), "path": p, "retrieved_at": "yesterday"})
    with pytest.raises(InputValidationError, match="Unknown source authority class"):
        MountReceipt(**{**good.as_dict(), "path": p, "source_authority_class": "NICE"})


def test_verify_mount_receipt_detects_drift_and_deletion(tmp_path):
    p = _write_observations(tmp_path / "obs.csv", 30)
    receipt = mount_raw_source(p, **GOOD_AUTHORITY)
    verify_mount_receipt(receipt)

    p.write_bytes(p.read_bytes() + b"G99999,2020,1,A,B,0,0,x,y,z,holdout\n")
    with pytest.raises(GovernanceBlock, match="not the present bytes"):
        verify_mount_receipt(receipt)

    p.unlink()
    with pytest.raises(GovernanceBlock, match="no longer exists"):
        verify_mount_receipt(receipt)


def test_mounted_dataset_refuses_two_digests_for_one_file(tmp_path):
    p = _write_observations(tmp_path / "obs.csv", 30)
    mounted = register_governed_dataset(p, "DS", **GOOD_AUTHORITY)
    forged = CalibrationDataset(
        dataset_id="DS",
        path=p,
        sha256="ff" * 32,
        rows=mounted.dataset.rows,
        columns=mounted.dataset.columns,
    )
    with pytest.raises(GovernanceBlock, match="Two digests for one file"):
        MountedDataset(dataset=forged, receipt=mounted.receipt)


def test_register_governed_dataset_refuses_before_it_registers(tmp_path):
    """A refused source never reaches registration, so it never gets a digest."""
    p = _write_observations(tmp_path / "obs.csv", 30)
    with pytest.raises(GovernanceBlock, match="classified"):
        register_governed_dataset(
            p, "DS", **dict(GOOD_AUTHORITY, source_authority_class="RESEARCH_ONLY")
        )


def test_require_byte_bound_dataset_detects_row_and_schema_drift(tmp_path):
    p = _write_observations(tmp_path / "obs.csv", 30)
    mounted = register_governed_dataset(p, "DS", **GOOD_AUTHORITY)
    assert require_byte_bound_dataset(mounted)["bytes_reverified"] is True

    stale = MountedDataset(
        dataset=CalibrationDataset(
            dataset_id="DS",
            path=p,
            sha256=mounted.dataset.sha256,
            rows=mounted.dataset.rows + 5,
            columns=mounted.dataset.columns,
        ),
        receipt=mounted.receipt,
    )
    with pytest.raises(GovernanceBlock, match="re-reads to"):
        require_byte_bound_dataset(stale)


# --------------------------------------------------------------------------
# Minimum volume
# --------------------------------------------------------------------------


def test_minimum_volume_refuses_the_shape_of_the_only_real_corpus_found():
    """550 observed 2024 games, one season: the corpus this lane actually found."""
    with pytest.raises(GovernanceBlock) as exc:
        require_minimum_volume(
            distinct_seasons=1,
            total_observations=550,
            holdout_observations=183,
            min_weeks_per_team_per_season=2,
        )
    message = str(exc.value)
    assert "distinct_seasons=1" in message
    assert "total_observations=550" in message
    assert "holdout_observations=183" in message


def test_minimum_volume_accepts_a_conforming_shape():
    result = require_minimum_volume(
        distinct_seasons=3,
        total_observations=1500,
        holdout_observations=300,
        min_weeks_per_team_per_season=8,
    )
    assert result["minimum_volume_satisfied"] is True


# --------------------------------------------------------------------------
# Envelope
# --------------------------------------------------------------------------


def _envelope(tmp_path, rows: int = 1800):
    p = _write_observations(tmp_path / "obs.csv", rows)
    mounted = register_governed_dataset(p, "DS", **GOOD_AUTHORITY)
    return mounted, bind_evidence_envelope(
        mounted,
        identity=_identity(),
        ordered_events=_ordered_events(p),
        experiment_inputs={"regime": "R_TEST", "seed": 1},
        experiment_outputs={PRIMARY_CALIBRATION_METRIC: 11.5},
        distinct_seasons=3,
        min_weeks_per_team_per_season=8,
    )


def test_envelope_binds_all_ten_and_digests_deterministically(tmp_path):
    _, envelope = _envelope(tmp_path)
    assert tuple(envelope.bindings) == REQUIRED_ENVELOPE_BINDINGS
    assert len(REQUIRED_ENVELOPE_BINDINGS) == 10
    assert envelope.digest() == envelope.digest()
    assert len(envelope.digest()) == 64
    assert envelope.temporal_split["assignment"] == "TEMPORAL_ONLY"


def test_envelope_digest_changes_when_any_binding_changes(tmp_path):
    _, envelope = _envelope(tmp_path)
    other = EvidenceEnvelope(
        mounted=envelope.mounted,
        identity=envelope.identity,
        temporal_split=envelope.temporal_split,
        experiment_input_digest=envelope.experiment_input_digest,
        experiment_output_digest="ab" * 32,
        volume=envelope.volume,
    )
    assert other.digest() != envelope.digest()


def test_envelope_refuses_incomplete_identity_reconciliation(tmp_path):
    p = _write_observations(tmp_path / "obs.csv", 1800)
    mounted = register_governed_dataset(p, "DS", **GOOD_AUTHORITY)
    with pytest.raises(GovernanceBlock, match="unresolved"):
        bind_evidence_envelope(
            mounted,
            identity=_identity(names=40, resolved=38, unresolved=("Ole Miss", "Miami")),
            ordered_events=_ordered_events(p),
            experiment_inputs={},
            experiment_outputs={},
            distinct_seasons=3,
            min_weeks_per_team_per_season=8,
        )


def test_envelope_refuses_a_partial_binding_set(tmp_path):
    _, envelope = _envelope(tmp_path)
    with pytest.raises(GovernanceBlock, match="missing required bindings"):
        EvidenceEnvelope(
            mounted=envelope.mounted,
            identity=envelope.identity,
            temporal_split=envelope.temporal_split,
            experiment_input_digest=envelope.experiment_input_digest,
            experiment_output_digest=envelope.experiment_output_digest,
            volume=envelope.volume,
            bindings=tuple(b for b in REQUIRED_ENVELOPE_BINDINGS if b != "temporal_split"),
        )


def test_envelope_refuses_a_non_temporal_split(tmp_path):
    p = _write_observations(tmp_path / "obs.csv", 1800)
    mounted = register_governed_dataset(p, "DS", **GOOD_AUTHORITY)
    events = _ordered_events(p)
    ids = list(events)
    # Move one holdout observation to the front of time: still disjoint, no longer ordered.
    events[ids[-1]] = ("holdout", "2019-01-01T00:00:00+00:00")
    with pytest.raises(GovernanceBlock, match="not temporally ordered"):
        bind_evidence_envelope(
            mounted,
            identity=_identity(),
            ordered_events=events,
            experiment_inputs={},
            experiment_outputs={},
            distinct_seasons=3,
            min_weeks_per_team_per_season=8,
        )


def test_identity_reconciliation_validates_its_own_arithmetic():
    with pytest.raises(InputValidationError, match="more than were offered"):
        IdentityReconciliation(
            authority="A", authority_sha256="0" * 64, source_names=10, resolved=11
        )
    with pytest.raises(InputValidationError, match="pinned by its bytes"):
        IdentityReconciliation(
            authority="A", authority_sha256="short", source_names=1, resolved=1
        )


# --------------------------------------------------------------------------
# Strong promotion binding
# --------------------------------------------------------------------------


def test_byte_verified_binding_reports_evidence_and_promotes_nothing(tmp_path):
    mounted, envelope = _envelope(tmp_path)
    bound = bind_canonical_promotion_evidence(
        _regime(),
        experiment=_experiment(mounted.dataset),
        envelope=envelope,
        evidence={PRIMARY_CALIBRATION_METRIC: 11.5},
    )
    assert bound["evidence_binding"] == EVIDENCE_BOUND_BYTE_VERIFIED
    assert bound["bytes_reverified_at_binding"] is True
    assert bound["envelope_digest"] == envelope.digest()
    assert bound["identity_reconciliation_complete"] is True
    assert bound["writes_canonical_config"] is False
    assert bound["promotion_authorised"] is False
    assert bound["bindings"] == list(REQUIRED_ENVELOPE_BINDINGS)


def test_byte_verified_binding_refuses_when_the_file_changes_after_registration(tmp_path):
    mounted, envelope = _envelope(tmp_path)
    experiment = _experiment(mounted.dataset)
    mounted.dataset.path.write_text("game_id\nG1\n", encoding="utf-8")
    with pytest.raises(GovernanceBlock, match="not the present bytes"):
        bind_canonical_promotion_evidence(
            _regime(), experiment=experiment, envelope=envelope
        )


def test_byte_verified_binding_still_enforces_the_r2_gates(tmp_path):
    mounted, envelope = _envelope(tmp_path)
    training = ExperimentRecord(
        **{**_experiment(mounted.dataset).as_dict(), "split": "training"}
    )
    with pytest.raises(GovernanceBlock, match="holdout"):
        bind_canonical_promotion_evidence(
            _regime(), experiment=training, envelope=envelope
        )

    mismatched = ExperimentRecord(
        **{**_experiment(mounted.dataset).as_dict(), "dataset_sha256": "cc" * 32}
    )
    with pytest.raises(GovernanceBlock, match="not the scored bytes"):
        bind_canonical_promotion_evidence(
            _regime(), experiment=mismatched, envelope=envelope
        )


def test_byte_verified_binding_refuses_a_cited_number_the_run_did_not_measure(tmp_path):
    mounted, envelope = _envelope(tmp_path)
    with pytest.raises(GovernanceBlock, match="but experiment"):
        bind_canonical_promotion_evidence(
            _regime(),
            experiment=_experiment(mounted.dataset, rmse=11.5),
            envelope=envelope,
            evidence={PRIMARY_CALIBRATION_METRIC: 0.0001},
        )
