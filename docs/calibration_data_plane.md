# Historical Calibration Data Plane (Lane C1)

Module: `src/ncaaf_engine/simulation/dynamic_weekly_mc_v3/calibration_data.py`
Tests: `tests/dynamic_weekly_mc_v3/test_calibration_data_plane.py`
Manifest: `reference/dynamic_weekly_mc_v3/MISSING_CALIBRATION_EVIDENCE.json`

## Finding

**No mounted artifact carries game-level historical observations.** Every historical-source
candidate in the repository falls into one of five classes, and none of them is an observation:

| Class | Artifacts | Why it is not an observation set |
|---|---|---|
| `FORWARD_LOOKING_FIXTURES` | Schedule v5, Playoff Calendar | 743 fixtures for the **unplayed** 2026 season; no score column exists |
| `DERIVED_PRIOR_SEASON_RATINGS` | Unified Preseason Power Ratings | `2025 Baxter Ridge Rating` is a season aggregate **fitted from** 2025 games that are not mounted |
| `SIMULATED_ENGINE_OUTPUT` | V2.1 Static Control, Model Parameters `CALIBRATION` sheet | 10,000 simulated paths and prior-run achieved metrics — engine behaviour, not evidence |
| `IDENTITY_*` / `*_STRUCTURE` | Canonical Master, POWER_CRUNCH, Bracket Regime, AAC divisions | identity and structure; carry no game rows |
| `MARKET_FLOW_SNAPSHOT` | `examples/week1_sample_seed.json` | 2026 Week 1 lines — FLOW, excluded from BELIEF calibration by doctrine |

The gap is quantified rather than described. `2025 Baxter Games` sums to **1,514 team-game
sides** across 119 teams with a fitted rating, implying **at least 757 games** whose per-game
record is absent. Mounted per-game rows: **0**.

## What the module provides

Deterministic plumbing, complete and tested, so that mounting a real set is a data step:

- **Inventory** — `inventory_historical_sources()` hashes every candidate and records its class,
  which governed columns it can partially supply, and whether it is admissible for belief.
- **Schema binding** — `MISSION_FIELD_TO_GOVERNED_COLUMN` maps each lane field onto an existing
  column in the governed allowlist. The allowlist is **not** widened: every required field
  already had a governed name.
- **Loaders** — CSV/TSV/JSON, format-aware and fail-closed, delegating admissibility to
  `calibration.register_dataset` before parsing a single row.
- **Normalization** — UTC-aware timestamps only (a naive timestamp cannot be ordered against
  another source's), typed numerics, closed vocabularies for site and result.
- **Checks** — identity (exact canonical `schedule_id`, never a near-match), chronology
  (`event_time → observed_at → recorded_at`, weeks rising with time), duplicates (repeated
  `game_id`, and both-perspective mirrors of one fixture), leakage (`prior_rating_state` dated
  after kickoff; unstamped state reported as *unverifiable*, not assumed clean), split
  separation.
- **Split** — chronological and deterministic, ordered by `(event_time, game_id)`. No seed, no
  clock. A hashed split would let week 14 train a model evaluated on week 3 while looking
  neutral.

## What it deliberately does not do

- **No split authority.** `SplitPolicy` carries `status = NOT_GOVERNED_PENDING_RULING`. Ruling
  R2-CAL-OBJECTIVE names the three split *names*, not a method; the 60/20/20 chronological
  default is deterministic engineering, not governance.
- **No synthetic evidence.** Test rows are stamped `TEST_FIXTURE::` in `source_provenance`, and
  `assert_not_test_fixture()` refuses any stamped set presented as governed evidence.
- **No blocker retirement.** All nine live blockers stand, seven of them calibration. Working
  plumbing is not evidence that exists.
- **No coefficients.** The six canonical calibration values remain `null`; the experimental
  regime file still ships with zero regimes.

## Clearing the block

1. Mount a governed game-level observation set at the path named in the manifest, carrying every
   required column with per-row source artifact provenance and hashes.
2. Obtain a ruling fixing the train/validation/holdout split policy.
3. Run the experimental harness against the primary criterion of ruling R2-CAL-OBJECTIVE
   (out-of-sample Baxter Rating RMSE, minimised), reporting Colley and SRS independently.
4. Promote only by explicit human approval token under a named authority.
