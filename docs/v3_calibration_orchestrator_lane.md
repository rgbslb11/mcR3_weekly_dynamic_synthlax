# OPERATION SYTHALAX — Calibration Orchestrator Lane

## Deterministic parallel search harness for the six V3 calibration families

Branch: `claude/v3-calibration-orchestrator-r1`
Frozen base: `5479f2ae7687c36c0ed4117334171289693dd5c9`
Disposition: **SEARCH MACHINERY COMPLETE — INPUTS NOT MOUNTED**

Machine-readable record: `reference/dynamic_weekly_mc_v3/V3_CALIBRATION_ORCHESTRATOR_R1.json`,
emitted deterministically by `calibration_orchestrator.write_orchestrator_record`
and compared byte-for-byte against the committed copy by the test suite.

No parameter was selected or promoted, no canonical writer was built, no blocker
was retired, no allowlist was widened, and no season Monte Carlo was run.

---

## 1. The short version

The remaining calibration work was a serial reasoning task: think about a
coefficient, argue about a cap, repeat. This lane converts it into a compute
task that four or eight workers can execute without talking to each other.

What exists now is the whole path from *approved inputs* to *recommended
parameter package* — candidate universe, shards, scorer, metrics, aggregation,
coarse winners, local refinement, sealed holdout — with every step deterministic
and every identification defect of the prior experiment reported rather than
repeated.

What does not exist is the inputs. A governed observation corpus and a settled
expected-margin authority are both absent, and every path that would score
against them fails closed. The coarse grid enumerates, shards and benchmarks
today; it refuses to produce a citable number.

The compute estimate is the mildly surprising part. The full coarse universe of
2,160 candidates over a 2,144-game corpus takes **30 seconds on one worker** and
**4 seconds on eight**. Compute was never the bottleneck. Governance was, and
still is.

---

## 2. What was built

| Module | Role |
| --- | --- |
| `calibration_search.py` | Candidate universe, content-addressed ids, sharding, staged plan, holdout custody |
| `calibration_scoring.py` | Temporal walk-forward scorer, metrics, `game_sd_points`, shard output |
| `calibration_aggregate.py` | Shard merge, coverage and homogeneity proofs, declared ranking |
| `calibration_orchestrator.py` | Lane facade: readiness, operator interface, machine-readable record |
| `colley.py` | Colley Matrix witness (SRS witness already existed in `srs.py`) |
| `calibration_fixture.py` | Synthetic non-promoting corpus, for benchmarks and tests only |
| `scripts/benchmark_calibration_search.py` | Timing instrument |

58 tests in `tests/dynamic_weekly_mc_v3/test_calibration_orchestrator.py`.

---

## 3. One universe, defined once

Six families are unresolved. Five of them describe the **mean model** and are
searched:

* `weekly_performance_residual_coefficient`
* `weekly_movement_cap_points`
* `recent_form_weights`
* `blowout_treatment`
* `sample_size_regularization`

The sixth, `game_sd_points`, is **not an axis**. It is a property of the
residuals a mean model leaves behind, so enumerating it would let a candidate
choose the dispersion its own errors are scored against. It is estimated after
selection — section 7.

### Candidate identity

`candidate_id` is the top 63 bits of `SHA-256` over the canonical serialization
of the parameter vector. It is content-addressed rather than ordinal, and that
choice is load-bearing:

> An ordinal index means the same parameter vector is candidate 4,117 in one run
> and 3,902 in the next, because somebody widened an axis. Two shard files from
> either side of that edit then merge without complaint into a table where one
> row's parameters are not the parameters that produced its metrics.

Because the id travels with the meaning, a Stage-1 result table stays joinable to
a Stage-2 table across a widened grid. A test asserts exactly that.

### Sharding

Membership is `candidate_id % shard_count == shard_index`. Pure arithmetic, no
coordination. Shard counts 1, 2, 4 and 8 are supported and each is *proved*
rather than asserted:

| Shards | Largest shard | Missing | Duplicates |
| --- | --- | --- | --- |
| 1 | 2,160 | 0 | 0 |
| 2 | 1,087 | 0 | 0 |
| 4 | 552 | 0 | 0 |
| 8 | 281 | 0 | 0 |

The digest-derived id distributes evenly without anybody choosing an ordering,
and keeps distributing evenly when an axis is widened.

A worker is handed a space and checks its `config_sha` against what it was told
to expect. A worker that built a different grid fails at startup rather than
returning a shard of a universe nobody else searched.

### Ranges are PENDING, and pending means refused

Every coarse axis carries `RANGE_PENDING_EVIDENCE`. The levels are scaffolding
chosen to exercise the harness, and `require_range_authority` refuses to score
them until a named authority fixes them.

The grid is deliberately **not** centred on the prior result. `0.18` is not a
coefficient level and `6.0` is not a cap level. That experiment's corpus is
inadmissible, so anchoring on its answer would import the provenance defect as a
prior. It is recorded in `HISTORICAL_RESEARCH_CONTEXT` with
`usable_as_anchor: false` and its three identification defects named.

Two levels exist specifically to be falsified: the 16-point cap is wide enough
that it should never bind, and the deepest recent-form levels sit at the top of
their ladder so a boundary optimum is detectable.

---

## 4. Staged search

**Stage 1 — coarse.** 2,160 candidates. Deliberately coarse: resolving a third
decimal place costs the same compute as covering twice the space, and Stage 2
resolves it anyway over a region Stage 1 has justified. Scored on validation.

**Stage 2 — refinement.** A pure function of the coarse space and the *ordered*
Stage-1 leaders, so two operators handed the same ranking build byte-identical
Stage-2 universes and their shards interlock. Interior leaders are subdivided at
half-step; leaders on an expandable edge are extended one full step past it. The
search grows rather than reporting the edge as an answer.

**Stage 3 — holdout.** An explicit shortlist, capped at 8. `HoldoutLedger`
records the single consumption and refuses the next:

> "No iterative tuning against holdout" cannot be enforced by intent, because the
> second run always has a reason.

Re-opening the holdout requires constructing a new ledger, which is a visible act
rather than a re-run of the same command. Dispersion for the holdout stage is
carried in from validation rather than re-estimated, so the holdout does not
inform its own diagnostics.

---

## 5. The temporal scorer

Every guard here closes a failure mode that leaves no trace in the output. A
leaking scorer does not raise; it returns a better number.

**Chronology is enforced.** Rows are ordered by `(event_time, game_id)`.
Timestamps must be fixed-width ISO-8601 with an explicit offset, and the whole
corpus must use one format — comparing instants as strings is chronological only
within a single width and offset. Week indices must agree with time, or the
rerating boundary would be drawn in the wrong place.

**Promotion is at week boundaries, never per game.** A per-game promotion lets a
team's noon result move the rating that predicts its conference-mate's evening
game, inside a week the model has not finished observing.

**Weeks 1–2 keep opening-strength semantics exactly.** Nothing is promoted before
Week 2 closes. The test asserts this numerically: every Week 1 and Week 2
prediction equals the corpus's own governed expected margin, and Week 3 does not.

**Leakage is proved on the output.** Each `Prediction` carries the
`information_cutoff` — the event time of the last result folded into the state
behind it — and `require_no_future_leakage` proves every cutoff strictly precedes
its own kickoff. Two mutation checks confirmed the guards fire: promoting from
Week 1 and letting the state see the current week both fail the suite.

**Raw and derived are different types.** `ObservationRow` is frozen and never
written to; everything the model learns lives in `TeamCalibrationState`. There is
no field an update could write back into the corpus.

**Season state is re-initialised per season.** Carrying last year's promoted
rating forward would score a model nobody proposed.

---

## 6. Expected-margin input contract

The disputed historical point-axis resolution is **not** implemented here. The
rating-to-margin transform arrives as an `ExpectedMarginAuthority` declaring its
`point_axis_id`, `transform_id`, HFA treatment and status.
`require_governed_authority` refuses anything that is not `GOVERNED`.

`EXPECTED_MARGIN_INPUT_CONTRACT` in `calibration_scoring.py` states, field by
field, what the parallel lane must supply. Two boundaries are strict:

* **A missing expected margin raises.** It never defaults to zero, because a zero
  expected margin is a confident prediction of a tie, not the absence of one.
* **The mounted transform must reproduce the corpus's own governed margins.** The
  corpus was produced by an authority that already applied a transform. If the
  one mounted here disagrees, every residual is measured against a predictor the
  corpus never used, and the search optimises a model of the wrong thing. This is
  checked once, before any compute is spent.

A fixture authority exists for benchmarking. It asserts that a point of strength
is a point of margin — precisely the assumption the governed lane exists to
replace — and it is refused for any run whose results could be cited.

---

## 7. `game_sd_points`

**Admissible:** `OUT_OF_SAMPLE_RESIDUAL_DISPERSION`, taken from validation or
holdout residuals. The training split is refused, because the mean model was
selected to minimise exactly those residuals.

**Refused:** `SD_OF_ACTUAL_MARGIN`. It is implemented and named so the gate has
something concrete to refuse, and so the distinction is testable rather than
asserted. SD of actual margin measures how variable college football is;
`game_sd_points` must measure how wrong the model is. They differ by everything
the model explains — which is the direction of the unexplained legacy 20.2
observation.

**Separation of mean model from dispersion.** Selection is on RMSE, which needs
no dispersion parameter at all. Dispersion enters only to convert a margin into a
win probability for Brier and log loss, and cannot change any prediction. A test
scores one candidate with a wildly wrong dispersion override and asserts RMSE,
MAE and winner accuracy are bit-identical while only the probabilistic
diagnostics move.

Both the RMS about zero and the classical sample SD are reported; the gap between
them is the model's bias, which is worth seeing rather than absorbing.

---

## 8. Identification reporting

The prior experiment's three defects are each answered by a specific report.

**Movement cap.** Every candidate records `cap_hit_count`, `cap_hit_rate`,
`max_uncapped_update`, `max_capped_update` and `cap_identified`. A cap that never
binds is a parameter the data cannot see, and the aggregate lists every cap level
that never bound anywhere. Where candidates tie on the primary metric and differ
only in such a family, the aggregate emits an `UNIDENTIFIED_EQUIVALENCE_CLASS`
naming the varying families rather than a winner. The tie-break still produces a
total order — a deterministic ranking is required — but the record says the
ordering came from the tie-break rather than from evidence.

**Boundary optimum.** `boundary_report` marks every ordered family whose winning
level sits at an edge as `BOUNDARY_OPTIMUM`, reports the recent-form tail mass so
the mark can be read as "the window wants to be wider", and hands it to
`refine_space`, which widens. `blowout_treatment` is excluded from boundary
testing: its levels are shapes, and the edge of an unordered set is an artifact of
the order somebody typed them in.

**Regularization.** Represented as an explicit policy with an id and a parameter.
`report()` emits effective sample count and regularization amount at both an
early-season and a late-season sample size. A shrinkage living in the update step
as `n / (n + 3)` is regularization nobody voted for.

**Recent form.** Depth and decay travel together in one policy because they are
not separable — decay 0.9 over depth 2 and decay 0.5 over depth 8 are nearly one
weighting, and searching them as independent axes reports two findings where
there is one. `effective_contributions` gives the weight each historical update
carries; a window deeper than the available history contributes nothing past it
rather than re-normalizing and quietly behaving like a shallower policy.

**Blowout treatment.** A named, serializable policy that appears in the candidate
id, the shard table and the audit record — not a clip buried in the update step,
which is invisible to all three. All three policies are odd functions, which is
what lets one corpus row update both sides of a game.

---

## 9. Aggregation

`require_homogeneous` refuses shards disagreeing on dataset digest, split digest,
experiment config, expected-margin authority, model version, stage, scored split,
shard count, or shard index. Headers are checked first and rows second — a row
disagreeing with its own header is the more dangerous case, because it survives a
check that only reads headers.

`require_complete_coverage` proves the merged rows are exactly the universe:
missing 0, duplicates 0, unexpected 0. A shard that died at candidate 400 leaves
a gap, and a merge over the survivors still returns a winner — it would just be
the best of what came back, reported as the best of what was searched.

Per-candidate failures become rows rather than exceptions, carrying their own
reason to the aggregator. Whole-run refusals are raised before the loop.

### The ranking, declared in source

`RANKING_POLICY` is a module constant with its own digest, cited in every
aggregate record. Choosing a tie-break after seeing the table is how the
candidate somebody already liked becomes the winner.

1. **`baxter_rmse` ascending** — the governed primary criterion, ruling
   R2-CAL-OBJECTIVE.
2. `baxter_mae` ascending — a second error measure on the same residuals, less
   dominated by the handful of blowouts that move RMSE.
3. `movement_p95` ascending — among equally accurate models, prefer the one whose
   weekly ratings move less.
4. `candidate_id` ascending — terminal and total.

Winner accuracy is reported and may never reorder the table. Colley and SRS are
reported as independent witnesses — Spearman rank correlation against the
candidate's closing ratings over the same span — and are never blended into the
primary criterion, never converted onto the V3 point axis, and never used as a
selection metric. ACC-EXT-12 records that blend as PROPOSAL ONLY / NOT ADOPTED.

---

## 10. Operator interface

Plan and prove a shard without any inputs:

```
python -m ncaaf_engine.simulation.dynamic_weekly_mc_v3.calibration_search \
    --stage coarse --shard-count 4 --shard-index 0 --plan
```

Score a shard, once inputs are governed:

```
python -m ncaaf_engine.simulation.dynamic_weekly_mc_v3.calibration_search \
    --stage coarse --shard-count 4 --shard-index 0 \
    --observations <governed-corpus> \
    --expected-margin-authority <authority-id> \
    --range-authority <ruling-id>
```

Aggregate:

```
python -m ncaaf_engine.simulation.dynamic_weekly_mc_v3.calibration_aggregate \
    --input <result-directory>
```

Four agents run the same command with `--shard-index` 0..3 and the same
`--expect-config-sha`. They need no coordination and cannot overlap.

Only the coarse stage has a standing space definition. Refinement and holdout
universes are functions of an earlier ranking and must be supplied to the worker,
which is the whole point of refusing to let a worker choose a grid.

---

## 11. Compute estimate

Measured by `scripts/benchmark_calibration_search.py` against a 2,144-game
synthetic corpus over 134 teams and four seasons, on a 20-logical-core machine.
Timing only; no result here is evidence about any parameter.

| Metric | Value |
| --- | --- |
| Per candidate | 13.9 ms |
| Games/sec | ~154,000 |
| Candidates/min | ~4,320 |
| Witness solve (once per shard) | 56 ms |

Projected wall time for the full 2,160-candidate coarse stage:

| Workers | Largest shard | Wall time | Speedup |
| --- | --- | --- | --- |
| 1 | 2,160 | 30.0 s | 1.00× |
| 2 | 1,087 | 15.1 s | 1.99× |
| 4 | 552 | 7.7 s | 3.91× |
| 8 | 281 | 4.0 s | 7.69× |

**Fastest sensible shard count on this machine: 8** — the largest supported count
that does not exceed the logical core count.

The honest reading: at this scale the coarse stage is cheap enough that shard
count barely matters, and a single worker finishes in half a minute. Sharding
earns its keep at refinement, where a widened grid around several leaders is a
much larger universe, and as insurance against a corpus an order of magnitude
larger than the one benchmarked. Compute is not what is blocking this program.

---

## 12. What this lane did not do

* No parameter selected, promoted, or written to canonical configuration. The
  six canonical values remain `null` and a test asserts it.
* No canonical writer created. The strongest output is a ranked table.
* No blocker retired. The formal set remains exactly 8; a test asserts that this
  lane added none of its own to it.
* No real calibration executed — the inputs are not there.
* No season Monte Carlo of any size.
* No governed allowlist widened, no ruling encoded, no existing module's contract
  changed. `srs.py` was left untouched; its mirrored-input requirement is met at
  the call site.

---

## 13. Blocked on

Three inputs, none of which this lane can supply:

1. **A governed historical observation corpus**, frozen and audited, registered
   through `calibration_evidence.register_governed_dataset` with an exact
   SHA-256. The parallel corpus lane reports roughly 2,241 admitted observations
   across 2021–2024; those numbers are not treated as governed here and the
   orchestrator is designed to accept an exact digest later, with no coupling to
   that worktree.

2. **A settled expected-margin authority** — the disputed point-axis resolution —
   supplied as an `ExpectedMarginAuthority` with status `GOVERNED`, naming its
   axis and its rating-to-margin transform.

3. **A search range authority**: a named ruling that fixes each pending axis,
   flipping its evidence status to `RANGE_FIXED_BY_NAMED_AUTHORITY`.

When those three land, the sequence is: fix the ranges, run four shards of Stage
1, aggregate, refine around the leaders, run Stage 2, shortlist at most eight,
open the holdout ledger once. Roughly a minute of compute, and every number it
produces carries its own provenance.

**Terminal status: `CALIBRATION_ORCHESTRATOR_READY_FOR_INPUTS`.**
