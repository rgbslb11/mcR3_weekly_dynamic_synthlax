# OPERATION SYTHALAX — Calibration Evaluation Metrics Lane

## The deterministic scoring oracle for the candidate search

Branch: `claude/v3-calibration-metrics-r1`
Frozen base: `5479f2ae7687c36c0ed4117334171289693dd5c9`
Disposition: **METRIC PACKAGE COMPLETE — AWAITING GOVERNED HISTORICAL INPUTS**

No parameter was promoted, no candidate grid was built, no blocker was retired,
no real calibration run was executed, and no season Monte Carlo was run. The
eight formal blockers are unchanged.

Module: `src/ncaaf_engine/simulation/dynamic_weekly_mc_v3/calibration_metrics.py`
Tests: `tests/dynamic_weekly_mc_v3/test_calibration_metrics.py` (106)

---

## 1. What this lane owns, and what it deliberately does not

This lane owns the answer to "how did this candidate score". It does not own
which candidate wins, which parameter values are worth trying, or what the
blowout policy should be. Those belong to the search lane and to the open
blockers respectively.

The separation is enforced rather than merely intended. The module never reads
`candidate_values` — it carries them through opaquely — so it cannot acquire an
opinion about what a coefficient means. Every diagnostic band, threshold and
phase boundary is a module constant fixed before any candidate exists, identical
for every candidate, and stamped `are_model_parameters: False`.

---

## 2. The criterion is imported, not restated

`PRIMARY_CALIBRATION_METRIC` and `PRIMARY_CALIBRATION_DIRECTION` come from
`calibration.py` rather than being written down a second time, so the criterion
cannot drift by being defined in two places. `rank_candidates` calls
`require_primary_objective` on the way in, which is the same gate
`rank_experiments_governed` uses: a worker cannot rank on a metric it chose.

Ruling `R2-CAL-OBJECTIVE` holds throughout. Colley and SRS are reported
independently and `reject_witness_composite` is called on every witness path.

---

## 3. Two inputs are unavailable, and both fail closed

**No governed margin-to-probability conversion exists.** The only logistic in
the V3 tree is `sor._reference_win_probability`, an Elo expectation scoped to
SOR-B and stamped `not_baxter_rating`. A Baxter conversion needs a per-game
margin standard deviation, and `calibration.game_sd_points` is one of the eight
open blockers — so the conversion is blocked by the quantity the calibration
exists to measure. Brier, log loss, reliability bins, ECE and the calibration
slope/intercept are all implemented and unit-tested, and all sit behind
`ProbabilityConversionAuthority`. **This module defines no margin-to-probability
function at all**; a test asserts that no such symbol exists on it.

**No Colley Matrix implementation is mounted.** Colley appears in the V3 tree
only as the name of a witness in `INDEPENDENT_WITNESSES`. The witness comparison
machinery is model-agnostic and will produce a full Colley block the moment a
governed Colley state is supplied — the supplied-snapshot path is live and
tested. What the module will not do is solve a Colley system of its own:
`require_no_colley_implementation_here` is an unconditional refusal, modelled on
`srs.require_canonical_validated_srs`. A witness written by the scorer is not
independent of the scorer.

The SRS witness *is* available, and carries `srs.py`'s authority boundary
forward unchanged: every SRS-derived number travels with
`NOT_VALIDATED_AGAINST_CANONICAL_ANCHORS` and
`governance.SRS_CANONICAL_VALIDATION_ANCHORS_NOT_MOUNTED` attached, so a rank
correlation computed here cannot be cited downstream as canonical-anchor
validation of anything.

---

## 4. Holdout is sealed by a mechanism, not by a label

A label saying "this is holdout" prevents nothing — the number is still one
dictionary lookup from a sort key. Holdout metrics are computed (the final stage
needs something to release) and then placed in a `SealedHoldout` whose only
accessor requires a token matching
`RELEASE_V3_CALIBRATION_HOLDOUT::<IDENTIFIER>`.

Three layers, because a single one is a single point of failure:

1. `SealedHoldout.as_dict()` emits `SEALED_HOLDOUT_NOT_RELEASED`, so serialising
   a record for a coarse-stage worker cannot leak the score through the artifact.
2. `by_split["holdout"]` is sealed the same way. This was a real leak found by
   the lane's own test and closed before the suite went green: `by_split` was
   emitting a live holdout score block one lookup away from the sealed one.
3. `rank_candidates` maps `COARSE` and `REFINEMENT` to the `validation` split
   and refuses holdout-scored records outright; only `FINAL_HOLDOUT` accepts
   them, and only against a release token.

`evaluate_candidate` additionally refuses `evaluation_split="training"` — an
in-sample RMSE cannot be requested through the argument that requests the real
one. Training metrics stay visible under `by_split` for diagnosis and are not
rankable.

---

## 5. Tie-breaks were fixed before any result existed

`TIE_BREAK_POLICY` is a module constant with digest
`TIE_BREAK_POLICY_SHA256`, which every emitted record carries and any consumer
can assert:

| Tier | Field | Direction |
|---|---|---|
| 0 | `out_of_sample_baxter_rating_rmse` | minimize (**primary**, R2-CAL-OBJECTIVE) |
| 1 | `out_of_sample_mae` | minimize |
| 2 | `absolute_bias` | minimize |
| 3 | `season_rmse_sd` (temporal stability) | minimize |
| 4 | `candidate_id` | ascending — totality only, **not a quality signal** |

Tier 4 exists so that two arithmetically indistinguishable candidates still
receive a deterministic order rather than one that depends on dictionary
insertion. Unscored candidates sort last via an availability flag rather than by
substituting `inf`, which would participate in the arithmetic tiers.

---

## 6. Shard and order invariance

Every aggregation sorts on the total key `(candidate_id, season, order_index,
game_id, split)` before consuming anything, and every sum goes through
`math.fsum`, which is correctly rounded and therefore permutation-invariant.
Floats are emitted raw, as everywhere else in this package; the only
normalisation is `-0.0` to `0.0`, so two arithmetically identical records cannot
digest differently.

Tested at shard counts 1, 2, 3, 5 and 7 against a single-process baseline,
compared by SHA-256 of the serialised record. `merge_shard_results` refuses a
candidate appearing in two shards rather than silently keeping one, which would
make the merged answer depend on shard iteration order.

One caveat recorded rather than papered over: `math.log`, used in log loss
alone, is not guaranteed correctly rounded and may differ in the last ulp
between libm implementations. Log loss is a gated diagnostic and never the
ranking criterion, so this cannot move a selection.

---

## 7. Diagnostics

**Residuals.** Mean, sample SD (ddof=1), RMSE, nine quantiles (type-7, named),
skewness, and a large-residual count at 21 points. `residual_sd` and
`actual_margin_sd` are both reported, adjacent and labelled, precisely because
substituting the second for the first is the failure that would corrupt a future
`game_sd_points` determination while looking correct.
`reject_actual_margin_sd_as_residual_sd` refuses the substitution by name.

**Blowout bands.** Fixed bands over `|actual_margin|` (0–7, 8–14, 15–21, 22–28,
29+) plus the three headline scores: all games, non-blowout (`< 22`), large
margin. The question this answers is whether a candidate's advantage survives
when the blowouts are removed. It does not choose the blowout policy;
`reject_band_as_blowout_policy` refuses that reading and
`calibration.blowout_treatment` stays open.

**Movement.** Mean, SD, median, p90/p95/p99 and max of *absolute* movement —
because a cap clamps magnitude, and a signed mean sitting comfortably inside a
cap can still be struck every week by alternating moves. Cap-hit count and rate
prefer a producer-supplied flag and fall back to derivation against the declared
cap, reporting which was used. The finding that matters is the zero case: a cap
that never binds is not a conservative cap, it is an absent one, and the
candidate is indistinguishable from the same candidate with no cap at all.
`non_binding_cap_detected` reports it; what to do about it is the search lane's
call.

**Temporal stability.** Per season, per season phase (early 1–4, mid 5–9, late
10+), per validation fold. Rows carrying no week abstain from the phase
diagnostic rather than being binned as late season — a postseason game has an
order but not a week. `season_rmse_sd` and `season_rmse_spread` surface the case
a pooled RMSE hides: excellent in two seasons and poor in a third pools to the
same number as mediocre in all three, and only the second is stable.

**Witness leakage.** `require_walk_forward_witness` refuses a witness state that
postdates the evaluation boundary. A retrospective comparison is permitted, but
only by setting `retrospective` on the snapshot, and the output carries
`RETROSPECTIVE_NOT_A_PREGAME_WITNESS` for the rest of the record's life.

---

## 8. Benchmark

Synthetic non-governed fixture, generated by a seeded LCG and stamped
`SYNTHETIC_NOT_ADMISSIBLE` on every provenance field. No real parameter grid was
run.

Best of five per configuration, one process:

| Configuration | Rows | rows/sec | candidates/sec |
|---|---:|---:|---:|
| Margin metrics only, 50 × 800 | 40,000 | 211,262 | 264.1 |
| Margin metrics only, 200 × 800 | 160,000 | 207,554 | 259.4 |
| Margin metrics only, 500 × 400 | 200,000 | 202,520 | 506.3 |
| Full (probabilities + movement + SRS witness), 100 × 800 | 80,000 | 166,694 | 208.4 |

Candidates/sec scales with rows per candidate, which is why the 400-row
configuration clears twice as many candidates at a slightly lower row rate. The
full configuration costs about 20% against margin metrics alone; the witness
comparison is quadratic in shared teams and is the reason, which matters only if
a future witness set is far larger than a 130-team field.

Pure stdlib, single process, no numpy. Measures throughput; measures nothing
about football.

---

## 9. What is still blocked

Only inputs, and none of them is this lane's to supply:

1. **A governed historical observation set.** None exists — see
   `docs/v3_calibration_lane_c.md` §4 and `docs/v3_calibration_evidence_lane.md`.
   The metric package is complete and cannot score anything until one arrives.
2. **A governed margin-to-probability conversion.** Blocked behind
   `calibration.game_sd_points`. Brier and log loss stay `None` with a named
   reason.
3. **A Colley Matrix implementation.** Named as a witness, never written.
4. **Walk-forward witness state.** Requires 1 and, for Colley, 3.

Everything downstream of those inputs is built, tested and deterministic.
