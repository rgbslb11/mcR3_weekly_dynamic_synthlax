"""The interface C2 offers to the producing lanes, as a machine-readable record.

C1 supplies the calibration observation set. C3 supplies the Colley Matrix and
SRS witnesses. Both hand over through the versioned contract document; neither
imports this package and this package imports neither of them, so the three
lanes can land independently.

The interface is written down here rather than only in prose so a producing lane
can assert against it, and so a reviewer can diff it when it changes.
"""

from __future__ import annotations

from typing import Any

from ..calibration import (
    CALIBRATION_FIELDS,
    CALIBRATION_OBSERVATION_COLUMNS,
    DATA_SPLITS,
    FORBIDDEN_SIGNAL_PATTERNS,
    INDEPENDENT_WITNESSES,
    PRIMARY_CALIBRATION_DIRECTION,
    PRIMARY_CALIBRATION_METRIC,
    REQUIRED_OBSERVATION_COLUMNS,
    SUPPORTED_DATASET_FORMATS,
)
from ..rulings import R2_CALIBRATION
from .contract import (
    BAXTER_RMSE_DEFINITIONS,
    CONTRACT_SCHEMA_VERSION,
    HFA_SOURCE_LITERAL,
    HFA_SOURCE_V3_CONFIG,
    REFUSED_SPLIT_MODES,
    SUPPORTED_SPLIT_MODES,
)
from .observations import SYNTHETIC_PROVENANCE_PREFIX, VENUES

#: Columns C2 needs beyond the governed minimum, and why.
C2_ADDITIONAL_EXPECTATIONS = {
    "pregame_team_rating": (
        "Required. Seeds a team's rating at its first appearance; without it the harness "
        "would have to invent a starting rating and refuses to run."
    ),
    "pregame_opponent_rating": (
        "Required. Seeds the opponent side on the same terms."
    ),
    "venue": (
        "Team-relative, one of HOME / AWAY / NEUTRAL. Absent, the row is treated as NEUTRAL "
        "and carries no home-field term."
    ),
    "expected_margin": (
        "Optional. The source model's own prediction, used only as a reported baseline "
        "comparison. It is never the harness's prediction."
    ),
    "game_result": (
        "Optional. Enables Brier, log loss and calibration diagnostics. When absent the "
        "outcome is derived from the sign of actual_margin; a zero margin is excluded and "
        "counted rather than assigned a winner."
    ),
    "split": (
        "Required when split_policy.mode is 'column'. One of "
        f"{list(DATA_SPLITS)}."
    ),
    "source_provenance": (
        "Optional but expected. A value beginning "
        f"'{SYNTHETIC_PROVENANCE_PREFIX}' marks the row as fixture data, which the harness "
        "reports as inadmissible as promotion evidence."
    ),
}


def interface_contract() -> dict[str, Any]:
    """The C2 side of the C1 / C3 handoff, as data."""
    return {
        "harness": "C2_BAXTER_RMSE_HARNESS",
        "contract_schema_version": CONTRACT_SCHEMA_VERSION,
        "authority": {
            "ruling": R2_CALIBRATION.convergence_id,
            "chairman_ruling_id": R2_CALIBRATION.chairman_ruling_id,
            "primary_metric": PRIMARY_CALIBRATION_METRIC,
            "primary_direction": PRIMARY_CALIBRATION_DIRECTION,
            "weighted_composite_authorised": False,
        },
        "calibration_axes": list(CALIBRATION_FIELDS),
        "from_c1_calibration_data": {
            "delivers": "historical calibration observation set + contract document",
            "handoff": "config/dynamic_weekly_mc_v3/experimental/baxter_data_contract.json",
            "contract_fields_to_fill": [
                "observations.path",
                "observations.format",
                "observations.dataset_id",
                "observations.sha256",
                "split_policy",
                "hfa.points / hfa.source",
            ],
            "supported_formats": list(SUPPORTED_DATASET_FORMATS),
            "column_allowlist": list(CALIBRATION_OBSERVATION_COLUMNS),
            "required_columns": list(REQUIRED_OBSERVATION_COLUMNS),
            "c2_additional_expectations": dict(C2_ADDITIONAL_EXPECTATIONS),
            "venue_values": list(VENUES),
            "row_orientation": (
                "Directed and team-relative: one row per (game, subject team), with "
                "actual_margin signed from the subject team's point of view. Both directed "
                "rows of a game may be supplied; supplying one means only that side's rating "
                "moves that week."
            ),
            "refused_signals": {
                "patterns": list(FORBIDDEN_SIGNAL_PATTERNS),
                "reason": (
                    "Public betting flow is never belief evidence and injury effects remain "
                    "deferred. Matched as substrings, so renaming does not admit them."
                ),
            },
            "split_policy_modes": list(SUPPORTED_SPLIT_MODES),
            "refused_split_policy_modes": list(REFUSED_SPLIT_MODES),
            "split_rules": [
                "Every observation lands in exactly one of " + ", ".join(DATA_SPLITS) + ".",
                "Splits are blocks of whole (season, week) keys in strictly increasing time "
                "order; a week may not straddle a split boundary.",
                "Holdout is scored only in a single-regime confirmation run.",
            ],
            "hfa_sources": [HFA_SOURCE_V3_CONFIG, HFA_SOURCE_LITERAL],
            "on_absence": (
                "If no observation set is mounted the harness returns READY_FOR_DATA with no "
                "metrics. It does not synthesise observations."
            ),
        },
        "from_c3_colley_srs": {
            "delivers": "independent witness ratings, reported beside the primary criterion",
            "handoff": "contract 'witnesses' object, one path per witness",
            "witnesses": list(INDEPENDENT_WITNESSES),
            "consumption": (
                "C2 reports witness mount status and never blends a witness into the primary "
                "criterion. Any attempt to score a weighted composite is refused by "
                "calibration.reject_witness_composite; ACC-EXT-12 records the blend as "
                "PROPOSAL ONLY / NOT ADOPTED."
            ),
            "blocking": False,
            "note": (
                "Witness absence never blocks a Baxter RMSE evaluation; it is reported as "
                "NOT_MOUNTED."
            ),
        },
        "metric_definitions": {
            definition_id: definition.as_dict()
            for definition_id, definition in sorted(BAXTER_RMSE_DEFINITIONS.items())
        },
        "outputs": {
            "statuses": ["READY_FOR_DATA", "BLOCKED", "EVALUATED"],
            "ranking_basis": "validation",
            "holdout_use": "single-regime confirmation only",
            "promotion": {
                "auto_promotion": False,
                "gate": (
                    "ncaaf_engine.simulation.dynamic_weekly_mc_v3.calibration.promote_regime_r2"
                ),
                "synthetic_evidence_admissible": False,
            },
            "determinism": (
                "Run identity (run_id, as_of, versions, seed) is caller-supplied. No wall "
                "clock, no RNG; identical inputs produce byte-identical payloads."
            ),
        },
        "c2_does_not": [
            "author candidate calibration values",
            "write canonical V3 configuration",
            "promote a regime, including the top-ranked one",
            "run the 10,000-path Monte Carlo",
            "produce final probabilities",
            "admit public-money or injury signals",
        ],
    }
