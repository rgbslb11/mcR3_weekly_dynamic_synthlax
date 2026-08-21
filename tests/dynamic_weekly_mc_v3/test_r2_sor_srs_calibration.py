"""R2 convergence: SOR report, SRS witness, and calibration governance."""

import pytest

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import calibration as cal
from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import sor, srs
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.errors import (
    GovernanceBlock,
    InputValidationError,
)

REF = sor.SorReferenceElo(
    value=1725.0,
    parameter_id="TEST-SOR-R-REF-2026",
    authority="TEST_FIXTURE season parameter",
    source_artifact="test fixture",
)
OPPONENTS = [
    sor.SorOpponent("X", 1600.0, True),
    sor.SorOpponent("Y", 1500.0, True),
    sor.SorOpponent("Z", 1700.0, False),
]


def _row(**overrides):
    kwargs = dict(
        week=10, as_of="2026-11-07T00:00:00Z", team="ARK", opponents=OPPONENTS,
        reference=REF, source_hashes={"schedule": "bd8089f7"},
        model="SYTHALAX_DYNAMIC_WEEKLY_MC_V3_EXPERIMENTAL",
        model_version="3.0.0-experimental-harness",
        configuration_version="V3-PLACEHOLDER-2026-08-21-R2-001",
        observed_at="2026-11-07T00:00:00Z", recorded_at="2026-11-07T01:00:00Z",
    )
    kwargs.update(overrides)
    return sor.weekly_sor_row(**kwargs)


# --- weekly SOR output -------------------------------------------------------


def test_weekly_sor_output_carries_every_required_field():
    payload = _row().as_dict()
    for field in (
        "week", "as_of", "team", "wins", "losses", "opponents_counted", "p_ref_ge_w",
        "raw_sor", "normalized_sor", "r_ref", "source_hashes", "model", "model_version",
        "configuration_version", "observed_at", "recorded_at", "provenance",
    ):
        assert field in payload, field
    assert payload["wins"] == 2 and payload["losses"] == 1
    assert payload["opponents_counted"] == 3
    assert 0.0 < payload["p_ref_ge_w"] < 1.0


def test_weekly_sor_is_report_only_and_never_committee_input():
    payload = _row().as_dict()
    assert payload["report_status"] == "RESEARCH_REPORT_ONLY"
    assert payload["is_committee_input"] is False
    assert payload["provenance"]["not_committee_sos"] is True
    assert payload["provenance"]["not_srs"] is True
    assert payload["provenance"]["not_baxter_rating"] is True
    assert payload["provenance"]["not_colley"] is True


def test_unresolved_assumptions_are_stamped_rather_than_hidden():
    payload = _row(unresolved_assumptions=["caller-supplied caveat"]).as_dict()
    assumptions = payload["provenance"]["unresolved_assumptions"]
    assert "caller-supplied caveat" in assumptions
    # The module stamps its own caveats too, so a silent convention cannot pass
    # itself off as governed methodology.
    assert any("compute_sor_b.py is not mounted" in a for a in assumptions)
    assert any("report convention" in a for a in assumptions)
    assert "REPORT CONVENTION" in payload["provenance"]["raw_sor_transform"]
    assert "REPORT CONVENTION" in payload["provenance"]["normalized_sor_transform"]


def test_the_stale_compute_sor_b_default_cannot_silently_execute():
    assert sor.STALE_COMPUTE_SOR_B_DEFAULT_R_REF == 1684.9
    with pytest.raises(GovernanceBlock, match="stale"):
        sor.SorReferenceElo(
            value=1684.9, parameter_id="X", authority="Y", source_artifact="Z"
        )
    with pytest.raises(GovernanceBlock, match="explicit governed season R_ref"):
        sor.require_sor_reference_elo(None)
    with pytest.raises(GovernanceBlock):
        _row(reference=None)


def test_the_mc_domain_r_ref_stays_in_its_own_namespace():
    mc = sor.mc_domain_reference_elo()
    assert mc.value == 1893.3
    assert mc.parameter_id == "CCG-R_REF"
    assert mc.namespace == sor.MC_NAMESPACE != sor.SOR_REPORT_NAMESPACE
    with pytest.raises(GovernanceBlock, match="keep domains separate"):
        sor.reject_mc_r_ref_overwrite(sor.MC_NAMESPACE, REF)
    # Passing the MC value in explicitly is allowed and recorded as such.
    row = _row(reference=mc).as_dict()
    assert row["r_ref"] == 1893.3
    assert row["r_ref_namespace"] == sor.MC_NAMESPACE


def test_sor_may_not_be_used_as_committee_sos():
    for name in ("SOS", "committee_sos", "strength_of_schedule"):
        with pytest.raises(GovernanceBlock, match="resume output"):
            sor.reject_sor_as_committee_sos(name)


def test_poisson_binomial_is_monotone_in_the_win_threshold():
    values = [sor.p_reference_at_least_w(1725.0, OPPONENTS, w) for w in range(4)]
    assert values == sorted(values, reverse=True)
    assert values[0] == pytest.approx(1.0, abs=1e-12)
    with pytest.raises(InputValidationError):
        sor.p_reference_at_least_w(1725.0, OPPONENTS, 4)


# --- SRS ---------------------------------------------------------------------


def _srs_games():
    return [
        srs.SrsGame("g1", "A", "B", 30.0), srs.SrsGame("g1", "B", "A", -30.0),
        srs.SrsGame("g2", "A", "C", 7.0), srs.SrsGame("g2", "C", "A", -7.0),
    ]


def test_srs_is_opponent_adjusted_capped_and_centred():
    ratings = srs.compute_srs(_srs_games())
    assert ratings["A"] == pytest.approx(31 / 3, abs=1e-9)
    assert ratings["B"] == pytest.approx(31 / 3 - 24, abs=1e-9)
    assert ratings["C"] == pytest.approx(31 / 3 - 7, abs=1e-9)
    assert sum(ratings.values()) == pytest.approx(0.0, abs=1e-9)
    assert srs.srs_ordering(ratings) == ["A", "C", "B"]


def test_the_margin_cap_of_plus_minus_24_binds():
    assert srs.SRS_MARGIN_CAP == 24.0
    assert srs.cap_margin(100.0) == 24.0
    assert srs.cap_margin(-100.0) == -24.0
    blown_out = [
        srs.SrsGame("g1", "A", "B", 100.0), srs.SrsGame("g1", "B", "A", -100.0),
        srs.SrsGame("g2", "A", "C", 7.0), srs.SrsGame("g2", "C", "A", -7.0),
    ]
    assert srs.compute_srs(blown_out) == srs.compute_srs(_srs_games())


def test_srs_is_deterministic_regardless_of_input_order():
    games = _srs_games()
    assert srs.compute_srs(list(reversed(games))) == srs.compute_srs(games)


def test_srs_is_neither_committee_sos_nor_sor():
    witness = srs.witness_as_dict(srs.compute_srs(_srs_games()))
    assert witness["is_committee_sos"] is False
    assert witness["is_sor"] is False
    assert witness["role"] == "CALIBRATION_VALIDATION_WITNESS"
    for name in ("SOS", "committee_sos", "SOR", "sor_b", "record_strength"):
        with pytest.raises(GovernanceBlock, match="separate"):
            srs.reject_srs_as(name)


def test_no_weighted_composite_of_the_witnesses_is_authorised():
    with pytest.raises(GovernanceBlock, match="NOT ADOPTED"):
        srs.reject_witness_composite(["SRS", "SOR_B"])
    with pytest.raises(GovernanceBlock, match="not authorised"):
        cal.reject_witness_composite(["baxter_rating", "colley_matrix", "srs"])
    # A single witness reported on its own is fine.
    cal.reject_witness_composite(["colley_matrix"])


# --- calibration governance --------------------------------------------------


def test_baxter_rmse_is_the_primary_objective_out_of_sample():
    assert cal.PRIMARY_CALIBRATION_METRIC == "out_of_sample_baxter_rating_rmse"
    assert cal.PRIMARY_CALIBRATION_DIRECTION == "minimize"
    assert cal.require_primary_objective(cal.PRIMARY_OBJECTIVE) is cal.PRIMARY_OBJECTIVE
    with pytest.raises(GovernanceBlock, match="primary calibration criterion"):
        cal.require_primary_objective(
            cal.EvaluationObjective("X", "brier_score", "minimize", "not primary")
        )
    with pytest.raises(GovernanceBlock, match="names"):
        cal.require_primary_objective(None)


def test_colley_and_srs_remain_independent_witnesses():
    governance = cal.calibration_governance_as_dict()
    assert governance["independent_witnesses"] == ["colley_matrix", "srs"]
    assert governance["weighted_composite_authorised"] is False
    assert cal.PRIMARY_CALIBRATION_METRIC not in governance["independent_witnesses"]


def test_training_validation_and_holdout_stay_separated():
    buckets = cal.require_split_separation(
        {"G1": "training", "G2": "validation", "G3": "holdout"}
    )
    assert buckets == {"training": ["G1"], "validation": ["G2"], "holdout": ["G3"]}
    with pytest.raises(InputValidationError, match="expected one of"):
        cal.require_split_separation({"G1": "test"})


def test_canonical_coefficient_fields_remain_null_until_promoted():
    status = cal.calibration_status({name: None for name in cal.CALIBRATION_FIELDS})
    assert status["all_canonical_values_null"] is True
    assert status["legacy_margin_sd_approved"] is False
    assert cal.calibration_governance_as_dict()["automatic_promotion"] is False


def test_promotion_requires_a_named_authority_and_a_human_token():
    regime = cal.CandidateRegime("R1", {"game_sd_points": 17.0}, "probe")
    with pytest.raises(GovernanceBlock, match="no promotion authority"):
        cal.promote_regime_r2(regime)
    with pytest.raises(GovernanceBlock, match="not an authority"):
        cal.promote_regime_r2(regime, ranked_first=True)
    with pytest.raises(GovernanceBlock, match="Unknown promotion authority"):
        cal.promote_regime_r2(regime, authority="BECAUSE_IT_WON")
    with pytest.raises(GovernanceBlock, match="requires governed"):
        cal.promote_regime_r2(regime, authority=cal.PROMOTION_AUTHORITY_MATHEMATICAL)
    with pytest.raises(GovernanceBlock, match="holdout split"):
        cal.promote_regime_r2(
            regime, authority=cal.PROMOTION_AUTHORITY_MATHEMATICAL,
            evidence={cal.PRIMARY_CALIBRATION_METRIC: 3.1, "split": "training"},
        )
    with pytest.raises(GovernanceBlock, match="written justification"):
        cal.promote_regime_r2(regime, authority=cal.PROMOTION_AUTHORITY_CHAIRMAN)
    # Authority plus evidence still needs the human token.
    with pytest.raises(GovernanceBlock, match="no human approval token"):
        cal.promote_regime_r2(
            regime, authority=cal.PROMOTION_AUTHORITY_MATHEMATICAL,
            evidence={cal.PRIMARY_CALIBRATION_METRIC: 3.1, "split": "holdout"},
        )


def test_an_authorised_promotion_records_which_authority_was_used():
    regime = cal.CandidateRegime("R1", {"game_sd_points": 17.0}, "probe")
    record = cal.promote_regime_r2(
        regime,
        authority=cal.PROMOTION_AUTHORITY_MATHEMATICAL,
        approval_token="APPROVE_V3_CALIBRATION_PROMOTION::RAT-999",
        evidence={cal.PRIMARY_CALIBRATION_METRIC: 3.1, "split": "holdout"},
    )
    assert record["promotion_authority"] == cal.PROMOTION_AUTHORITY_MATHEMATICAL
    assert record["writes_canonical_config"] is False


# --- dataset registration hardening (audit finding B-4) ----------------------

HEADER = "game_id,season,week,team,opponent,expected_margin,actual_margin,observed_at,recorded_at"
ROW = "G1,2026,1,ARK,GAST,3.5,7,2026-08-29T00:00:00Z,2026-08-30T00:00:00Z\n"


def test_a_missing_dataset_still_returns_blocked_on_calibration_data(tmp_path):
    with pytest.raises(GovernanceBlock, match=cal.BLOCKED_ON_CALIBRATION_DATA):
        cal.register_dataset(tmp_path / "absent.csv", "DS")


def test_csv_tsv_and_json_are_parsed_format_aware(tmp_path):
    csv_path = tmp_path / "a.csv"
    csv_path.write_text(f"{HEADER}\n{ROW}", encoding="utf-8")
    assert cal.register_dataset(csv_path, "DS").rows == 1

    tsv_path = tmp_path / "a.tsv"
    tsv_path.write_text(
        HEADER.replace(",", "\t") + "\n" + ROW.replace(",", "\t"), encoding="utf-8"
    )
    registered = cal.register_dataset(tsv_path, "DS")
    assert registered.rows == 1
    assert "game_id" in registered.columns

    json_path = tmp_path / "a.json"
    json_path.write_text(
        '{"observations": [{"game_id": "G1", "season": 2026, "week": 1, "team": "ARK",'
        ' "opponent": "GAST", "expected_margin": 3.5, "actual_margin": 7,'
        ' "observed_at": "t", "recorded_at": "t"}]}',
        encoding="utf-8",
    )
    assert cal.register_dataset(json_path, "DS").rows == 1


def test_an_unknown_format_is_refused_rather_than_guessed(tmp_path):
    path = tmp_path / "a.parquet"
    path.write_text("anything", encoding="utf-8")
    with pytest.raises(GovernanceBlock, match="unsupported format"):
        cal.register_dataset(path, "DS")


def test_invalid_encoding_is_refused(tmp_path):
    path = tmp_path / "a.csv"
    path.write_bytes(b"\xff\xfe\x00game_id")
    with pytest.raises(GovernanceBlock, match="not valid UTF-8"):
        cal.register_dataset(path, "DS")


def test_malformed_json_is_refused(tmp_path):
    path = tmp_path / "a.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(GovernanceBlock, match="does not parse"):
        cal.register_dataset(path, "DS")


@pytest.mark.parametrize(
    "alias",
    [
        "public_money_pct",
        "public_money_percentage",
        "PublicMoney",
        "bet_pct",
        "bet_percentage",
        "handle_percent",
        "ticket_pct",
        "sharp_money",
        "wager_share",
        "injury_adjustment",
    ],
)
def test_public_money_and_injury_aliases_are_rejected(tmp_path, alias):
    path = tmp_path / "a.csv"
    path.write_text(f"{HEADER},{alias}\n{ROW.strip()},1\n", encoding="utf-8")
    with pytest.raises(GovernanceBlock, match="non-admissible predictive signals"):
        cal.register_dataset(path, "DS")


def test_a_tsv_cannot_smuggle_a_forbidden_signal_past_a_csv_parser(tmp_path):
    """The pre-hardening parser read a whole TSV header as one column name."""
    path = tmp_path / "a.tsv"
    path.write_text(
        HEADER.replace(",", "\t") + "\tpublic_money_pct\n" + ROW.replace(",", "\t").strip() + "\t62\n",
        encoding="utf-8",
    )
    with pytest.raises(GovernanceBlock, match="non-admissible predictive signals"):
        cal.register_dataset(path, "DS")


def test_columns_outside_the_governed_allowlist_are_refused(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text(f"{HEADER},vibes\n{ROW.strip()},9\n", encoding="utf-8")
    with pytest.raises(GovernanceBlock, match="outside the governed"):
        cal.register_dataset(path, "DS")


def test_a_dataset_missing_required_observation_columns_is_refused(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text("game_id,season\nG1,2026\n", encoding="utf-8")
    with pytest.raises(GovernanceBlock, match=cal.BLOCKED_ON_CALIBRATION_DATA):
        cal.register_dataset(path, "DS")


def test_no_real_calibration_dataset_is_mounted():
    assert cal.calibration_governance_as_dict()["dataset_mounted"] is False
    assert cal.calibration_governance_as_dict()["disposition"] == cal.BLOCKED_ON_CALIBRATION_DATA
