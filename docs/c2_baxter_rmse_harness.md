# C2 — Baxter Rating RMSE experimental evaluation harness

Ruling **R2-CAL-OBJECTIVE** names out-of-sample **Baxter Rating RMSE**, minimised,
as the primary mathematical calibration criterion, with Colley Matrix and SRS
reported as independent witnesses and never blended into it.

This lane builds the instrument that measures that criterion for a candidate
regime over the six unresolved V3 calibration axes. It measures. It does not
decide, and it does not supply the numbers it measures.

Package: `ncaaf_engine.simulation.dynamic_weekly_mc_v3.baxter_harness`

## What the harness will not do

| | |
|---|---|
| Author candidate calibration values | The six canonical values stay `null`; `experimental/calibration_regimes.json` ships with zero regimes. Grids are built from values the caller supplies. |
| Write canonical configuration | No code path exists. Promotion stays in `calibration.promote_regime_r2`, behind a human approval token and a named authority. |
| Promote the winner | Ranking is advisory and labelled as such in every payload. |
| Invent observations | With nothing mounted the harness returns `READY_FOR_DATA` and no metrics. |
| Admit betting flow or injury signals | Refused at registration by substring match, so renaming does not admit them. |
| Run the 10,000-path Monte Carlo, or produce final probabilities | Out of lane. Production weekly rerating stays fail-closed in `rerating.BlockedGovernedRerater`. |

## The three statuses

| Status | Meaning |
|---|---|
| `READY_FOR_DATA` | The contract is well formed; the observation set is not mounted. Not an error. No metrics, and none implied. |
| `BLOCKED` | Something is mounted but cannot be honoured — a forbidden signal, an unresolved home-field term, a leaking split. |
| `EVALUATED` | An admissible observation set is mounted and candidates were scored. |

## The measurement

`BAXTER_MARGIN_PREDICTION_RMSE_V1`, the definition the shipped contract names:

> RMSE, over scored out-of-sample observations, of
> `rating[team] - rating[opponent] + venue home-field term`
> against the observed team-relative final margin, where ratings are the Baxter
> rating state the candidate regime produced from **strictly prior weeks**.

This definition is **DERIVED**, not ruled. R2-CAL-OBJECTIVE names the criterion
but does not state its formula, so the harness proposes one, names it in the
contract, records it in every payload as
`OPERATIONAL_DEFINITION_NOT_YET_RULED`, and does not treat it as adopted.

### The weekly recursion

1. Predict every observation in a week from rating state carried in from earlier
   weeks only. This is what makes a scored week out-of-sample.
2. Pass each residual through the regime's **blowout treatment**; average a
   team's treated residuals for the week.
3. Blend against earlier weekly residuals with the **recent-form weights**, most
   recent first, renormalised over the weeks that exist.
4. Scale by the **residual coefficient** and the **sample-size shrink**, clamp to
   the **movement cap**, apply.

**Game SD** converts a predicted margin to a win probability, which drives the
Brier, log-loss and calibration diagnostics. It does not affect the primary
criterion — a test pins that.

Ratings are seeded from `pregame_team_rating` at a team's first appearance. A
team that never carries one blocks the run rather than being given an invented
starting rating.

## Splits

Training / validation / holdout, with three rules enforced rather than assumed:

- Every observation lands in exactly one split.
- Splits are blocks of whole `(season, week)` keys in **strictly increasing time
  order**. A week straddling a boundary is refused.
- **Holdout is not a sweep surface.** `include_holdout` is refused for more than
  one regime: a holdout that can be swept is a second validation set with a more
  reassuring name. Ranking is always computed on validation.

Random, hashed, shuffled, stratified and k-fold policies are refused outright —
on a weekly recursive rating model they train on the future and call the result
out-of-sample.

## Diagnostics

Reported beside the primary criterion, **where supported**. A diagnostic whose
inputs the dataset does not carry returns `UNSUPPORTED` naming what was missing,
rather than a number standing in for absent evidence.

| Diagnostic | Supported when |
|---|---|
| `residuals` | any scored prediction |
| `week_to_week_movement_distribution` | any weekly update was applied |
| `rating_stability` | any weekly update was applied |
| `brier_score`, `log_loss`, `probability_calibration` | some outcome is determinable (`game_result`, else the sign of `actual_margin`; a zero margin is excluded and counted) |
| `blowout_sensitivity` | the regime's blowout treatment names a binding threshold |

One reporting caveat is made explicit rather than left to be misread: when both
directed rows of each game are present, residuals come in exact ± pairs and their
mean is **structurally zero**. The diagnostic says so, and the flat metric set
omits `residual_bias_points` in that case rather than publishing a zero that
looks like evidence of unbiasedness.

## Determinism

No wall clock, no RNG, no set iteration into output. Run identity — `run_id`,
`as_of`, versions, `seed` — is supplied by the caller in a `RunContext`.
Identical inputs produce byte-identical payloads (`payload_digest` pins it), and
a regime's own score does not depend on the order regimes were submitted in.

## Synthetic fixtures

`fixtures.py` generates deterministic synthetic observation sets for validating
the harness itself. Every row carries `source_provenance` beginning
`SYNTHETIC_HARNESS_FIXTURE`; the loader detects it, and the payload reports
`evidence_admissible_for_promotion: false`.
`assert_promotion_evidence_admissible` refuses a synthetic payload outright.
Fixtures are written only to a caller-supplied path — never into `config/` or
`reference/`.

---

# Interface contract

Machine-readable and testable:

```
python -m ncaaf_engine.simulation.dynamic_weekly_mc_v3.baxter_harness.cli interface
```

Handoff document (ships unfilled, on purpose):
`config/dynamic_weekly_mc_v3/experimental/baxter_data_contract.json`,
contract schema version **1.0.0**. A major-version change is a renegotiation and
is refused, not upgraded.

Neither producing lane imports this package, and this package imports neither of
them, so all three can land independently.

## C1 → C2 (calibration data)

C1 delivers the observation set and fills:

| Field | Notes |
|---|---|
| `observations.path` | Resolved relative to the contract document. C2 has no built-in dataset location. |
| `observations.format` | `csv`, `tsv` or `json` — the declared format is used, not the file extension. |
| `observations.dataset_id` | Provenance handle. |
| `observations.sha256` | Optional; when set it must match the mounted file or the run is refused. |
| `split_policy` | `column`, `temporal_week` or `temporal_season`. |
| `hfa.points` / `hfa.source` | Default `V3_CONFIG_HFA_BASELINE_POINTS` reads the governed value from V3 config; `CONTRACT_LITERAL` is required before `points` may be set. |

Columns come from the governed allowlist in `calibration.CALIBRATION_OBSERVATION_COLUMNS`.
Beyond the governed required set, C2 needs:

| Column | Requirement |
|---|---|
| `pregame_team_rating`, `pregame_opponent_rating` | **Required.** Seeds ratings at first appearance. |
| `venue` | Team-relative `HOME` / `AWAY` / `NEUTRAL`. Absent ⇒ treated as `NEUTRAL`, no home-field term. |
| `split` | Required when `split_policy.mode` is `column`. |
| `expected_margin` | Optional. Reported as a baseline comparison only — explicitly **not** the V2.1 static control workbook, and the payload says so. |
| `game_result` | Optional. Enables the probability diagnostics. |
| `source_provenance` | Expected. Marks fixture rows. |

**Row orientation.** Directed and team-relative: one row per `(game, subject
team)`, `actual_margin` signed from the subject team's point of view. Supplying
both directed rows means both sides' ratings move; supplying one means only that
side's does. The payload reports `directed_rows_per_game` so which case it is
stays visible.

If C1 delivers nothing, C2 returns `READY_FOR_DATA`. It does not synthesise
observations to fill the gap.

## C3 → C2 (Colley Matrix and SRS witnesses)

C3 fills the contract's `witnesses` object, one path per witness. C2 reports each
as `MOUNTED` / `NOT_MOUNTED` / `NOT_DECLARED` beside the primary criterion and
**never blends a witness into it** — `calibration.reject_witness_composite`
refuses any weighted composite, and ACC-EXT-12 records the blend as
PROPOSAL ONLY / NOT ADOPTED.

Witness absence is **non-blocking**: a Baxter RMSE evaluation runs without them.

## C2 → downstream

`evaluate_regimes(...)` returns a JSON-serialisable payload carrying the
contract, the objective and its ruling, the observation-set shape, one
`ExperimentRecord` per candidate with full provenance, per-split metrics and
diagnostics, the advisory validation ranking, witness reporting, and a promotion
block that states `auto_promoted: false` and names the gate that would be
required instead.
