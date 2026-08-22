"""Micro-benchmark for the V3 calibration orchestrator. Measures time, nothing else.

This runs the real scorer over a synthetic corpus of realistic shape so that a
shard count can be chosen before governed inputs arrive. It is a timing
instrument: :mod:`calibration_fixture` refuses to be mounted as a governed
source, the fixture authority is refused by :func:`require_governed_structure`,
and no number this prints is evidence about any parameter.

Wall-time projections assume workers are separate processes on distinct cores and
that per-worker throughput does not degrade with concurrency. Both stop being
true past the machine's physical core count, which is why the report names the
core count alongside the projection rather than extrapolating past it silently.

Run:

    python scripts/benchmark_calibration_search.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import (  # noqa: E402
    calibration_fixture as fixture,
)
from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import (  # noqa: E402
    calibration_scoring as scoring,
)
from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import (  # noqa: E402
    calibration_search as search,
)

#: Shaped after the corpus the historical lane reports in progress: roughly 2,200
#: observations across four seasons of a full FBS-sized field. Not that corpus,
#: and not a claim about it — a stand-in of the same size, so the timing scales.
BENCHMARK_SEASONS = (2021, 2022, 2023, 2024)
BENCHMARK_TEAMS = 134
BENCHMARK_WEEKS = 8

#: How many candidates to time. Large enough to average out per-candidate noise,
#: small enough that the benchmark is not itself a search.
BENCHMARK_CANDIDATES = 48


def main() -> int:
    observations = fixture.fixture_observations(
        seasons=BENCHMARK_SEASONS,
        team_count=BENCHMARK_TEAMS,
        weeks=BENCHMARK_WEEKS,
    )
    authority = fixture.fixture_authority()
    space = search.coarse_space()
    universe = space.enumerate()

    # Sample across the universe rather than off the front of it: the first
    # candidates all carry the smallest coefficient, whose caps never bind and
    # whose update path is the cheapest one available.
    stride = max(1, len(universe) // BENCHMARK_CANDIDATES)
    sample = universe[::stride][:BENCHMARK_CANDIDATES]

    witness_start = time.perf_counter()
    witnesses = scoring.compute_witnesses(
        [r for r in observations.ordered_rows if r.normalized_split == "validation"]
    )
    witness_seconds = time.perf_counter() - witness_start

    # Warm the interpreter on one candidate so first-call overhead is not billed
    # to the sample.
    scoring.score_candidate(sample[0], observations, authority, witnesses=witnesses)

    start = time.perf_counter()
    for candidate in sample:
        scoring.score_candidate(candidate, observations, authority, witnesses=witnesses)
    elapsed = time.perf_counter() - start

    games = len(observations.rows)
    per_candidate = elapsed / len(sample)
    candidates_per_minute = 60.0 / per_candidate
    games_per_second = games / per_candidate

    cores = os.cpu_count() or 1
    serial_seconds = per_candidate * len(universe)
    projections = {}
    for workers in search.SUPPORTED_SHARD_COUNTS:
        shards = [
            len(search.shard_candidates(universe, workers, index))
            for index in range(workers)
        ]
        # Wall time is the slowest shard plus that worker's one-off witness solve,
        # not the mean: the aggregation cannot start until the last shard lands.
        slowest = max(shards)
        projections[str(workers)] = {
            "workers": workers,
            "largest_shard_candidates": slowest,
            "projected_wall_seconds": slowest * per_candidate + witness_seconds,
            "projected_wall_minutes": (slowest * per_candidate + witness_seconds) / 60.0,
            "speedup_vs_1_worker": serial_seconds / (slowest * per_candidate)
            if slowest
            else None,
            "exceeds_physical_cores": workers > cores,
        }

    sensible = [
        w for w in search.SUPPORTED_SHARD_COUNTS if not projections[str(w)]["exceeds_physical_cores"]
    ]
    report = {
        "benchmark_id": "V3-CAL-ORCHESTRATOR-MICROBENCH-001",
        "status": "TIMING_ONLY_NON_PROMOTING",
        "corpus": {
            "provenance": observations.provenance,
            "observations": games,
            "seasons": list(BENCHMARK_SEASONS),
            "teams": BENCHMARK_TEAMS,
            "split_counts": observations.split_counts(),
            "admissible_as_governed_source": False,
        },
        "authority": authority.as_dict(),
        "universe": {
            "space_id": space.space_id,
            "config_sha": space.config_sha,
            "candidate_count": len(universe),
        },
        "measurement": {
            "candidates_timed": len(sample),
            "elapsed_seconds": elapsed,
            "seconds_per_candidate": per_candidate,
            "milliseconds_per_candidate": per_candidate * 1000.0,
            "games_per_second": games_per_second,
            "candidates_per_minute": candidates_per_minute,
            "witness_solve_seconds_once_per_shard": witness_seconds,
        },
        "projected_wall_time": projections,
        "machine": {"cpu_count": cores},
        "fastest_sensible_shard_count": max(sensible) if sensible else 1,
        "fastest_sensible_shard_count_reason": (
            "Largest supported shard count that does not exceed the machine's logical "
            "core count. Beyond that, shards contend for the same cores and the "
            "projection above stops being an upper bound on speedup."
        ),
        "parameters_promoted": 0,
        "real_calibration_executed": False,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
