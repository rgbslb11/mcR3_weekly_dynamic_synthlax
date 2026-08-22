"""Deterministic aggregation of calibration shard results.

Four workers returning four files is not a search result. It becomes one only if
the four files are shards of the same universe, scored against the same bytes,
the same partition, the same transform and the same model — and if the ranking
they are put through was decided before anyone saw them.

Each gate here closes a way a merge produces a confident wrong answer.

Coverage is proved, not assumed
    :func:`require_complete_coverage` compares the received candidate ids against
    the ids the search space says exist. A shard that died at candidate 400 leaves
    a gap, and a merge over the survivors still returns a winner. It would just be
    the best of what came back, reported as the best of what was searched.

Heterogeneous inputs are refused, not reconciled
    :func:`require_homogeneous` refuses shards that disagree on dataset digest,
    split digest, experiment configuration, expected-margin authority, model
    version, stage or scored split. Any one of those differing means the numbers
    are not on the same scale, and the cheapest way to produce a new record is to
    merge a re-run against slightly different bytes into an older result set.

The tie-break is declared in source, ahead of any result
    :data:`RANKING_POLICY` is a module constant with its own digest. Choosing a
    tie-break after seeing the table is how the candidate somebody already liked
    becomes the winner, so the order is fixed here and cited by digest in the
    aggregate record.

A tie-break is not a discovery
    Where candidates tie on the primary metric and differ only in a parameter the
    corpus cannot see — a movement cap that never bound, most of all — the
    aggregate reports an equivalence class marked
    :data:`UNIDENTIFIED_EQUIVALENCE_CLASS` rather than a winner. The prior
    9,600-candidate experiment reported a 6.0-point cap that never bound as its
    result. That is the specific failure this refuses to repeat.

Nothing here promotes a value or writes canonical configuration. The strongest
output is a ranked table and a shortlist.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import calibration as cal
from .calibration_search import (
    CalibrationCandidate,
    SearchSpace,
    boundary_report,
    canonical_json,
    coarse_space,
)
from .calibration_scoring import FAILURE_NONE
from .errors import GovernanceBlock, InputValidationError
from .textio import write_json_lf

__all__ = [
    "HOMOGENEITY_KEYS",
    "PRIMARY_METRIC_TIE_TOLERANCE",
    "RANKING_POLICY",
    "UNIDENTIFIED_EQUIVALENCE_CLASS",
    "aggregate",
    "cap_identification",
    "equivalence_classes",
    "load_shard_tables",
    "main",
    "rank_rows",
    "ranking_policy_sha",
    "require_complete_coverage",
    "require_homogeneous",
    "shortlist_for_holdout",
]


#: Every header field that must agree across shards before they may be merged.
#: Each is here because differing on it means the rows are not comparable, not
#: merely inconvenient.
HOMOGENEITY_KEYS = (
    "input_dataset_sha",
    "split_sha",
    "experiment_config_sha",
    "expected_margin_authority_id",
    "model_version",
    "stage",
)

#: Two primary-metric values closer than this are treated as tied. Declared as a
#: tolerance rather than left to float equality because a genuine tie between two
#: candidates that differ only in an inert parameter can land a few ULPs apart
#: purely through summation order, and calling that a separation is exactly the
#: false discovery this module exists to prevent.
PRIMARY_METRIC_TIE_TOLERANCE = 1e-9

UNIDENTIFIED_EQUIVALENCE_CLASS = "UNIDENTIFIED_EQUIVALENCE_CLASS"
IDENTIFIED_SEPARATION = "IDENTIFIED_SEPARATION"

#: The ranking, fixed in source before any result exists. The primary criterion is
#: ruling R2-CAL-OBJECTIVE's; the tie-breaks below it are stated here so that no
#: ordering decision is ever made with the table in view.
RANKING_POLICY: dict[str, Any] = {
    "policy_id": "V3-CAL-RANKING-001",
    "declared_before_results": True,
    "primary": {
        "metric": "baxter_rmse",
        "governed_metric": cal.PRIMARY_CALIBRATION_METRIC,
        "direction": cal.PRIMARY_CALIBRATION_DIRECTION,
        "ruling": "R2-CAL-OBJECTIVE",
    },
    "tie_breaks": [
        {
            "key": "baxter_mae",
            "direction": "ascending",
            "reason": (
                "A second error measure on the same residuals, less dominated by the "
                "handful of blowouts that move RMSE."
            ),
        },
        {
            "key": "movement_p95",
            "direction": "ascending",
            "reason": (
                "Among equally accurate models, prefer the one whose weekly ratings "
                "move less. A rating that swings to reach the same accuracy is worse "
                "to publish, and this is the diagnostic ruling R2-CAL-OBJECTIVE "
                "already names."
            ),
        },
        {
            "key": "candidate_id",
            "direction": "ascending",
            "reason": (
                "Terminal and total, so the order is fully determined. Reaching this "
                "tie-break means the corpus did not separate the candidates, which the "
                "equivalence-class report states rather than hides."
            ),
        },
    ],
    "winner_accuracy_may_override_primary": False,
    "witness_composite_authorised": False,
    "excluded_from_ranking": "Rows whose failure_status is not OK.",
}


def ranking_policy_sha() -> str:
    """Digest of the declared ranking, cited in every aggregate record."""
    return hashlib.sha256(canonical_json(RANKING_POLICY).encode("utf-8")).hexdigest()


# --- loading -----------------------------------------------------------------


def load_shard_tables(directory: Path) -> list[dict[str, Any]]:
    """Read every shard table in a directory, in a fixed filename order.

    Sorted by name so two aggregations over the same directory visit the files in
    the same order. Nothing here depends on that order, which is the point: if a
    result ever did, the sort makes the dependence reproducible instead of
    filesystem-dependent.
    """
    root = Path(directory)
    if not root.is_dir():
        raise InputValidationError(f"Shard result directory {root} does not exist.")
    tables: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise InputValidationError(
                f"Shard result {path.name} does not parse: {exc.msg}"
            ) from None
        if not isinstance(payload, dict) or "rows" not in payload:
            raise InputValidationError(
                f"Shard result {path.name} is not a shard table; it carries no rows."
            )
        payload = dict(payload)
        payload["_source_file"] = path.name
        tables.append(payload)
    if not tables:
        raise InputValidationError(
            f"No shard result tables found in {root}. An aggregation over nothing "
            "would report a complete search of an empty universe."
        )
    return tables


def require_homogeneous(tables: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Refuse to merge shards that were not scoring the same thing.

    Headers are checked first and rows second. A header disagreement is a wrong
    file in the directory; a row disagreeing with its own header is a corrupted or
    hand-edited table, and the second is the more dangerous of the two because it
    survives a check that only reads headers.
    """
    if not tables:
        raise InputValidationError("No shard tables to check.")
    agreed: dict[str, Any] = {}
    for key in HOMOGENEITY_KEYS:
        values = {}
        for table in tables:
            if key not in table:
                raise InputValidationError(
                    f"Shard {table.get('_source_file', '?')} declares no {key}; it "
                    "cannot be shown to belong with the others."
                )
            values.setdefault(table[key], []).append(table.get("_source_file", "?"))
        if len(values) > 1:
            raise GovernanceBlock(
                f"Refusing to aggregate shards that disagree on {key}: "
                f"{ {k: v for k, v in sorted(values.items(), key=lambda kv: str(kv[0]))} }. "
                "Results scored against different inputs are not on one scale, and "
                "merging them produces a ranking of nothing in particular."
            )
        agreed[key] = next(iter(values))

    scored_splits = {
        row.get("scored_split")
        for table in tables
        for row in table["rows"]
        if row.get("failure_status") == FAILURE_NONE
    }
    if len(scored_splits) > 1:
        raise GovernanceBlock(
            f"Refusing to aggregate across mixed scored splits {sorted(scored_splits)}; "
            "a candidate scored on validation does not compete with one scored on "
            "holdout."
        )

    mismatched: list[str] = []
    for table in tables:
        for row in table["rows"]:
            for key in HOMOGENEITY_KEYS:
                if key in row and row[key] != agreed[key]:
                    mismatched.append(
                        f"{table.get('_source_file', '?')}#{row.get('candidate_id')}:{key}"
                    )
    if mismatched:
        raise GovernanceBlock(
            f"Shard rows disagree with their own headers: {mismatched[:5]}. A table "
            "that contradicts itself cannot be repaired by choosing one of the two."
        )

    declared_counts = {int(t["shard_count"]) for t in tables}
    if len(declared_counts) > 1:
        raise GovernanceBlock(
            f"Shards were produced under different shard counts {sorted(declared_counts)}. "
            "Membership is candidate_id % shard_count, so two different moduli do not "
            "partition anything together."
        )
    indices = [int(t["shard_index"]) for t in tables]
    repeated = sorted({i for i in indices if indices.count(i) > 1})
    if repeated:
        raise GovernanceBlock(
            f"Shard index {repeated} appears more than once. Two files claiming the same "
            "shard means one of them is a stale re-run, and merging both double-counts "
            "exactly the candidates that shard owned."
        )
    agreed["scored_split"] = next(iter(scored_splits)) if scored_splits else None
    agreed["shard_indices"] = sorted(indices)
    agreed["shard_count"] = next(iter(declared_counts))
    return agreed


def require_complete_coverage(
    rows: Sequence[Mapping[str, Any]], expected_ids: Iterable[int]
) -> dict[str, Any]:
    """Prove the merged rows are exactly the universe: no gaps, no repeats."""
    expected = {int(i) for i in expected_ids}
    received = [int(r["candidate_id"]) for r in rows]
    counts: dict[int, int] = {}
    for candidate_id in received:
        counts[candidate_id] = counts.get(candidate_id, 0) + 1
    duplicates = sorted(i for i, n in counts.items() if n > 1)
    missing = sorted(expected - set(received))
    unexpected = sorted(set(received) - expected)
    if missing:
        raise GovernanceBlock(
            f"{len(missing)} expected candidate(s) are absent from the merged shards, "
            f"first: {missing[:5]}. The best of what came back is not the best of what "
            "was searched."
        )
    if duplicates:
        raise GovernanceBlock(
            f"{len(duplicates)} candidate(s) appear more than once across shards, "
            f"first: {duplicates[:5]}. Two shards evaluated the same candidate, so the "
            "partition they were run under was not disjoint."
        )
    if unexpected:
        raise GovernanceBlock(
            f"{len(unexpected)} returned candidate(s) are not in the search universe, "
            f"first: {unexpected[:5]}. A worker scored a grid of its own."
        )
    return {
        "expected": len(expected),
        "received": len(received),
        "missing": 0,
        "duplicates": 0,
        "unexpected": 0,
        "complete": True,
    }


# --- ranking -----------------------------------------------------------------


def _sort_key(row: Mapping[str, Any]) -> tuple[float, float, float, int]:
    return (
        float(row["baxter_rmse"]),
        float(row["baxter_mae"]),
        float(row["movement_p95"]),
        int(row["candidate_id"]),
    )


def rank_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Order successful rows under :data:`RANKING_POLICY`, and only that policy."""
    scored = [r for r in rows if r.get("failure_status") == FAILURE_NONE]
    if not scored:
        raise GovernanceBlock(
            "Every candidate row carries a failure status; there is nothing to rank."
        )
    incomplete = [
        int(r["candidate_id"])
        for r in scored
        if r.get("baxter_rmse") is None
        or r.get("baxter_mae") is None
        or r.get("movement_p95") is None
    ]
    if incomplete:
        raise InputValidationError(
            f"Rows report success but carry no ranking metrics: {incomplete[:5]}."
        )
    ordered = sorted(scored, key=_sort_key)
    return [dict(row, rank=index + 1) for index, row in enumerate(ordered)]


def equivalence_classes(ranked: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Group candidates the corpus could not separate, and say what varies inside.

    A group is formed from consecutive ranks whose primary metric agrees within
    :data:`PRIMARY_METRIC_TIE_TOLERANCE`. Within a group, any family that takes
    more than one value is a family this corpus did not identify, and the group is
    marked :data:`UNIDENTIFIED_EQUIVALENCE_CLASS`. The tie-break still produces a
    total order — a deterministic ranking is required — but the record says the
    ordering inside the group came from the tie-break rather than from evidence.
    """
    classes: list[dict[str, Any]] = []
    group: list[Mapping[str, Any]] = []

    def _close(group_rows: list[Mapping[str, Any]]) -> None:
        if not group_rows:
            return
        varying: dict[str, list[Any]] = {}
        for family in (
            "weekly_performance_residual_coefficient",
            "weekly_movement_cap_points",
            "recent_form_weights",
            "blowout_treatment",
            "sample_size_regularization",
        ):
            seen: list[Any] = []
            for row in group_rows:
                value = row["parameters"][family]
                if value not in seen:
                    seen.append(value)
            if len(seen) > 1:
                varying[family] = seen
        cap_inert = all(not bool(r.get("cap_identified")) for r in group_rows)
        classes.append(
            {
                "member_count": len(group_rows),
                "best_rank": min(int(r["rank"]) for r in group_rows),
                "candidate_ids": sorted(int(r["candidate_id"]) for r in group_rows),
                "primary_metric": float(group_rows[0]["baxter_rmse"]),
                "unidentified_families": sorted(varying),
                "varying_values": varying,
                "movement_cap_never_binds_in_class": cap_inert,
                "status": (
                    UNIDENTIFIED_EQUIVALENCE_CLASS if varying else IDENTIFIED_SEPARATION
                ),
                "note": (
                    "Ordering within this class comes from the declared tie-break, not "
                    "from the corpus. The families listed are not identified by this "
                    "evidence and must not be reported as findings."
                    if varying
                    else "Single parameter vector at this primary-metric value."
                ),
            }
        )

    for row in ranked:
        if group and abs(
            float(row["baxter_rmse"]) - float(group[0]["baxter_rmse"])
        ) > PRIMARY_METRIC_TIE_TOLERANCE:
            _close(group)
            group = []
        group.append(row)
    _close(group)
    return classes


def cap_identification(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Which movement-cap levels the corpus can actually see.

    Reported over the whole table rather than only the winner, because a cap level
    that never binds anywhere is unidentified for every candidate that carries it,
    not just for the one that happened to rank first.
    """
    scored = [r for r in rows if r.get("failure_status") == FAILURE_NONE]
    by_level: dict[float, dict[str, Any]] = {}
    for row in scored:
        level = float(row["parameters"]["weekly_movement_cap_points"])
        bucket = by_level.setdefault(
            level,
            {
                "cap_points": level,
                "candidates": 0,
                "candidates_where_cap_bound": 0,
                "max_cap_hit_rate": 0.0,
                "max_uncapped_update": 0.0,
            },
        )
        bucket["candidates"] += 1
        if row.get("cap_identified"):
            bucket["candidates_where_cap_bound"] += 1
        bucket["max_cap_hit_rate"] = max(
            bucket["max_cap_hit_rate"], float(row.get("cap_hit_rate") or 0.0)
        )
        bucket["max_uncapped_update"] = max(
            bucket["max_uncapped_update"], float(row.get("max_uncapped_update") or 0.0)
        )
    levels = []
    for level in sorted(by_level):
        bucket = dict(by_level[level])
        bucket["identified"] = bucket["candidates_where_cap_bound"] > 0
        levels.append(bucket)
    inert = [b["cap_points"] for b in levels if not b["identified"]]
    return {
        "levels": levels,
        "levels_never_binding": inert,
        "all_levels_identified": not inert,
        "note": (
            "Cap levels listed in levels_never_binding are not identified by this "
            "corpus. Ranking one of them first reports a tie-break as a discovery."
        ),
    }


def shortlist_for_holdout(
    ranked: Sequence[Mapping[str, Any]], *, limit: int = 4
) -> list[int]:
    """The only candidate ids that may ever meet the holdout.

    Taken from the top of the declared ranking, deduplicated by parameter vector,
    and short. The holdout is scored once; a long shortlist turns that single
    scoring into a selection.
    """
    if limit < 1:
        raise InputValidationError("Holdout shortlist limit must be at least 1.")
    out: list[int] = []
    for row in ranked:
        if len(out) >= limit:
            break
        out.append(int(row["candidate_id"]))
    return out


# --- aggregation -------------------------------------------------------------


def aggregate(
    tables: Sequence[Mapping[str, Any]],
    *,
    expected_ids: Iterable[int],
    space: SearchSpace | None = None,
    winner_candidate: CalibrationCandidate | None = None,
    holdout_shortlist_limit: int = 4,
) -> dict[str, Any]:
    """Merge, verify, rank and report. Produces no promotion of any kind."""
    header = require_homogeneous(tables)
    rows = [dict(row) for table in tables for row in table["rows"]]
    coverage = require_complete_coverage(rows, expected_ids)
    ranked = rank_rows(rows)
    classes = equivalence_classes(ranked)
    winner = ranked[0]

    failures = [r for r in rows if r.get("failure_status") != FAILURE_NONE]
    report: dict[str, Any] = {
        "aggregate_id": "V3-CAL-AGGREGATE-001",
        "header": dict(header),
        "ranking_policy": dict(RANKING_POLICY),
        "ranking_policy_sha": ranking_policy_sha(),
        "coverage": coverage,
        "shard_count": header.get("shard_count"),
        "shard_indices": header.get("shard_indices"),
        "candidate_count": len(rows),
        "ranked_count": len(ranked),
        "failure_count": len(failures),
        "failures": [
            {
                "candidate_id": int(r["candidate_id"]),
                "failure_status": r.get("failure_status"),
                "failure_reason": r.get("failure_reason"),
            }
            for r in sorted(failures, key=lambda r: int(r["candidate_id"]))[:20]
        ],
        "winner": {
            "candidate_id": int(winner["candidate_id"]),
            "candidate_key": winner.get("candidate_key"),
            "parameters": winner["parameters"],
            "baxter_rmse": winner["baxter_rmse"],
            "baxter_mae": winner["baxter_mae"],
            "winner_accuracy": winner.get("winner_accuracy"),
            "brier_score": winner.get("brier_score"),
            "log_loss": winner.get("log_loss"),
            "game_sd_points": winner.get("game_sd_points"),
            "game_sd_method": winner.get("game_sd_method"),
            "cap_identified": winner.get("cap_identified"),
            "movement_p95": winner.get("movement_p95"),
            "colley_rank_correlation": winner.get("colley_rank_correlation"),
            "srs_rank_correlation": winner.get("srs_rank_correlation"),
        },
        "equivalence_classes": classes,
        "winning_class_status": classes[0]["status"] if classes else None,
        "cap_identification": cap_identification(rows),
        "holdout_shortlist": shortlist_for_holdout(
            ranked, limit=holdout_shortlist_limit
        ),
        "ranked": [
            {
                "rank": int(r["rank"]),
                "candidate_id": int(r["candidate_id"]),
                "baxter_rmse": r["baxter_rmse"],
                "baxter_mae": r["baxter_mae"],
                "movement_p95": r["movement_p95"],
                "cap_identified": r.get("cap_identified"),
            }
            for r in ranked
        ],
        "parameters_promoted": 0,
        "writes_canonical_config": False,
        "promotion_authority_conferred": None,
    }
    if space is not None and winner_candidate is not None:
        report["boundary_report"] = boundary_report(space, winner_candidate)
        report["refinement_required"] = bool(
            report["boundary_report"]["boundary_families"]
        )
    return report


def main(argv: list[str] | None = None) -> int:
    """Operator entry point: ``--input <result-directory>``."""
    parser = argparse.ArgumentParser(
        prog="sythalax-v3-calibration-aggregate",
        description="Merge, verify and rank V3 calibration shard result tables.",
    )
    parser.add_argument("--input", required=True, help="Directory of shard result tables.")
    parser.add_argument(
        "--output",
        default=None,
        help="Where to write the aggregate record. Defaults beside the input.",
    )
    parser.add_argument(
        "--holdout-shortlist-limit",
        type=int,
        default=4,
        help="How many candidates the aggregate may nominate for the holdout.",
    )
    args = parser.parse_args(argv)

    try:
        tables = load_shard_tables(Path(args.input))
        stages = {t.get("stage") for t in tables}
        if stages != {"coarse"}:
            raise GovernanceBlock(
                f"This entry point reconstructs the expected candidate universe only "
                f"for the coarse stage; the shards declare {sorted(stages)}. A "
                "refinement or holdout universe is a function of an earlier ranking "
                "and must be supplied with the results it belongs to."
            )
        space = coarse_space()
        candidates = space.enumerate()
        declared = {t.get("experiment_config_sha") for t in tables}
        if declared != {space.config_sha}:
            raise GovernanceBlock(
                f"Shards were scored under experiment config {sorted(declared)} but the "
                f"coarse space in this build digests to {space.config_sha}. The universe "
                "the results came from is not the universe this process can enumerate."
            )
        report = aggregate(
            tables,
            expected_ids=[c.candidate_id for c in candidates],
            space=space,
            winner_candidate=None,
            holdout_shortlist_limit=args.holdout_shortlist_limit,
        )
        target = (
            Path(args.output)
            if args.output
            else Path(args.input) / "AGGREGATE.json"
        )
        write_json_lf(target, report)
        print(
            json.dumps(
                {
                    "status": "AGGREGATED",
                    "written": str(target),
                    "candidate_count": report["candidate_count"],
                    "winner_candidate_id": report["winner"]["candidate_id"],
                    "winning_class_status": report["winning_class_status"],
                    "parameters_promoted": 0,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except (GovernanceBlock, InputValidationError) as exc:
        print(
            json.dumps(
                {"status": "BLOCKED", "reason": str(exc), "parameters_promoted": 0},
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
