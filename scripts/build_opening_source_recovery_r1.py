"""Emit the V3 opening source-recovery artifacts (lane R1).

The lane answers one question: can the component families that produce the V3
opening Unified Master Z be sourced for preseason 2021-2024?

Every statement below was established by reading a source artifact, not by
reading a prose label. Where a number is asserted it was recomputed; where a
formula is asserted it was solved or reproduced against the workbook that
publishes it. Several recomputation inputs live outside the repository -- the
board workbooks, the TrueSkill consolidation, the Baxter package -- so this
emitter carries the *findings* and their evidence, and the artifacts it writes
are the lane's deliverable.

No V3 point value is produced. No parameter is fitted. No population is ruled on.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ARTIFACT_VERSION = "V3-OPENING-SOURCE-RECOVERY-R1"
SEASONS = (2021, 2022, 2023, 2024)

OUT_DIR = (
    Path(__file__).resolve().parents[1]
    / "reference"
    / "dynamic_weekly_mc_v3"
    / "opening_source_recovery_r1"
)

# --------------------------------------------------------------------------
# Section 1 -- the exact opening families, read from the construction workbook
# --------------------------------------------------------------------------

FAMILY_INVENTORY = {
    "artifact": "V3_OPENING_FAMILY_INVENTORY_R1",
    "artifact_version": ARTIFACT_VERSION,
    "construction_source": {
        "ensemble_parameters_sheet": "Ensemble Parameters",
        "master_sheet": "Master Ratings",
        "path": (
            "reference/dynamic_weekly_mc_v3/inputs/"
            "2026_CFB_2026_Preseason_Unified_Power_Ratings.xlsx"
        ),
        "sha256": "4b2535459ec069b8dc16edb64a90df694562746035279f961aa8f73530807a4a",
    },
    "family_count_rule": {
        "included_family_count_column": "BZ",
        "renormalization_rule_exists": False,
        "statement": (
            "The workbook stores Included Family Count as the literal 4 on every "
            "row and its Validation sheet asserts MIN(BZ5:BZ125) = 4. Neither the "
            "workbook nor V3 source carries a rule for combining fewer than four "
            "families; combine_unified_z on the sibling historical-opening-state "
            "branch refuses a subset rather than renormalizing. No missing-family "
            "rule is invented here."
        ),
        "value": 4,
    },
    "families": [
        {
            "family_id": "TRUESKILL",
            "family_name": "TrueSkill",
            "externally_sourced": False,
            "generator": {
                "algorithm": (
                    "Classic two-team TrueSkill, winner/loser only. mu0=25, "
                    "sigma0=25/3=8.333333, beta=25/6=4.166667, tau=25/300=0.083333, "
                    "draw probability 0, equal game weight, no margin, no home field. "
                    "Parameter set TS-V0-2025-001; replayed in published game_seq order."
                ),
                "fully_specified": True,
                "preseason_transition": (
                    "mu_2026 = 25 + 0.70 * (mu_2025 - 25); "
                    "sigma_2026 = sqrt(sigma_2025^2 + 3.0^2). "
                    "Parameter set P0-LAMBDA070-OMEGA300-v1."
                ),
                "required_input": (
                    "complete prior-season game ledger (winner/loser per game)"
                ),
                "source_of_specification": (
                    "Operation_Sythalax_TrueSkill_2025_2026_Thread_Consolidation.xlsx, "
                    "sheets '01 Method Register' (M-001..M-009), '10 2025 README', "
                    "'21 2026 P0 Params', '24 2026 README'"
                ),
            },
            "master_column": "F",
            "native_field": "TrueSkill 2026 Preseason mu",
            "preseason_effective_date": (
                "2026 preseason; P0 transition applied to the 2025 posterior"
            ),
            "reproducible_algorithmically": True,
            "standardized_column": "BM",
            "supplying_artifact_2026": (
                "Operation_Sythalax_TrueSkill_2025_2026_Thread_Consolidation.xlsx"
            ),
            "supplying_artifact_sha256": (
                "4b7d84d8a4b626c7f207162cb8748268d4d3f2608e41cba376a4272c6c7dfc79"
            ),
            "upstream_evidence_class": "SYNTHETIC_2025_SEASON_LEDGER",
            "weight": 0.25,
        },
        {
            "family_id": "LITKENHOUS",
            "family_name": "Litkenhous",
            "externally_sourced": False,
            "generator": {
                "algorithm": (
                    "Two layers. Layer 1 (pure carryover) = 0.60 * prior-season "
                    "Litkenhous power margin, field recentered. The prior-season rating "
                    "is itself SYTHLAX-LIT-V0: minimise sum_g [35*tanh(m_g/35) - "
                    "(r_i - r_j + H*home_g)]^2 subject to sum_i r_i = 0, one jointly "
                    "estimated home-field coefficient, equal game weights, no preseason "
                    "priors. Layer 2 (the V3 input) adds "
                    "clip[16 * (offseason_composite - 0.5), +/-8] and recenters to 100."
                ),
                "fully_specified": False,
                "layer_2_dependency": (
                    "The offseason composite is the Board I-H component vector under the "
                    "Board I-H sub-weights: returning 0.216216, movement 0.162162, "
                    "talent 0.108108, coaching 0.081081, renormalized over their total "
                    "0.567567, with talent excluded for the academies. Recomputing the "
                    "composite from the Board I-H v2 sheet reproduces the workbook's "
                    "Litkenhous Offseason Composite column to 6.7e-16 and the "
                    "Offseason Adjustment column to 1.2e-14. Layer 2 is therefore not "
                    "independent of the Board family."
                ),
                "required_input": (
                    "complete prior-season game ledger with scores and a neutral-site "
                    "indicator, plus the Board I-H component vector"
                ),
                "source_of_specification": (
                    "2026_Synthetic_FBS_Litkenhous_Preseason_Three_Layer.xlsx sheet "
                    "'Methodology'; "
                    "2025_Synthetic_CFB_Litkenhous_Inspired_Final_Ratings.xlsx "
                    "sheet 'Methodology' (model SYTHLAX-LIT-V0-2025-FINAL)"
                ),
            },
            "historical_name_disclaimer": (
                "The historical Litkenhous Difference by Score system was an NCAA major "
                "selector for 1934-1984. The ingested source record SRC-LIT-001 carries "
                "its algorithm, coefficients, score transformation and schedule "
                "adjustment as BLOCKED, sets direct_production_weight to 0.0, and "
                "prohibits exact reconstruction. The programme's own model card states "
                "'Litkenhous-inspired reconstruction; not an exact reproduction of the "
                "proprietary historical formula'. The V3 family is a contemporary "
                "implementation carrying a historical name."
            ),
            "master_column": "L",
            "native_field": "Litkenhous Adjusted Power",
            "preseason_effective_date": (
                "2026 preseason; carryover from the 2025 final rating"
            ),
            "reproducible_algorithmically": False,
            "standardized_column": "BN",
            "supplying_artifact_2026": (
                "2026_Synthetic_FBS_Litkenhous_Preseason_Three_Layer.xlsx"
            ),
            "supplying_artifact_sha256": (
                "5ad5125a306601eeca67a3750c7fa8e556a5c8bdb8680f5031b6818e86ff37db"
            ),
            "upstream_evidence_class": (
                "SYNTHETIC_2025_SEASON_LEDGER_PLUS_CHAIRMAN_BOARD"
            ),
            "variance_decomposition_of_adjusted_power": {
                "board_adjustment_variance_share": 0.023,
                "carryover_variance_share": 0.8133,
                "covariance_share": 0.1637,
                "note": (
                    "Recomputed over the 121 published rows. The Board-derived layer "
                    "supplies a minority of the dispersion but is a hard prerequisite: "
                    "without it the published Adjusted Power cannot be formed at all."
                ),
            },
            "weight": 0.25,
        },
        {
            "family_id": "PURE_BAXTER",
            "family_name": "Pure Baxter",
            "externally_sourced": False,
            "generator": {
                "algorithm": (
                    "Doctrine BAXTER-MOV-v1.0-R. Opponent-adjusted margin ridge: "
                    "predicted margin A = HFA * non-neutral indicator + rating A - "
                    "rating B; team ratings sum to zero within a season; margin cap 49; "
                    "ridge lambda 0.3 with the HFA term unpenalized; HFA mode "
                    "season_fit."
                ),
                "fully_specified": True,
                "preseason_transition": (
                    "2026 Pure Baxter = 0.70 * 2025 Baxter Ridge rating; documented "
                    "regression imputation for entrants with no prior-season fit."
                ),
                "required_input": (
                    "complete prior-season game ledger with scores and a neutral-site "
                    "indicator"
                ),
                "source_of_specification": (
                    "Baxter_Ratings_v1_Joint_2024_2025_Validation_and_Freeze.xlsx sheets "
                    "'Doctrine' and 'Executive Summary'; "
                    "Baxter_v1_2006_2011_2024_2025_Complete_Package/README.txt"
                ),
            },
            "master_column": "AQ",
            "native_field": "2026 Pure Baxter Rating",
            "preseason_effective_date": (
                "2026 preseason; carry-forward of the 2025 ridge fit"
            ),
            "reproducible_algorithmically": True,
            "standardized_column": "BR",
            "supplying_artifact_2026": (
                "2026_Synthetic_CFB_Preseason_Baxter_Carryforward.xlsx"
            ),
            "supplying_artifact_sha256": None,
            "upstream_evidence_class": "SYNTHETIC_2025_SEASON_LEDGER",
            "weight": 0.25,
        },
        {
            "family_id": "BOARD_FAMILY",
            "family_name": "Board Family",
            "combination_rule": (
                "Board Family Z = AVERAGE(Board I-H Z, Board J-B Z). The two members "
                "are standardized separately against their own field deviations and "
                "then averaged; this is not the Z score of an averaged native value."
            ),
            "externally_sourced": False,
            "members": [
                {
                    "generator": {
                        "algorithm": (
                            "power_H = (16*baseline + 8*returning + 6*movement + "
                            "4*talent + 3*coaching) / 37, i.e. weights 0.432432, "
                            "0.216216, 0.162162, 0.108108, 0.081081."
                        ),
                        "component_scoring_manual": (
                            "NOT_DOCUMENTED_IN_ANY_LOCATED_ARTIFACT"
                        ),
                        "fully_specified": False,
                        "solved_weights_max_residual": 9.06e-06,
                        "source_of_specification": (
                            "Board_I-K_Derivation_Methodology.md section 2, corroborated "
                            "by least squares over the 118 non-academy rows of "
                            "2026_Board_I-H_v2.xlsx"
                        ),
                    },
                    "master_column": "S",
                    "member_id": "BOARD_I_H",
                    "native_field": "Board I-H Power Rating (power_H)",
                    "standardized_column": "BO",
                    "supplying_artifact_2026": "2026_Board_I-H_v2.xlsx",
                    "supplying_artifact_sha256": (
                        "278701fc8e8ef62f992cf9f04f2ddddb6ba15c428cbd833a7bd14babf62b2213"
                    ),
                    "weight": 0.125,
                },
                {
                    "generator": {
                        "algorithm": (
                            "power_Run2 = 0.35*baseline + 0.20*returning + "
                            "0.25*movement + 0.10*talent + 0.10*coaching, over the SAME "
                            "component vector as Board I-H v2; academies exclude talent "
                            "and renormalize the remaining terms over 0.90."
                        ),
                        "component_scoring_manual": (
                            "NOT_DOCUMENTED_IN_ANY_LOCATED_ARTIFACT"
                        ),
                        "fully_specified": False,
                        "reproduction_max_residual": 1.11e-16,
                        "source_of_specification": (
                            "2026_Board_J-B_Run2.xlsx sheet 'Rulings Run2', field "
                            "POWER_FORMULA; scenario approved by the Chairman 2026-07-28"
                        ),
                    },
                    "master_column": "W",
                    "member_id": "BOARD_J_B",
                    "native_field": "Board J-B Run2 Power Rating (power_Run2)",
                    "standardized_column": "BP",
                    "supplying_artifact_2026": "2026_Board_J-B_Run2.xlsx",
                    "supplying_artifact_sha256": (
                        "bcec6150b9bf46b9cee2fb8accb3f0a7875848d09983a5b2e0a17374d6df46aa"
                    ),
                    "weight": 0.125,
                },
            ],
            "member_independence": {
                "component_vectors_identical": True,
                "distinct_component_rows": 0,
                "pearson_r_between_member_power_series": 0.99721236,
                "statement": (
                    "The two Board members are not two boards. They are one "
                    "Chairman-governed component vector under two approved weightings; "
                    "every one of the 121 rows carries identical baseline, returning, "
                    "movement, talent and coaching values in both workbooks. The Board "
                    "family therefore contributes one independent measurement at 25% "
                    "weight, not two at 12.5%."
                ),
            },
            "native_field": (
                "mean of standardized Board I-H power_H and Board J-B power_Run2"
            ),
            "preseason_effective_date": (
                "2026-07-14 (I-H v2) and 2026-07-28 (J-B Run 2)"
            ),
            "reproducible_algorithmically": False,
            "standardized_column": "BQ",
            "upstream_evidence_class": "CHAIRMAN_GOVERNED_HUMAN_BOARD",
            "weight": 0.25,
        },
    ],
    "output_transforms": {
        "family_disagreement": (
            "STDEV(TrueSkill Z, Litkenhous Z, Board Family Z, Pure Baxter Z)"
        ),
        "unified_master_power_index": "100 + 10 * Unified Master Z",
        "unified_master_z": (
            "0.25*TrueSkill Z + 0.25*Litkenhous Z + 0.25*Pure Baxter Z + "
            "0.25*Board Family Z"
        ),
        "unified_neutral_field_points": (
            "14 * Unified Master Z (workbook calls this provisional)"
        ),
    },
    "standardization": {
        "ddof": 1,
        "formula": "(native - AVERAGE(population)) / STDEV(population)",
        "note": (
            "The workbook titles this block 'Population Statistics' but divides by "
            "Excel STDEV, the sample deviation. Confirmed independently by the sibling "
            "historical-opening-state lane, which reproduces every family Z at ddof=1 "
            "and none at ddof=0."
        ),
        "population": "the 121 FBS rows of the Master Ratings sheet",
    },
    "the_board_dependency": {
        "board_dependent_families": ["BOARD_FAMILY", "LITKENHOUS"],
        "board_dependent_weight": 0.5,
        "board_free_families": ["PURE_BAXTER", "TRUESKILL"],
        "statement": (
            "Half the Unified Master Z weight terminates in the Board component "
            "vector: the Board family directly at 0.25, and Litkenhous through its "
            "Layer 2 offseason composite at a further 0.25. The Ensemble Parameters "
            "sheet describes Litkenhous as an independent family; against the "
            "arithmetic it is not independent of the Board."
        ),
    },
}

# --------------------------------------------------------------------------
# Sections 2/3 -- per-season, per-component source recovery
# --------------------------------------------------------------------------

_LEDGER_2020_EVIDENCE = (
    "The NCAA scoreboard feed serves 2020. Probing "
    "https://data.ncaa.com/casablanca/scoreboard/football/fbs/2020/{week}/"
    "scoreboard.json for weeks 01-15 returns HTTP 200 with 616 scheduled entries and "
    "523 games in state 'final'; weeks 16+ are empty. 2020 was the COVID-disrupted "
    "season and the feed carries no postseason, so a replayed 2020 fit would rest on "
    "an abnormal and bowl-free schedule."
)

_LEDGER_R6_EVIDENCE = (
    "Raw NCAA scoreboard captures for this season exist on the unmerged sibling "
    "branch claude/v3-historical-observation-corpus-r6 and its admitted corpus is "
    "materially short of the real field. The corpus also classifies venue as BLOCKED "
    "-- the feed publishes no neutral-site indicator -- and both the Baxter ridge "
    "(HFA mode season_fit) and SYTHLAX-LIT-V0 (jointly estimated home-field "
    "coefficient) require one."
)

_R6_COVERAGE = {2021: (556, 105), 2022: (524, 101), 2023: (598, 114), 2024: (563, 108)}
_REAL_FBS = {2021: 130, 2022: 131, 2023: 133, 2024: 134}


def _prior_ledger_row(season: int) -> dict:
    prior = season - 1
    if prior == 2020:
        evidence = _LEDGER_2020_EVIDENCE
        missing = (
            "No 2020 game ledger of any kind exists on the filesystem. The "
            "authoritative feed is reachable and unmounted."
        )
        team_count = None
        games = 523
    else:
        games, teams = _R6_COVERAGE[prior]
        evidence = (
            f"{_LEDGER_R6_EVIDENCE} For {prior} the admitted corpus carries {games} "
            f"games over {teams} distinct teams against a real FBS field of "
            f"{_REAL_FBS[prior]}."
        )
        missing = (
            f"Unmerged, incomplete ({teams} of {_REAL_FBS[prior]} programs), "
            "postseason-free, and carrying no neutral-site indicator."
        )
        team_count = teams
        games = games
    return {
        "authority_status": "PUBLIC_ARCHIVE_UNGOVERNED",
        "classification": "ARCHIVED_SOURCE_LOCATED_NOT_MOUNTED",
        "component": "PRIOR_SEASON_GAME_LEDGER",
        "effective_date": (
            f"end of the {prior} season, before the {season} season opens"
        ),
        "evidence": evidence,
        "family": "SHARED_PREREQUISITE",
        "games_available": games,
        "leakage_status": "PRESEASON_CLEAN_FOR_TARGET_SEASON",
        "missing_reason": missing,
        "reconstructable": True,
        "season": season,
        "source": (
            "https://data.ncaa.com/casablanca/scoreboard/football/{division}/"
            f"{prior}/{{week}}/scoreboard.json"
        ),
        "source_effective_date": f"{prior} season, published weekly",
        "team_count": team_count,
    }


def _population_row(season: int) -> dict:
    row = {
        "authority_status": "PUBLIC_ARCHIVE_UNGOVERNED",
        "classification": "ARCHIVED_SOURCE_LOCATED_NOT_MOUNTED",
        "component": "HISTORICAL_FBS_POPULATION",
        "effective_date": f"settled before the {season} season opens",
        "evidence": (
            "Membership is settled before a season starts, so this class is "
            "leakage-clean. Two rosters were located and both are frozen at 251 "
            "entities; see V3_OPENING_POPULATION_RECONCILIATION_R1.json."
        ),
        "family": "SHARED_PREREQUISITE",
        "leakage_status": "PRESEASON_CLEAN",
        "reconstructable": True,
        "season": season,
        "source": (
            "251_Team_Conference_Affiliations_2012_2026.xlsx (Conference Affiliations, "
            "251 rows, 2012-2026, source-cited to NCAA / Sports-Reference / conference "
            "releases); Synthetic_NCAA_Conference_Distribution_2021_2026.xlsx "
            "(Team Affiliations, per-season subdivision)"
        ),
        "source_effective_date": f"{season} membership, settled preseason",
        "team_count": _REAL_FBS[season],
    }
    if season == 2024:
        row["missing_reason"] = (
            "Neither located candidate states the real 2024 field of 134. The "
            "conference-distribution workbook gives 133 because Kennesaw State is "
            "absent from its frozen 251-entity roster; the Phase5J registry gives 118 "
            "because it is a synthetic universe, not a membership record."
        )
    else:
        row["missing_reason"] = (
            "The conference-distribution workbook reproduces the real count for this "
            "season but its named upstream, Synthetic_CFB_2021_2026_Walkover_RERUN.csv, "
            "was not located, so the lineage is documented and not closed to bytes."
        )
    return row


def _rows() -> list[dict]:
    rows: list[dict] = []
    for season in SEASONS:
        prior = season - 1
        rows.append(
            {
                "authority_status": "NONE_LOCATED",
                "classification": "ALGORITHMICALLY_RECONSTRUCTABLE",
                "component": "TRUESKILL_PRESEASON_MU",
                "effective_date": f"{season} preseason",
                "evidence": (
                    "No 2021-2024 TrueSkill artifact exists. The whole located lineage "
                    "is Operation_Sythalax_TrueSkill_2025_2026_Thread_Consolidation.xlsx, "
                    "whose 2025 season opens with pregame_mu 25 and pregame_sigma "
                    "8.333333 for every team. The generating method is nevertheless "
                    "fully specified (TS-V0-2025-001 replay, then the "
                    "P0-LAMBDA070-OMEGA300-v1 transition) and consumes only "
                    "prior-season results, which is information available before the "
                    "target season."
                ),
                "family": "TRUESKILL",
                "leakage_status": "PRESEASON_CLEAN_UNDER_REPLAY",
                "missing_reason": (
                    f"Requires a complete {prior} game ledger, which is not mounted. "
                    "The 2026 value derives from a SYNTHETIC 2025 season; a replay over "
                    "real games is a different evidence lineage and must be labelled as "
                    "one rather than presented as the same object."
                ),
                "reconstructable": True,
                "reconstruction_gate": "PRIOR_SEASON_GAME_LEDGER",
                "season": season,
                "source": "NONE_LOCATED",
                "source_effective_date": None,
                "team_count": 0,
            }
        )
        rows.append(
            {
                "authority_status": "NONE_LOCATED",
                "classification": "ALGORITHMICALLY_RECONSTRUCTABLE",
                "component": "PURE_BAXTER_RATING",
                "effective_date": f"{season} preseason",
                "evidence": (
                    "The Baxter universe is 2006-2011, 2024 and 2025; there is no "
                    "2012-2023 fit of any kind. Baxter_Ratings_2024.csv carries a 2024 "
                    "label but is a ridge fit over 2024's own games -- its rows carry "
                    "post-season game counts -- and is refused as a 2024 preseason "
                    "value. The frozen specification BAXTER-MOV-v1.0-R is complete "
                    "enough to replay over any prior-season ledger."
                ),
                "family": "PURE_BAXTER",
                "leakage_status": "PRESEASON_CLEAN_UNDER_REPLAY",
                "missing_reason": (
                    f"Requires a complete {prior} game ledger with scores and a "
                    "neutral-site indicator. No such ledger is mounted, and the one "
                    "historical corpus in the programme classifies venue as BLOCKED."
                ),
                "reconstructable": True,
                "reconstruction_gate": "PRIOR_SEASON_GAME_LEDGER_WITH_NEUTRAL_FLAG",
                "season": season,
                "source": "NONE_LOCATED",
                "source_effective_date": None,
                "team_count": 0,
            }
        )
        rows.append(
            {
                "authority_status": "NONE_LOCATED",
                "classification": "ALGORITHMICALLY_RECONSTRUCTABLE",
                "component": "LITKENHOUS_PURE_CARRYOVER",
                "effective_date": f"{season} preseason",
                "evidence": (
                    "Layer 1 only. SYTHLAX-LIT-V0 is fully specified and the carry "
                    "weight 0.60 is published. This is the reconstructable half of the "
                    "Litkenhous family and on its own it is not the V3 input."
                ),
                "family": "LITKENHOUS",
                "leakage_status": "PRESEASON_CLEAN_UNDER_REPLAY",
                "missing_reason": (
                    f"Requires a complete {prior} game ledger with scores and a "
                    "neutral-site indicator."
                ),
                "reconstructable": True,
                "reconstruction_gate": "PRIOR_SEASON_GAME_LEDGER_WITH_NEUTRAL_FLAG",
                "season": season,
                "source": "NONE_LOCATED",
                "source_effective_date": None,
                "team_count": 0,
            }
        )
        rows.append(
            {
                "authority_status": "NONE_LOCATED",
                "classification": "NO_HISTORICAL_COUNTERPART_FOUND",
                "component": "LITKENHOUS_OFFSEASON_COMPOSITE",
                "effective_date": f"{season} preseason",
                "evidence": (
                    "The composite is the Board I-H component vector under the I-H "
                    "sub-weights. Recomputing it from the Board sheet reproduces the "
                    "published column to 6.7e-16. It inherits every Board blocker."
                ),
                "family": "LITKENHOUS",
                "leakage_status": "NOT_APPLICABLE",
                "missing_reason": (
                    "No board of any letter exists for any season before 2026, and the "
                    "component scoring manual is not reproduced in any located artifact."
                ),
                "reconstructable": False,
                "reconstruction_gate": "BOARD_COMPONENT_VECTOR",
                "season": season,
                "source": "NONE_LOCATED",
                "source_effective_date": None,
                "team_count": 0,
            }
        )
        rows.append(
            {
                "authority_status": "NONE_LOCATED",
                "classification": "NO_HISTORICAL_COUNTERPART_FOUND",
                "component": "LITKENHOUS_ADJUSTED_POWER",
                "effective_date": f"{season} preseason",
                "evidence": (
                    "The V3 native input, master column L. It is Layer 1 plus Layer 2 "
                    "and cannot be formed while Layer 2 is unavailable. The Litkenhous "
                    "name does not import a historical series: the historical "
                    "Litkenhous Difference by Score system was an NCAA major selector "
                    "for 1934-1984 whose algorithm source record SRC-LIT-001 marks "
                    "BLOCKED, and no historical Litkenhous rating exists for 2021-2024 "
                    "because the historical system had long ceased publication."
                ),
                "family": "LITKENHOUS",
                "leakage_status": "NOT_APPLICABLE",
                "missing_reason": "Blocked by LITKENHOUS_OFFSEASON_COMPOSITE.",
                "reconstructable": False,
                "reconstruction_gate": "BOARD_COMPONENT_VECTOR",
                "season": season,
                "source": "NONE_LOCATED",
                "source_effective_date": None,
                "team_count": 0,
            }
        )
        for member, native, artifact in (
            (
                "BOARD_I_H_POWER_H",
                "Board I-H Power Rating (power_H)",
                "2026_Board_I-H_v2.xlsx",
            ),
            (
                "BOARD_J_B_POWER_RUN2",
                "Board J-B Run2 Power Rating (power_Run2)",
                "2026_Board_J-B_Run2.xlsx",
            ),
        ):
            rows.append(
                {
                    "authority_status": "CHAIRMAN_GOVERNED_2026_ONLY",
                    "classification": "NO_HISTORICAL_COUNTERPART_FOUND",
                    "component": member,
                    "effective_date": f"{season} preseason",
                    "evidence": (
                        f"The only located artifact carrying {native} is {artifact}, "
                        "dated 2026. Every board in the series -- I, I-H, I-H v2, I-I, "
                        "I-J, I-K, J-A, J-B, J-C -- is 2026. A filesystem sweep for "
                        "board artifacts returned no board bearing a 2012-2025 label."
                    ),
                    "family": "BOARD_FAMILY",
                    "leakage_status": "NOT_APPLICABLE",
                    "missing_reason": (
                        "The board did not exist historically. It is a human, "
                        "Chairman-governed instrument: its rulings are dated and "
                        "signed, its imputations are accepted risks recorded by name "
                        "(R-H4-ACCEPT, D-MARKET-NDSU), and "
                        "Board_I-K_Derivation_Methodology.md section 7 states that the "
                        "component-by-component scoring manual is not reproduced "
                        "anywhere. Its largest term, baseline at 16/37, is defined as "
                        "carry-forward from a SYNTHETIC 2025 season, which has no "
                        "historical analogue by construction."
                    ),
                    "reconstructable": False,
                    "reconstruction_gate": "NONE_EXISTS",
                    "season": season,
                    "source": "NONE_LOCATED",
                    "source_effective_date": None,
                    "team_count": 0,
                }
            )
        rows.append(_prior_ledger_row(season))
        rows.append(_population_row(season))
    return rows


REFUSED_CANDIDATES = [
    {
        "candidate": "Baxter_Ratings_2024.csv",
        "disposition": "POSTSEASON_ONLY",
        "provides_families": ["PURE_BAXTER"],
        "reason": (
            "A ridge fit over 2024's own completed games; its games column carries "
            "post-season counts. Admissible as a 2025 preseason carry-forward input, "
            "never as a 2024 preseason value."
        ),
        "seasons_claimed": [2024],
    },
    {
        "candidate": "Power_Crunch_Research_Lab_Phase5J_2024_FACT_Ratings_Package.zip",
        "disposition": "POSTSEASON_ONLY",
        "provides_families": [],
        "reason": (
            "season_config_2024.json declares season_status COMPLETE, "
            "include_postseason true and calculation_cutoff_date 2025-01-31. FACT is "
            "also not a V3 family."
        ),
        "seasons_claimed": [2024],
    },
    {
        "candidate": "Power_Crunch_Research_Lab_Phase5M_2024_CPI_Ratings_Package.zip",
        "disposition": "POSTSEASON_ONLY",
        "provides_families": [],
        "reason": (
            "Built from accepted_games_2024.csv; a 2024 rating computed from 2024 "
            "results."
        ),
        "seasons_claimed": [2024],
    },
    {
        "candidate": "pregame_states_2024_2025.csv",
        "disposition": "SYNTHETIC_ONLY",
        "provides_families": [],
        "reason": (
            "The only genuinely leak-free season-opening state located, and "
            "degenerate: every 2024 week-0 row carries elo_a_pre and elo_b_pre exactly "
            "1500.0, so the opening population has zero dispersion and no deviation to "
            "divide by. It is also research Elo, base 1500 -- not a V3 family and a "
            "foreign scale."
        ),
        "seasons_claimed": [2024, 2025],
    },
    {
        "candidate": "2025_Synthetic_CFB_Litkenhous_Inspired_Final_Ratings.xlsx",
        "disposition": "POSTSEASON_ONLY",
        "provides_families": ["LITKENHOUS"],
        "reason": (
            "A 2025 season-final rating, and out of the 2021-2024 scope. Registered "
            "here because its Methodology sheet is the specification that makes "
            "LITKENHOUS_PURE_CARRYOVER replayable."
        ),
        "seasons_claimed": [2025],
    },
    {
        "candidate": "2026_TEAM_CANONICAL_MASTER_v2_LLM_GROUNDING.md",
        "disposition": "SYNTHETIC_ONLY",
        "provides_families": [],
        "reason": (
            "The canonical identity authority for a synthetic 2026 universe of 134 "
            "entities. It classifies eight real FBS programs as SCHEDULE_ONLY_FCS and "
            "nine real FCS programs as FBS_MEMBER. Usable for identity binding, never "
            "as a historical population."
        ),
        "seasons_claimed": [2026],
    },
    {
        "candidate": "Litkenhous Ratings source-ingestion package (SRC-LIT-001)",
        "disposition": "NO_HISTORICAL_COUNTERPART_FOUND",
        "provides_families": ["LITKENHOUS"],
        "reason": (
            "The genuine historical provenance record for the Litkenhous Difference by "
            "Score system. Its empirical scope is the 1934-1984 No. 1 selections; the "
            "algorithm, coefficients and score transformation are all recorded BLOCKED, "
            "and direct_production_weight is 0.0. It establishes that no historical "
            "Litkenhous rating exists for 2021-2024 and that none could be recomputed."
        ),
        "seasons_claimed": [1934, 1984],
    },
]

BOARD_SUBSTITUTE_CANDIDATES = {
    "adjudication_note": (
        "Reported for later adjudication only. None is adopted, none is mounted, and "
        "none is proposed as an authority. Substituting any of them changes what the "
        "Board family measures, which is a Chairman decision and not an evidence one."
    ),
    "candidates": [
        {
            "board_component_addressed": "talent",
            "candidate": "247Sports Team Talent Composite",
            "coverage": "full FBS field, published annually before Week 1",
            "seasons_available": [2021, 2022, 2023, 2024],
        },
        {
            "board_component_addressed": "returning",
            "candidate": "Returning production (SP+ author's published metric)",
            "coverage": "full FBS field, published in the offseason",
            "seasons_available": [2021, 2022, 2023, 2024],
        },
        {
            "board_component_addressed": "movement",
            "candidate": "Transfer-portal team rankings (247Sports / On3)",
            "coverage": "full FBS field, published before Week 1",
            "seasons_available": [2021, 2022, 2023, 2024],
        },
        {
            "board_component_addressed": "market",
            "candidate": "Sportsbook preseason season win totals",
            "coverage": "most FBS programs, posted before Week 1",
            "seasons_available": [2021, 2022, 2023, 2024],
        },
        {
            "board_component_addressed": "baseline (whole-board proxy)",
            "candidate": "SP+ preseason ratings",
            "coverage": "full FBS field, published before Week 1",
            "seasons_available": [2021, 2022, 2023, 2024],
        },
        {
            "board_component_addressed": "baseline (whole-board proxy)",
            "candidate": "ESPN FPI preseason projections",
            "coverage": "full FBS field, published before Week 1",
            "seasons_available": [2021, 2022, 2023, 2024],
        },
        {
            "board_component_addressed": "whole-board proxy, ordinal only",
            "candidate": "AP and Coaches preseason polls",
            "coverage": (
                "25 ranked teams plus others receiving votes; not a full-field rating "
                "and cannot be standardized over a 130+ population"
            ),
            "seasons_available": [2021, 2022, 2023, 2024],
        },
    ],
    "coaching_component": (
        "No published preseason index corresponds to the Board's coaching term. "
        "Coaching changes are documented facts, but the mapping from a change to a "
        "0-1 score is the undocumented part."
    ),
    "fundamental_limit": (
        "Even with every raw input above, the Board values cannot be reproduced. What "
        "is missing is not the inputs but the rubric that maps them onto the 0-1 "
        "component scale, together with the case-by-case rulings that override it. "
        "A substitute board would be a different instrument wearing the same weight."
    ),
}

SOURCE_RECOVERY_MATRIX = {
    "artifact": "V3_OPENING_SOURCE_RECOVERY_MATRIX_R1",
    "artifact_version": ARTIFACT_VERSION,
    "board_substitute_candidates": BOARD_SUBSTITUTE_CANDIDATES,
    "classification_vocabulary": [
        "ALGORITHMICALLY_RECONSTRUCTABLE",
        "AMBIGUOUS",
        "ARCHIVED_SOURCE_LOCATED_NOT_MOUNTED",
        "EXACT_SOURCE_RECOVERED",
        "NO_HISTORICAL_COUNTERPART_FOUND",
        "POSTSEASON_ONLY",
        "SYNTHETIC_ONLY",
    ],
    "exact_source_recovered_count": 0,
    "refused_candidates": REFUSED_CANDIDATES,
    "rows": _rows(),
    "seasons_in_scope": list(SEASONS),
    "v3_point_values_emitted": 0,
}

# --------------------------------------------------------------------------
# Section 7 -- coverage matrix
# --------------------------------------------------------------------------

COVERAGE_MATRIX = {
    "all_four_families_required": True,
    "artifact": "V3_OPENING_COVERAGE_MATRIX_R1",
    "artifact_version": ARTIFACT_VERSION,
    "families": ["TRUESKILL", "LITKENHOUS", "PURE_BAXTER", "BOARD_FAMILY"],
    "matrix": {
        str(season): {
            "BOARD_FAMILY": {
                "authority": "CHAIRMAN_GOVERNED_2026_ONLY",
                "effective_date": None,
                "status": "NO_HISTORICAL_COUNTERPART_FOUND",
                "team_count": 0,
            },
            "LITKENHOUS": {
                "authority": "NONE_LOCATED",
                "effective_date": None,
                "status": "NO_HISTORICAL_COUNTERPART_FOUND",
                "team_count": 0,
            },
            "PURE_BAXTER": {
                "authority": "NONE_LOCATED",
                "effective_date": None,
                "status": "ALGORITHMICALLY_RECONSTRUCTABLE",
                "team_count": 0,
            },
            "TRUESKILL": {
                "authority": "NONE_LOCATED",
                "effective_date": None,
                "status": "ALGORITHMICALLY_RECONSTRUCTABLE",
                "team_count": 0,
            },
            "population_required": _REAL_FBS[season],
            "unified_z_constructible": False,
        }
        for season in SEASONS
    },
    "missing_family_renormalization": {
        "existing_v3_rule": None,
        "invented_here": False,
        "statement": (
            "The key question this lane was asked -- whether all four families are "
            "necessary or whether existing V3 rules already permit missing-family "
            "renormalization -- resolves to: all four are necessary and no such rule "
            "exists. The workbook hardcodes Included Family Count at 4 and validates "
            "MIN = 4; combine_unified_z refuses a subset with ComponentUnavailable "
            "rather than reweighting. Two of four families being reconstructable does "
            "not yield two-thirds of a Unified Z or a rescaled one. It yields nothing, "
            "until somebody with authority rules otherwise."
        ),
    },
    "seasons_in_scope": list(SEASONS),
}

# --------------------------------------------------------------------------
# Section 8 -- population reconciliation
# --------------------------------------------------------------------------

_ECL = [
    "Colgate",
    "Cornell",
    "Harvard",
    "Holy Cross",
    "Lehigh",
    "Penn",
    "Princeton",
    "Yale",
]

POPULATION_RECONCILIATION = {
    "artifact": "V3_OPENING_POPULATION_RECONCILIATION_R1",
    "artifact_version": ARTIFACT_VERSION,
    "brief_figure_correction": {
        "figure_in_evidence": 118,
        "figure_in_lane_brief": 128,
        "statement": (
            "The lane brief describes the 2024 disagreement as 133 vs 128. No artifact "
            "on any branch or on the filesystem states a 2024 FBS population of 128. "
            "The figure in evidence is 118, from team_registry_2024.csv inside the "
            "Phase5J package, and it is what the sibling lane recorded."
        ),
    },
    "candidates": [
        {
            "candidate_id": "CONFERENCE_DISTRIBUTION_2021_2026",
            "class": "REAL_MEMBERSHIP_RECORD_WITH_A_FROZEN_ROSTER",
            "fbs_counts": {"2021": 130, "2022": 131, "2023": 133, "2024": 133},
            "location": "Synthetic_NCAA_Conference_Distribution_2021_2026.xlsx",
            "sha256": (
                "376a6f624eea6c60794f061de27f3d875c127e89afc80ec4f81664742588e2ac"
            ),
            "verdict": (
                "Reproduces real FBS membership exactly for 2021, 2022 and 2023, and "
                "its season-to-season deltas are the real ones -- James Madison in "
                "2022, Jacksonville State and Sam Houston in 2023. It is one short for "
                "2024, for a single identifiable reason recorded under "
                "disputed_programs."
            ),
        },
        {
            "candidate_id": "PHASE5J_TEAM_REGISTRY_2024",
            "class": "SYNTHETIC_MODELLING_UNIVERSE",
            "fbs_counts": {"2024": 118},
            "location": (
                "Power_Crunch_Research_Lab_Phase5J_2024_FACT_Ratings_Package.zip"
                "!01_Inputs/team_registry_2024.csv"
            ),
            "sha256": (
                "0cf7ac5704a78d56d8bbbacdaec23c0e7e4f802edbce181ad10b817f4e0e16ef"
            ),
            "verdict": (
                "Not a membership record at all. Its conference column carries "
                "Atlantic-8, ECL and a two-member Pac-12, none of which existed in "
                "real 2024 football. The sibling Phase5D package's GOVERNING_RULES.md "
                "declares 'ECL is a full FBS conference' and its INPUTS.md crosswalk "
                "marks the eight ECL schools OUT as 'real FCS -- do not anchor', which "
                "is the package stating in its own words that its universe is "
                "synthetic."
            ),
        },
        {
            "candidate_id": "TEAM_CONFERENCE_AFFILIATIONS_2012_2026",
            "class": "REAL_MEMBERSHIP_RECORD_WITH_A_FROZEN_ROSTER",
            "fbs_counts": {},
            "location": (
                "C:/2026 Synthetic NCAA/251_Team_Conference_Affiliations_2012_2026.xlsx"
            ),
            "sha256": None,
            "verdict": (
                "Newly located by this lane and not previously registered. 251 teams by "
                "season for 2012-2026 with a Sources sheet citing NCAA releases, "
                "Sports-Reference and conference announcements. It reaches back to "
                "2012, which covers the 2020 prior season a 2021 reconstruction needs, "
                "and it is the better population candidate of the two -- but it shares "
                "the same frozen 251-entity roster and therefore the same 2024 "
                "omission. It records conference, not subdivision, so subdivision would "
                "have to be derived from the conference labels."
            ),
        },
    ],
    "disputed_programs": [
        {
            "classification": "REAL_FBS_2024_ABSENT_FROM_EVERY_LOCATED_UNIVERSE",
            "evidence": (
                "Kennesaw State joined Conference USA and began FBS play on 1 July "
                "2024, announced by the conference on 2022-10-14. It appears in "
                "neither 251-entity roster and in no registry located by this lane. It "
                "is the whole of the 133-vs-134 gap."
            ),
            "program": "Kennesaw State",
            "resolution": "ADD_TO_2024_POPULATION_ON_EVIDENCE",
        },
        *[
            {
                "classification": "SYNTHETIC_FBS_BY_FIAT_REAL_FCS",
                "evidence": (
                    "Carried as FBS in the ECL conference by the Phase5J registry and "
                    "as FBS_MEMBER by the 2026 canonical master. Real division in "
                    "2021-2024 is FCS, and the Phase5D crosswalk marks it OUT for "
                    "exactly that reason."
                ),
                "program": program,
                "resolution": "EXCLUDE_FROM_HISTORICAL_POPULATION_ON_EVIDENCE",
            }
            for program in _ECL
        ],
        {
            "classification": "SYNTHETIC_FBS_BY_FIAT_REAL_FCS",
            "evidence": (
                "FBS_MEMBER in the synthetic 2026 canonical master; FCS in all four "
                "seasons in scope. Its real FBS move is 2026."
            ),
            "program": "North Dakota State",
            "resolution": "EXCLUDE_FROM_HISTORICAL_POPULATION_ON_EVIDENCE",
        },
    ],
    "finding": (
        "The 2024 disagreement is not a membership dispute and does not need a "
        "Chairman ruling. The two figures describe two different objects: 133 is a "
        "real-membership count taken over a roster frozen before Kennesaw State "
        "existed as an FBS program, and 118 is the size of a synthetic modelling "
        "universe that admits eight Ivy and Patriot League schools as FBS and omits "
        "sixteen real FBS programs. Reconciled against contemporaneous evidence the "
        "real 2024 FBS field is 134, and neither candidate states it."
    ),
    "real_fbs_counts": {str(season): _REAL_FBS[season] for season in SEASONS},
    "ruling_required": False,
    "ruling_requested": False,
}

# --------------------------------------------------------------------------
# Section 10 -- decision
# --------------------------------------------------------------------------

STATUS = {
    "artifact": "V3_OPENING_SOURCE_RECOVERY_STATUS_R1",
    "artifact_version": ARTIFACT_VERSION,
    "blockers_opened": 0,
    "blockers_retired": 0,
    "decisions": {
        "A_exact_reconstruction_possible": {
            "answer": "NO",
            "detail": (
                "Not for 2021, not for 2022, not for 2023, not for 2024. The Board "
                "family carries 25% of the Unified Master Z directly and a further 25% "
                "through the Litkenhous Layer 2 offseason composite, and no board of "
                "any letter existed before 2026."
            ),
        },
        "B_missing_families_and_seasons": {
            "answer": "BOARD_FAMILY and LITKENHOUS, in all four seasons",
            "detail": (
                "TRUESKILL and PURE_BAXTER are missing as artifacts but recoverable as "
                "method. BOARD_FAMILY and LITKENHOUS are missing as artifacts and "
                "unrecoverable as method. The seasons do not differ from one another: "
                "the gap is a property of the family lineage, not of any season."
            ),
        },
        "C_algorithmic_reconstruction_from_preseason_information": {
            "answer": "PARTIAL - two of four families",
            "detail": (
                "TrueSkill (TS-V0 replay then the P0 transition) and Pure Baxter "
                "(BAXTER-MOV-v1.0-R ridge then 0.70 carry-forward) are fully specified "
                "and consume only prior-season results, which is genuinely preseason "
                "information for the target season. Litkenhous Layer 1 is likewise "
                "specified. All three are gated on one artifact class -- a complete "
                "prior-season game ledger carrying scores and a neutral-site indicator "
                "-- and none is mounted. Litkenhous Layer 2 and both Board members are "
                "not reconstructable at any price, because the component scoring manual "
                "was never written down and the baseline term is defined against a "
                "synthetic season."
            ),
        },
        "D_impossible_because_a_family_did_not_exist": {
            "answer": "YES",
            "detail": (
                "This is the operative finding. The Board family is a human, "
                "Chairman-governed instrument first issued in 2026. Its components are "
                "scored once, preseason, by judgement; its rulings are dated and "
                "signed; its published derivation note states outright that the "
                "component-by-component scoring manual is not reproduced; and its "
                "largest term is carry-forward from a synthetic season that has no "
                "historical counterpart. No acquisition can recover a measurement that "
                "was never taken. An exact historical V3 opening state is therefore not "
                "blocked pending evidence -- it is impossible."
            ),
        },
        "E_smallest_evidence_acquisition": {
            "answer": (
                "One artifact class, which unblocks two families and still does not "
                "produce a Unified Z"
            ),
            "detail": (
                "The smallest acquisition that moves anything is a complete season game "
                "ledger for 2020, 2021, 2022 and 2023 carrying, per game: both "
                "participants under a historical identity authority, both scores, and a "
                "neutral-site indicator. That single class unlocks TrueSkill, Pure "
                "Baxter and Litkenhous Layer 1 for all four seasons at once. The NCAA "
                "scoreboard feed is verified reachable for 2020 and already captured "
                "for 2021-2024 on an unmerged sibling branch, but it publishes no "
                "neutral-site indicator and no postseason, so it does not by itself "
                "satisfy the class. Acquiring it still does not produce a Unified Z, "
                "because the Board family remains absent and no missing-family rule "
                "exists. Whether a two-family opening state is worth anything is a "
                "governance question, and this lane does not answer it."
            ),
        },
    },
    "families_algorithmically_reconstructable": 2,
    "families_required_for_unified_z": 4,
    "monte_carlo_runs": 0,
    "parameters_fitted": 0,
    "seasons_in_scope": list(SEASONS),
    "terminal_status": "OPENING_SOURCE_RECOVERY_EXACT_NOT_POSSIBLE",
    "unblocking_summary": {
        "acquisition_required": (
            "Complete 2020-2023 season game ledgers with participants, scores and a "
            "neutral-site indicator, bound to a historical identity authority."
        ),
        "impossible_regardless_of_acquisition": [
            "BOARD_I_H",
            "BOARD_J_B",
            "LITKENHOUS_LAYER_2",
        ],
        "unlocked_by_acquisition": [
            "LITKENHOUS_PURE_CARRYOVER",
            "PURE_BAXTER_RATING",
            "TRUESKILL_PRESEASON_MU",
        ],
    },
    "v3_point_values_emitted": 0,
}

ARTIFACTS = {
    "V3_OPENING_COVERAGE_MATRIX_R1.json": COVERAGE_MATRIX,
    "V3_OPENING_FAMILY_INVENTORY_R1.json": FAMILY_INVENTORY,
    "V3_OPENING_POPULATION_RECONCILIATION_R1.json": POPULATION_RECONCILIATION,
    "V3_OPENING_SOURCE_RECOVERY_MATRIX_R1.json": SOURCE_RECOVERY_MATRIX,
    "V3_OPENING_SOURCE_RECOVERY_STATUS_R1.json": STATUS,
}


def render(payload: object) -> str:
    """Deterministic bytes: sorted keys, two-space indent, LF, trailing newline.

    No artifact carries a ``generated_at`` field. A timestamp inside the bytes
    would defeat byte-identity on the second run; git records *when*.
    """
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def build(out_dir: Path = OUT_DIR) -> dict[str, str]:
    """Write every artifact and return its SHA-256 over the emitted bytes."""
    out_dir.mkdir(parents=True, exist_ok=True)
    digests: dict[str, str] = {}
    for name, payload in sorted(ARTIFACTS.items()):
        text = render(payload)
        (out_dir / name).write_text(text, encoding="utf-8", newline="\n")
        digests[name] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return digests


if __name__ == "__main__":
    for artifact_name, artifact_digest in sorted(build().items()):
        print(f"{artifact_digest}  {artifact_name}")
