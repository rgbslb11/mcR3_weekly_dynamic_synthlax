"""Build every R6 observation-corpus artifact from the captured raw bytes.

Deterministic and offline. It reads the raw files acquired by
``acquire_ncaa_scoreboard_r6.py``, re-verifies each one against its registered
digest, and writes the corpus plus the reports that explain it. Running it twice
against unchanged inputs produces identical bytes, which is what makes the
committed artifacts checkable rather than merely present.

Nothing here promotes anything. The last thing it does is call
``calibration.register_dataset`` on the finished corpus and record the refusal,
because the corpus is an observation set and the point is to demonstrate that
the calibration gate still says so.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import blocker_report  # noqa: E402
from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import calibration  # noqa: E402
from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import observation_corpus as oc  # noqa: E402
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.errors import GovernanceBlock  # noqa: E402

#: Read from source rather than restated, so the discovery record cannot drift
#: from what the blocker report actually computes.
BLOCKERS = blocker_report.R3_EXPECTED_LIVE_BLOCKERS_IF_BOARD_MOUNTED

CORPUS_DIR = REPO_ROOT / "reference" / "dynamic_weekly_mc_v3" / "observation_corpus_r6"
AUTHORITY_PATH = (
    REPO_ROOT
    / "reference"
    / "dynamic_weekly_mc_v3"
    / "inputs"
    / "2026_TEAM_CANONICAL_MASTER_v2_LLM_GROUNDING.md"
)
ACQUISITION_MANIFEST = CORPUS_DIR / "V3_R6_SOURCE_ACQUISITION_MANIFEST.json"
CORPUS_CSV = CORPUS_DIR / "V3_R6_OBSERVATION_CORPUS.csv"

HEADER = {
    "authority": "EXPERIMENTAL / NOT CANONICAL / NO PARAMETER PROMOTED / NO BLOCKER RETIRED",
    "contract": "V3-CALIBRATION-DATA-CONTRACT-001",
    "lane": "claude/v3-historical-observation-corpus-r6",
}


def write_json(path: Path, payload: dict) -> str:
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    data = text.encode("utf-8")
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    records = oc.load_acquisition_manifest(ACQUISITION_MANIFEST)
    custody = oc.verify_raw_custody(records, REPO_ROOT)
    authority = oc.load_canonical_identity_authority(AUTHORITY_PATH)
    build = oc.build_observation_corpus(records, authority, REPO_ROOT)

    if not build.reconciles():  # pragma: no cover - guarded by tests too
        raise GovernanceBlock(
            f"Counts do not reconcile: raw={build.raw_row_count} "
            f"admitted={len(build.rows)} excluded={len(build.exclusions)}"
        )

    corpus_bytes = oc.render_corpus_csv(build.rows)
    CORPUS_CSV.write_bytes(corpus_bytes)
    receipt = oc.corpus_registration_receipt(CORPUS_CSV, build.rows, REPO_ROOT)
    split = oc.build_temporal_split(build.rows)
    volume = oc.volume_assessment(build.rows, build.source_report["team_season_coverage"])

    # --- source custody -----------------------------------------------------
    write_json(
        CORPUS_DIR / "V3_R6_SOURCE_CUSTODY_MANIFEST.json",
        {
            **HEADER,
            "artifact": "V3_R6_SOURCE_CUSTODY_MANIFEST.json",
            "artifact_status": "SOURCE_CUSTODY_RECORD",
            "custody_rule": (
                "Each file is bound twice: stored_sha256 over the gzip container "
                "git holds, raw_sha256 over the response body inside it. Both are "
                "recomputed from disk at verification; neither is taken on trust "
                "from this manifest."
            ),
            "verification": custody,
            "sources": [r.as_dict() for r in records],
        },
    )

    # --- identity -----------------------------------------------------------
    write_json(
        CORPUS_DIR / "V3_R6_TEAM_IDENTITY_RECONCILIATION.json",
        {
            **HEADER,
            "artifact": "V3_R6_TEAM_IDENTITY_RECONCILIATION.json",
            "artifact_status": "TEAM_IDENTITY_RECONCILIATION_RECORD",
            "resolution_rules": [
                {
                    "rule": "EXACT_CANONICAL_KEY",
                    "outcome_class": "MATCHED_CANONICAL",
                    "basis": (
                        "The NCAA short name is already a canonical schedule_id, "
                        "team_name, abbreviated_name or aka_name."
                    ),
                },
                {
                    "rule": "NCAA_CHAR6_CANONICAL_KEY",
                    "outcome_class": "HISTORICAL_ALIAS_MATCH",
                    "basis": (
                        "The NCAA six-character team code is a canonical key. This "
                        "is the source's own identifier matching the master's own "
                        "identifier, not an alias authored here."
                    ),
                },
                {
                    "rule": "NCAA_ABBREVIATION_EXPANSION",
                    "outcome_class": "HISTORICAL_ALIAS_MATCH",
                    "basis": (
                        "One of the NCAA house-style abbreviations in "
                        "NCAA_ABBREVIATION_EXPANSIONS is expanded and the result "
                        "must land on an exact canonical key. A wrong expansion "
                        "yields no match rather than a wrong match."
                    ),
                },
                {
                    "rule": "UNRESOLVED_ENTITY",
                    "outcome_class": "HISTORICAL_NON_2026_ENTITY or UNRESOLVED_ENTITY",
                    "basis": (
                        "Not present in the 2026 canonical master under any "
                        "resolution key. Games are excluded with a reason, never "
                        "dropped and never mapped to a similarly named school."
                    ),
                },
            ],
            "abbreviation_expansions": dict(sorted(oc.NCAA_ABBREVIATION_EXPANSIONS.items())),
            "injectivity_rule": (
                "Within a season the resolution must be injective. Two NCAA "
                "entities landing on one canonical schedule_id refuses both, "
                "because no source fact says which is correct."
            ),
            "source_side_qualifiers_preserved": (
                "A parenthetical qualifier on the source name is never stripped. "
                "Miami (FL) and Miami (OH) are two schools, and discarding the "
                "qualifier to force a match is the silent mis-mapping this "
                "resolver exists to prevent. Miami (OH) is consequently "
                "unresolved and its games are excluded."
            ),
            **build.identity_report,
        },
    )

    # --- game identity, chronology -----------------------------------------
    write_json(
        CORPUS_DIR / "V3_R6_GAME_IDENTITY_REPORT.json",
        {
            **HEADER,
            "artifact": "V3_R6_GAME_IDENTITY_REPORT.json",
            "artifact_status": "GAME_IDENTITY_RECORD",
            "supersedes_finding": (
                "R5 recorded game_id T073vT114 colliding on a repeated Oregon "
                "State / Washington State matchup. A team-pair key cannot carry "
                "unique game identity; this scheme keys on the source's own game "
                "identifier instead."
            ),
            **build.game_identity_report,
        },
    )
    write_json(
        CORPUS_DIR / "V3_R6_CHRONOLOGY_REPORT.json",
        {
            **HEADER,
            "artifact": "V3_R6_CHRONOLOGY_REPORT.json",
            "artifact_status": "CHRONOLOGY_AND_WALK_FORWARD_RECORD",
            "supersedes_finding": (
                "R5 recorded zero kickoff instants on the one real stream it "
                "found. Every admitted observation here carries a source-published "
                "start instant."
            ),
            **build.chronology_report,
        },
    )

    # --- exclusions ---------------------------------------------------------
    reason_counts = Counter(e["reason"] for e in build.exclusions)
    write_json(
        CORPUS_DIR / "V3_R6_EXCLUSION_REPORT.json",
        {
            **HEADER,
            "artifact": "V3_R6_EXCLUSION_REPORT.json",
            "artifact_status": "EXCLUSION_AND_RECONCILIATION_RECORD",
            "reconciliation": {
                "raw_row_count": build.raw_row_count,
                "admitted_row_count": len(build.rows),
                "excluded_row_count": len(build.exclusions),
                "reconciles": build.reconciles(),
                "reconciliation_universe": "NCAA_FBS_SCOREBOARD_FEED",
                "rule": (
                    "raw == admitted + excluded over every fbs-feed source file. "
                    "The fbs feed is the reconciliation universe because it is the "
                    "superset of the in-scope scored-game observations: an "
                    "FBS-versus-FCS game is published in both feeds, so no in-scope "
                    "game is reachable only through the fcs feed."
                ),
                "fbs_feed_row_count": build.source_report["raw_row_count"],
                "fbs_feed_files": len(
                    [r for r in records if r.division == "fbs"]
                ),
                "fcs_oracle_row_count": build.source_report["fcs_oracle_row_count"],
                "fcs_oracle_files": build.source_report["fcs_oracle_files"],
                "fcs_oracle_role": build.source_report["fcs_oracle_role"],
                "fcs_oracle_rule": (
                    "The fcs feed is read only to decide observed division — a game "
                    "appearing in both feeds crosses divisions — and its rows are "
                    "deliberately NOT terms in the equation above. They are not "
                    "admitted, not excluded, and not counted as raw: an FCS-versus-FCS "
                    "game is outside the governed scope of this corpus rather than a "
                    "row it dropped."
                ),
            },
            "reason_codes": list(oc.EXCLUSION_REASONS),
            "reason_counts": dict(sorted(reason_counts.items())),
            "fbs_vs_fcs_inventory_count": len(build.fcs_inventory),
            "fbs_vs_fcs_inventory": [
                {
                    "season": r["season"],
                    "week": r["week"],
                    "source_game_id": r["source_game_id"],
                    "event_time": r["epoch"],
                    "fbs_side": r["team"] if r["home_division"] == "FBS" else r["opponent"],
                    "fcs_side": r["opponent"] if r["home_division"] == "FBS" else r["team"],
                    "margin_home_perspective": r["margin"],
                    "source_home": r["source_home"],
                    "source_away": r["source_away"],
                }
                for r in build.fcs_inventory
            ],
            "excluded_rows": list(build.exclusions),
        },
    )

    # --- split, registration, evidence -------------------------------------
    write_json(
        CORPUS_DIR / "V3_R6_TEMPORAL_SPLIT_MANIFEST.json",
        {
            **HEADER,
            "artifact": "V3_R6_TEMPORAL_SPLIT_MANIFEST.json",
            "artifact_status": "TEMPORAL_SPLIT_RECORD",
            "minimum_volume": volume,
            **split,
        },
    )
    write_json(
        CORPUS_DIR / "V3_R6_CORPUS_REGISTRATION_RECEIPT.json",
        {
            **HEADER,
            "artifact": "V3_R6_CORPUS_REGISTRATION_RECEIPT.json",
            "artifact_status": "CORPUS_REGISTRATION_RECEIPT",
            "field_classification": {
                k: dict(v) for k, v in sorted(oc.FIELD_CLASSIFICATION.items())
            },
            "team_season_coverage": build.source_report["team_season_coverage"],
            "source_report": build.source_report,
            **receipt,
        },
    )

    # The corpus is an observation set, not a calibration dataset. Prove the
    # calibration gate still refuses it rather than asserting that it would.
    try:
        calibration.register_dataset(CORPUS_CSV, oc.CORPUS_ID)
        calibration_refusal = None
    except GovernanceBlock as exc:
        calibration_refusal = str(exc)
    if calibration_refusal is None:  # pragma: no cover - would be a governance failure
        raise GovernanceBlock(
            "calibration.register_dataset accepted the observation corpus. It "
            "must not: the corpus carries no model-output fields and is not a "
            "calibration dataset."
        )

    write_json(
        CORPUS_DIR / "V3_R6_EVIDENCE_BINDING_RECEIPT.json",
        {
            **HEADER,
            "artifact": "V3_R6_EVIDENCE_BINDING_RECEIPT.json",
            "artifact_status": "OBSERVATION_CORPUS_EVIDENCE_BINDING_RECEIPT",
            "evidence_status": "OBSERVATION_CORPUS_BOUND_BYTES_REVERIFIED",
            "bytes_reverified_at_binding": True,
            "bindings": {
                "raw_source_bytes": custody["bytes_reverified"],
                "raw_source_sha256": True,
                "source_authority": custody["source_authority_classes"],
                "retrieval_record": True,
                "canonical_identity_authority_sha256": authority.sha256,
                "team_identity_reconciliation": {
                    "complete_over_admitted_rows": True,
                    "unresolved_entity_count": build.identity_report[
                        "unresolved_entity_count"
                    ],
                    "unresolved_disposition": (
                        "excluded with UNRESOLVED_TEAM_IDENTITY and listed by name; "
                        "never dropped and never mapped by similarity"
                    ),
                },
                "game_identity_unique": build.game_identity_report[
                    "duplicate_game_id_count"
                ]
                == 0,
                "chronology": build.chronology_report["scheme"],
                "temporal_split": split["leak_free"],
                "minimum_volume": volume["minimum_volume_satisfied"],
                "corpus_sha256": receipt["sha256"],
            },
            "calibration_evidence_status": "NOT_REACHED",
            "calibration_evidence_status_reason": (
                "EVIDENCE_BOUND_BYTES_REVERIFIED_AT_BINDING requires a registered "
                "CalibrationDataset. This corpus cannot be one. The code gate, "
                "calibration.register_dataset, refuses it for the two columns "
                "named in calibration_register_dataset_refusal; the data "
                "contract's own required_fields list is wider still and adds the "
                "fields in contract_required_fields_absent. Every one of those is "
                "either a model output no observation source can supply or, in "
                "the case of venue, a fact this source does not publish."
            ),
            "calibration_register_dataset_refusal": calibration_refusal,
            "code_gate_required_columns_absent": sorted(
                c
                for c in calibration.REQUIRED_OBSERVATION_COLUMNS
                if c not in oc.CORPUS_COLUMNS
            ),
            "contract_required_fields_absent": sorted(
                name
                for name, entry in oc.FIELD_CLASSIFICATION.items()
                if entry["class"].startswith("BLOCKED")
                or entry["class"] == "DERIVED_AVAILABLE_NOT_EMITTED"
            ),
            "promotion_authorised": False,
            "writes_canonical_config": False,
            "canonical_writer_created": False,
            "parameters_promoted": [],
            "blockers_retired": [],
            "allowlist_widened": False,
            "experiments_run": 0,
        },
    )

    # --- R6 discovery / status ---------------------------------------------
    reason_counts = Counter(e["reason"] for e in build.exclusions)
    fcs_sides = sorted(
        {
            entry["opponent"] if entry["home_division"] == "FBS" else entry["team"]
            for entry in build.fcs_inventory
        }
    )
    write_json(
        CORPUS_DIR / "V3_R6_OBSERVATION_CORPUS_DISCOVERY_R6.json",
        {
            **HEADER,
            "artifact": "V3_R6_OBSERVATION_CORPUS_DISCOVERY_R6.json",
            "artifact_status": "OBSERVATION_CORPUS_DISCOVERY_RECORD",
            "supersedes": "V3_CALIBRATION_EVIDENCE_DISCOVERY_R5.json (successor, not replacement)",
            "terminal": "HISTORICAL_OBSERVATION_CORPUS_R6_READY_FOR_AUDIT",
            "source_acquisition": {
                "status": "ACQUIRED",
                "source_authority": "NCAA_OFFICIAL_SCOREBOARD_FEED",
                "source_authority_class": "GOVERNED_RESULT_SOURCE",
                "source_authority_tier": "TIER_1_NCAA_OFFICIAL",
                "base_url": "https://data.ncaa.com/casablanca/scoreboard/football",
                "files_captured": len(records),
                "raw_bytes": custody["raw_bytes_verified"],
                "seasons_retrieved": custody["seasons"],
                "seasons_admitted": list(oc.ADMITTED_SEASONS),
                "seasons_refused": build.source_report["seasons_not_admitted"],
                "seasons_refused_source_content_fact": build.source_report[
                    "seasons_not_admitted_state_census"
                ],
                "seasons_refused_source_content_rule": build.source_report[
                    "seasons_not_admitted_census_rule"
                ],
                "seasons_refused_evidence": (
                    "SOURCE CONTENT FACT. The captured 2025 week files are a "
                    "mid-season snapshot, not an empty one. Their gameState census "
                    "is published verbatim in seasons_refused_source_content_fact "
                    "and is counted from the bytes: the season stands mostly "
                    "unplayed, a minority of rows already read final and a few "
                    "still read live. EVIDENCE ADMISSION DECISION. That mix is why "
                    "the season is refused, not an obstacle to refusing it. "
                    "Admission is by whole finalised season: a season whose own "
                    "bytes show it still in progress cannot supply a "
                    "season-complete observation set, and admitting only the rows "
                    "that happen to read final would make the corpus a function of "
                    "when the snapshot was taken. Every 2025 row is therefore "
                    "refused under SOURCE_SEASON_NOT_FINALISED, the final and live "
                    "rows included. The bytes are retained as the evidence for "
                    "both the fact and the decision."
                ),
                "postseason_coverage": (
                    "None. The feed carries no bowl or College Football Playoff "
                    "games in any retrieved season."
                ),
            },
            "reconciliation": {
                "raw_row_count": build.raw_row_count,
                "admitted_row_count": len(build.rows),
                "excluded_row_count": len(build.exclusions),
                "reconciles": build.reconciles(),
                "reason_counts": dict(sorted(reason_counts.items())),
            },
            "division_inventory": {
                "method": (
                    "A game appears in both the fbs and fcs scoreboards exactly "
                    "when it crosses divisions. Team division follows from "
                    "appearing in an FBS-only game; nothing is inferred from a "
                    "conference name."
                ),
                "FBS_FBS_admitted": len(build.rows),
                "FBS_FCS_identified": len(build.fcs_inventory),
                "FBS_FCS_admitted": 0,
                "unresolved_division": 0,
                "fcs_participants_identified": fcs_sides,
                "fcs_disposition": (
                    "Excluded under FBS_VS_FCS_OPPONENT_DIVISION_NOT_GOVERNED and "
                    "inventoried in full. opponent_division is not on the governed "
                    "allowlist and the FCS point-scale adapter is an open blocker."
                ),
            },
            "supersedes_r5_findings": {
                "no_admissible_corpus_mounted": (
                    "ADDRESSED. A real, byte-bound corpus of "
                    f"{len(build.rows)} observations across "
                    f"{len(oc.ADMITTED_SEASONS)} seasons now exists."
                ),
                "zero_admissible_fbs_vs_fcs_observations": (
                    f"ADDRESSED IN PART. {len(build.fcs_inventory)} real "
                    "FBS-versus-FCS observations are now identified and "
                    "inventoried. They remain excluded from the corpus and no "
                    "FCS mapping is derived."
                ),
                "team_pair_game_id_collision_T073vT114": (
                    "RESOLVED. Identity keys on the NCAA's own game identifier "
                    "namespaced by season; "
                    f"{build.game_identity_report['repeat_matchup_count']} repeat "
                    "matchups are carried with distinct identifiers."
                ),
                "zero_kickoff_instants": (
                    "RESOLVED. Every admitted observation carries a "
                    "source-published start instant."
                ),
                "2006_2011_material_refused_as_synthetic": (
                    "NOT RE-ADMITTED. No 2006-2011 material is used."
                ),
                "real_2024_margin_sd_19_764": (
                    "NOT USED. No dispersion statistic is computed here and none "
                    "is offered toward game_sd_points."
                ),
                "local_synthetic_games_refused": (
                    "STILL REFUSED. The synthetic-content gate is unchanged and "
                    "no synthetic outcome enters this corpus."
                ),
            },
            "governance": {
                "blockers_before": sorted(BLOCKERS),
                "blockers_after": sorted(BLOCKERS),
                "blocker_count_before": len(BLOCKERS),
                "blocker_count_after": len(BLOCKERS),
                "blockers_opened": [],
                "blockers_retired": [],
                "parameters_promoted": [],
                "fcs_mapping_promoted": False,
                "fcs_elo": 1250,
                "allowlist_widened": False,
                "canonical_config_written": False,
                "experiments_run": 0,
                "season_monte_carlo_run": False,
            },
            "remaining_blocked": {
                "corpus_construction": [
                    "venue (HOME|AWAY|NEUTRAL): the source publishes no "
                    "neutral-site indicator, so actual_margin is signed from the "
                    "designated home team's perspective and neutral sites are "
                    "indistinguishable from home games.",
                    "observed_at: no per-row zoned observability instant exists.",
                    "game_type: the feed carries no postseason games and no "
                    "competition-type field, so regular-season and conference "
                    "championship games are present and indistinguishable.",
                    "Game completion instants: only start instants are published, "
                    "so a strict result-availability ordering within a day cannot "
                    "be proved.",
                ],
                "downstream_calibration": [
                    "pregame_team_rating, pregame_opponent_rating, expected_margin, "
                    "prior_rating_state, model_version, configuration_version: "
                    "model outputs no observation source can supply.",
                    "The rating-to-margin transform (P_TO_STRENGTH_TRANSFORM) and "
                    "REFERENCE_HFA remain unratified, so expected_margin cannot be "
                    "constructed in V3 units even against a perfect corpus.",
                    "Rulings on games_played_to_date, game_type, overtime_periods "
                    "and opponent_division are still outstanding.",
                    "All eight formal blockers remain open.",
                ],
            },
            "provenance_class": {
                "FACT": (
                    "Byte-level properties of files retrieved in this lane and "
                    "the field values inside them: digests, byte lengths, row "
                    "counts, scores, participants, start instants and NCAA game "
                    "identifiers."
                ),
                "DERIVED": (
                    "Counts and classifications computed from those bytes: "
                    "margins, results, game identifiers, division determination, "
                    "canonical identity resolution and the temporal split."
                ),
                "ASSUMPTION": (
                    "None. Where a fact was unavailable — neutral-site status, "
                    "observability instants, competition type — the field is "
                    "classified BLOCKED and omitted rather than filled."
                ),
            },
        },
    )

    print(f"corpus rows       : {len(build.rows)}")
    print(f"corpus sha256     : {receipt['sha256']}")
    print(f"raw / adm / excl  : {build.raw_row_count} / {len(build.rows)} / {len(build.exclusions)}")
    print(f"split             : {split['splits']}")
    print(f"split digest      : {split['split_digest']}")
    print(f"fbs-vs-fcs        : {len(build.fcs_inventory)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
