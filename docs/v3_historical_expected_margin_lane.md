# V3 historical expected-margin lane

Base `5479f2ae7687c36c0ed4117334171289693dd5c9`, branch
`claude/v3-historical-expected-margin`. Baseline reproduced at **602 full / 543
V3**, `pip check` clean, working tree clean.

The question: does OPERATION SYTHALAX have enough governed and mathematical
authority to reconstruct a historical pregame expected margin, so that

```
actual_margin_g - governed_pregame_expected_margin_g = performance_residual_g
```

can be computed without leakage?

**Answer.** The transform is fully governed and always was. What is missing is
the *axis*, and it is missing for a different reason than the record currently
states.

---

## 1. The correction this lane makes

`docs/v3_calibration_evidence_lane.md` §9 concludes that `expected_margin`
cannot exist in V3 units because "V3 has no ratified rating-to-margin transform.
`sor.py` records `P_TO_STRENGTH_TRANSFORM` and `REFERENCE_HFA` as unratified."
§14 makes ratifying those two a required unblocking step.

Read against the module that defines them, that inference does not hold. Both
labels are **SOR-B items in the Elo domain**:

| Label | What it actually is | Domain |
|---|---|---|
| `P_TO_STRENGTH_TRANSFORM` | Mapping from the Poisson-binomial **reference win probability** `p_ref_ge_w` to a resume scalar, inside an unmounted `compute_sor_b.py` | dimensionless [0, 1] → resume scalar |
| `REFERENCE_HFA` | Whether and how HFA enters `sor._reference_win_probability(r_ref, opponent_elo)` | **Elo** points, on the 400-point logistic scale |

`P` is not a power index. `sor.UNRATIFIED_SOR_B_ITEMS` is reachable only from
`sor.weekly_sor_row`, which stamps `RESEARCH_REPORT_ONLY` and is never a
committee or Monte Carlo input. `SorOpponent` carries `home` and `neutral_site`
and `_reference_win_probability` ignores both — that is the `REFERENCE_HFA` gap,
and it is entirely inside a research resume metric.

Ratifying either would change that report and would not produce one football
point. The correction is recorded in `expected_margin.SOR_B_SCOPE_FINDING` and
in the authority matrix. **The evidence-lane document is not rewritten**; it
stays as issued and this artifact supersedes only the one inference.

---

## 2. The transform that does exist

`game.simulate_game`, in production, unchanged by this lane:

```python
hfa      = 0.0 if game.venue == "NEUTRAL" else hfa_baseline_points * home_hfa_modifier
expected = home.current_strength_points - away.current_strength_points + hfa
```

Home-oriented. Two properties make it exact rather than conventional:

**The strength axis is already a margin axis.** `inputs.load_preseason_ratings`
reads column **"Unified Neutral-Field Points"** verbatim from
`2026_CFB_2026_Preseason_Unified_Power_Ratings.xlsx!Master Ratings`. It is a
neutral-field *point* quantity by construction, so the difference of two of them
is a neutral-field margin in points. On this axis the rating-to-margin transform
is the identity. No coefficient is interposed and none is needed.

**The venue term is additive in the same unit and exactly zero at neutral.**
Because the axis is defined at neutral field, the venue correction is the whole
of the departure from neutral, carried by `SCHED-HFA-BASE = 3.5` — LOCKED, ruling
`R2-HFA-3P5`.

Consequences worth stating plainly:

- The formula has **no free parameter** and consumes **no** calibration
  coefficient.
- It does **not** consume `game_sd_points`. `simulate_game` uses the SD only for
  the stochastic draw. Expected-margin reconstruction is independent of the
  game-SD blocker.
- `home_hfa_modifier` is `1.0` for all 121 FBS members and `None` for the 13 FCS
  entities, whose POWER_CRUNCH value is the sentinel `UNRESOLVED`. There is no
  `or 1.0`.

The subject-oriented form is a re-orientation, not a second parameter: `+h` at
HOME, `−h` at AWAY (the modifier still belongs to the home side), exactly `0.0`
at NEUTRAL.

---

## 3. What is genuinely missing

Not the transform, and not a ruling — the **opening state**. `Unified
Neutral-Field Points = 14 × Unified Master Z`, and both halves are 2026-specific.

**Population closure.** Unified Master Z is standardized over a *closed*
121-team FBS population, and the canonical 2026 universe is itself synthetic. So
2026 point *values* are not transportable onto another season's axis. That
bounds what may be copied across seasons — it does not block reconstruction,
which standardizes the historical population on its own terms rather than
importing 2026 numbers.

**Scale provisionality.** The `14` points/SD is marked in its own source
"initial scale pending margin calibration", and `!Ensemble Parameters` says
outright "recalibrate against game margins". `ENG-CAL-MARGIN` is OPEN.

> **Correction (audit finding 1).** A prior revision of this lane read the second
> point as a *global* identification failure: scale the axis by `k`, scale the
> residual coefficient by `1/k`, and every predicted margin is unchanged. That
> claim is **withdrawn**. It requires a weekly residual coefficient to be present
> to absorb the rescale, and in weeks 1–2 there is none — those weeks precede the
> first promoted rerating, which §4 records as the base case of the very same
> recursion. The claim contradicted the base case stated alongside it.
> Independently, the venue term carries the governed additive HFA `3.5` in real
> football points; it does not rescale with the strength axis, so it acts as a
> fixed-length ruler against which a change of scale is visible rather than
> absorbable. Observed margins are already in that same unit.

So the axis scale is **empirically identifiable**, not a matter for governance:

| Weeks | Expected margin | Scale identifiable? |
|---|---|---|
| **1–2** | `scale × opening-strength difference + governed venue adjustment` | **Yes** — no weekly coefficient is in the model to cancel it |
| **3+** | adds the promoted-rerating term | Yes, conditional on weeks 1–2, as an outer-loop problem over candidate vectors |

The cleanest subset is confirmed-**neutral** games, where the venue term is
exactly `0.0` — neither the HFA nor a per-team home-field modifier enters at all.

This claims identifiability, not precision. Two weeks per season is a thin base,
opening schedules are mismatch-heavy and are not a random sample, and
venue-ambiguous games are excluded rather than imputed.

`HISTORICAL_STRENGTH_AXIS_ANCHOR` is therefore classified
**`EMPIRICALLY_CALIBRATABLE`**, with `chairman_ruling_required = false`. What
remains outstanding is a model **input** — a historical opening standardized
state — not an authority. It is still **not a formal blocker**: it gates no V3
execution path, and the eight formal blockers are unchanged.

A separate operation stays impossible, and is not the one performed here:
recovering a historical *raw standard deviation* from a Z-score. A Z carries no
information about the scale of the population it was taken over. The scale here
is fitted **forward** against observed margins, not recovered backward from a Z.

---

## 4. Circularity: tested, and it is not there

The suspected circle: expected margin needs pregame strength → pregame strength
needs the prior rerating → the prior rerating needs the coefficient being
calibrated.

Traced against `engine` and `config`, it is a recursion with a **well-founded
base case**. `first_promoted_rerating_after_week = 2` and
`audit_only_after_week(w) = w < 2`, so week 1's rerating is audit-only and never
promoted, and week 2's games are played *before* the after-week-2 promotion.
Weeks 1 and 2 therefore open on preseason strength and consume no coefficient.

For any candidate parameter vector the whole walk-forward is deterministic and
uses only prior completed games. That is a profile / outer-loop estimation
structure, statistically valid, and **not** a circular definition.
Classification: `NOT_CIRCULAR__PARAMETER_CONDITIONAL_RECURSION`. This lane does
not run the loop.

One thing is stronger than the record suggests, and in the unhelpful direction:
for weeks 3+ V3 carries **no governed rerating formula at all**.
`rerating.BlockedGovernedRerater` raises unconditionally, and
`FixtureResidualRerater` is test-only and says so. Even a fully specified
parameter vector would not let V3 reconstruct a week-3 state. The six null
coefficients are the *second* obstacle there, not the first.

---

## 5. The identification stage graph

Conditional on the anchor, and on a corpus this repository does not hold.

`expected_margin.IDENTIFICATION_STAGES` is the full dependency graph, in the
corrected resolution order of audit finding 2:

| Stage | Name | Scope |
|---|---|---|
| **A** | `HISTORICAL_OPENING_STANDARDIZED_STATE` | per historical season, before any week is scored |
| **B** | `WEEK_1_2_POINT_AXIS_SCALE_IDENTIFICATION` | weeks 1–2 only |
| **C** | `OUTER_WALK_FORWARD_OVER_CANDIDATE_RERATING_PARAMETERS` | weeks 3+ |
| **D** | `OUT_OF_SAMPLE_RESIDUAL_DISPERSION` | `game_sd_points` |
| **E** | `HFA_AS_AN_EXPERIMENTAL_WITNESS` | diagnostic, after stage B |
| **F** | `HOLDOUT_VALIDATION` | reserved seasons |

The order is the content of the graph, not a presentational choice:

```
historical opening standardized state                (A)
    -> week 1–2 point-scale calibration              (B)
    -> anchored historical V3 point states
    -> weeks 3+ candidate-vector walk-forward        (C)
    -> out-of-sample residuals
    -> game_sd_points / residual dispersion          (D)
```

**A** is a model *input*, consumed and not reconstructed here: an opening state
standardized over the historical season's own population, never imported from
the closed 2026 universe. It depends on no calibration coefficient, no governed
weekly rerating formula, and no ruling.

**B** is the genuine identification subset. Weeks 1–2 precede the first promoted
rerating (§4), so no weekly residual coefficient is in the model to absorb a
rescale, and the governed additive HFA `3.5` stays a fixed-length ruler in real
football points. That is what makes the points-per-SD scale empirically
identifiable rather than a governance question. Three honest limits: two weeks
per season is a thin base; the estimate inherits the anchored scale directly;
and opening weeks are systematically heavy in mismatches, so they are not a
random sample of a season. Venue-ambiguous games are excluded rather than
imputed, which is itself a selection effect. The stage is identified; it is not
thereby precise.

**C** is valid as a procedure and not runnable today — the formula that a
candidate vector would parameterise does not exist in governed form
(`rerating.BlockedGovernedRerater` raises unconditionally). It is an
optimisation problem conditional on B, not an identification failure.

**D** comes *after* the scale, never before it. `game_sd_points` is estimated
from out-of-sample residuals once the deterministic mean model exists, never
from `sd(actual_margin)`. Weeks 1–2 can support a preliminary estimate off B
alone; that bounds and informs, and does not settle `game_sd_points`.

**E** is a diagnostic in its own namespace. Estimating HFA jointly with the axis
scale would weaken the ruler that makes B clean, so it is estimated only against
an already identified scale, and the canonical V3 football-point HFA `3.5`
stays LOCKED under `R2-HFA-3P5` and is not an estimand.

**F** is scored once, never used for selection.

This lane runs no stage. Nothing was estimated.

---

## 6. Game SD: 19.764 is a bound, not a value

`Var(actual) = Var(expected) + Var(residual) + 2·Cov(expected, residual)`. A
pregame predictor without systematic bias has `Cov ≈ 0`, so
`Var(residual) = Var(actual) − Var(expected) ≤ Var(actual)`. The unconditional
signed-margin SD bounds the residual SD from above, strictly whenever the
predictor explains any strength difference at all. It locates nothing.

`game_sd_points` is the residual SD by construction — `simulate_game` draws
`Normal(expected, game_sd_points)` *around* the deterministic mean.

Before it can be estimated: the axis anchor (the SD is in points and inherits
the scale), a governed pregame expected margin per observation, `game_type` and
`overtime_periods` tagging, and `opponent_division` so FBS-vs-FCS residuals are
not pooled on an open scale. `ENG-CAL-MARGIN` is untouched; 20.2 stays
unpromoted.

---

## 7. HFA

Not chosen by convenience. The reference HFA a reconstruction requires is a
question of **units**, not preference: an HFA is meaningful only in the units of
the strengths it is added to. So:

- Strengths on `V3_UNIFIED_NEUTRAL_FIELD_POINTS` → `3.5`, authority
  `R2-HFA-3P5` / `SCHED-HFA-BASE`. Authorized.
- Strengths on any other axis → `3.5` is **not** authorized, and nothing here
  supplies a substitute.

The four values stay separated and none is collapsed: V3 point `3.5` (LOCKED),
V2.1 legacy `4.0` (HISTORICAL / NOT CURRENT, refused by name by
`hfa.require_governed_hfa`), CCG/MC Elo `65` (LOCKED, separate namespace), and
Elo-layer `55` — which is **not defined anywhere in this repository**. The
matrix records it as `NOT_PRESENT_IN_THIS_REPOSITORY` rather than asserting a
value for it.

A historically estimated HFA would be a witness in its own namespace. The
canonical V3 HFA is unchanged by this lane.

---

## 8. FCS

Unchanged. FCS Elo stays `1250`, point mapping stays `None`,
`model_scale.FCS_ELO_1250_TO_V3_POINT_SCALE_ADAPTER` stays open. Every
FBS-vs-FCS expected margin fails closed on that existing blocker. No conversion
was attempted and no number produced.

The interface refuses at two independent points: an FCS opponent has no point
value (`fcs.require_fcs_unified_points`), and an FCS home side has no home-field
modifier (`fcs.require_fcs_hfa_modifier`). Neither defaults.

---

## 9. What was built

`src/ncaaf_engine/simulation/dynamic_weekly_mc_v3/expected_margin.py` — a narrow
experimental module. Three statuses, and the middle one is the point:

| Status | Meaning | Number returned |
|---|---|---|
| `AUTHORIZED` | every input and binding present | yes |
| `DERIVABLE` | every term determined, formula exact, **axis binding ungoverned** | no |
| `UNAVAILABLE` | an input absent, refused, or on the wrong axis | no |

`DERIVABLE` lets a reader tell "we cannot compute this" from "we can compute
this and are not permitted to". Those are different problems with different
remedies and a two-state interface conflates them.

Refusals that raise rather than return a status: a leaking pregame state, and an
HFA that is not the ruled value. No later corpus fixes either, so neither may be
summarised as one unavailable row among many.

Artifact: `reference/dynamic_weekly_mc_v3/V3_HISTORICAL_EXPECTED_MARGIN_AUTHORITY_MATRIX.json`
(deterministic, sorted keys, LF, trailing newline).

Tests: `tests/dynamic_weekly_mc_v3/test_r6_historical_expected_margin.py`. The
load-bearing one evaluates `game.simulate_game` and the historical path on the
same inputs and requires bitwise agreement — every other guarantee is worthless
if those two drift.

---

## 10. What the corpus lane must supply

Tier A, and only tier A. `expected_margin.pregame_state_contract()` is a composed
view over three **disjoint** contracts — A is sourced, B is generated, C is
stamped — and a raw historical corpus owns the first of them. The whole is still
deliberately narrower than `calibration_contract.REQUIRED_CONTRACT_FIELDS`,
which is the superset the six coefficients need across all tiers.

### A. Raw historical observation inputs — `raw_observation_contract()`

Supplied by the historical observation corpus. Source-observed or
deterministically source-derived football facts only:

`game_id` · `season` · `week` (the week the game was **played**) · `order_key` ·
`subject_team` · `opponent_team` · `venue` (subject-oriented) ·
**`actual_margin`** · `source` · `observed_at` · `recorded_at`; plus
`opponent_division` where the observed division is relevant to an exclusion.

Three that a supplier will not expect and that are load-bearing:

- **`actual_margin` is required here.** It is a raw observation — the outcome
  half of every residual, and the only quantity in the reconstruction the engine
  never produces. It is sourced, never reconstructed.
- **`venue` must be subject-oriented.** The V3 schedule stores venue
  home-oriented (`models.Venue` is `HOME|NEUTRAL`, away-ness positional). The
  orientation must be stated from named venue evidence, never inferred from
  column order.
- **`order_key` is not decoration.** It is the only field that can prove a state
  pre-dates its game when two games share a week.

Refused outright: postgame ratings, end-of-week ratings containing the game
itself, season-end ratings, future opponent results, final committee rank, and
future standings, SRS, SOS or SOR.

**The corpus lane is not asked to manufacture V3 pregame ratings.** Every rating,
point state, strength domain and expected margin is model output; a raw supplier
producing them is how a reconstruction ends up validating itself.

### B. Derived / reconstructed model state — `derived_model_state_contract()`

Produced downstream by the historical replay / expected-margin layer, as a
function of a tier-A row, an opening state and a candidate parameter vector —
never sourced:

`subject_pregame_points` · `opponent_pregame_points` · `strength_domain` ·
`state_origin` · `state_effective_through_week` · `expected_margin` ·
`venue_adjustment_points` (the venue term actually applied: `+H·m` at HOME,
`−H·m` at AWAY, exactly `0.0` at NEUTRAL) · `axis_anchor` · `status`

`strength_domain` must be declared per row, because a residual computed across
two axes is arithmetic, not evidence. The layer additionally requires, as
inputs it does not itself emit, a historical opening standardized strength
state, a candidate rerating parameter vector for weeks ≥ 3, and the governed
`home_field_modifier` of the home side at non-neutral venues — a governed V3
register value, not a corpus field.

### C. Experiment metadata — `experiment_metadata_contract()`

Stamped by whatever harness runs the experiment; neither the corpus's job nor
the reconstruction's:

`candidate_id` · `parameter_vector_id` · `model_version` ·
`experiment_config_sha` · `dataset_sha` · `split_sha` · `authority_id` (the
`AxisAnchor` `anchor_id` carried on every tier-B row, so a residual can be
attributed to the mapping that produced it) · `formula_id`

`game_sd_points` is owed by none of the three: `simulate_game` consumes it for
the stochastic draw only, and the deterministic mean does not depend on it.

The tier table in §11a is the same boundary stated once more, and a test asserts
the three field sets are disjoint.

`claude/v3-historical-observation-corpus-r6` was not read, edited or waited on.

---

## 11. Is a Chairman ruling actually needed?

Classified before asking:

| Item | Classification |
|---|---|
| V3 expected-margin transform | `MATHEMATICALLY_DERIVABLE_FROM_GOVERNED_DEFINITIONS` — already mounted and ratified |
| Subject-team orientation | `ENGINEERING_DERIVABLE` — arithmetic on one governed term |
| Venue term at neutral | `MATHEMATICALLY_DERIVABLE` — exactly zero because the axis is neutral-field |
| `P_TO_STRENGTH_TRANSFORM` | Out of scope for expected margin. Remains open for SOR-B on its own terms |
| `REFERENCE_HFA` | Out of scope for expected margin. Remains open for SOR-B on its own terms |
| Reference HFA for a V3-axis reconstruction | `MATHEMATICALLY_DERIVABLE` — units decide it; `3.5` under `R2-HFA-3P5` |
| `game_sd_points`, residual coefficient | `EMPIRICALLY_CALIBRATABLE`, after the week 1–2 scale |
| Weeks 3+ rerating formula | `EVIDENCE_MISSING` — no governed formula exists |
| Historical corpus | `EVIDENCE_MISSING` — already raised by the prior lane |
| **Historical strength axis anchor** | **`EMPIRICALLY_CALIBRATABLE`** |
| Historical opening standardized state | `EVIDENCE_MISSING` — a model **input**, supplied externally |

**No Chairman ruling is required, and none is formulated here.**
`chairman_ruling_required = false`.

The prior revision classified the axis anchor `HUMAN_GOVERNANCE_REQUIRED` and
put a ruling question here. Audit finding 3 reversed that, and the reasoning is
in §3: the points-per-SD scale is identifiable from real week 1–2 margins, which
precede the first promoted rerating and so consume no weekly residual
coefficient. Estimating it also *executes* the instruction its own governed
source carries — "recalibrate against game margins" — rather than extending
governance. The ruling question is withdrawn rather than reworded.

What still sits on the critical path is an **input**, not an authority: a
historical opening standardized strength state. `claude/v3-historical-opening-state-r1`
owns that; this lane consumes it.

Governance re-enters only at the **promotion** boundary. Fitting a scale as
experimental evidence needs no ruling; promoting any fitted value to canonical
stays governed by the existing no-canonical-writer regime and the six `null`
calibration values. This lane promotes nothing.

Note that this **replaces** step 3 of the evidence lane's §14 unblocking list.
Ratifying the SOR-B items would not advance expected margin.

### Resolution order (audit finding 2)

The prior revision said the axis had to be fixed *before* margin calibration
because the reverse order was unidentified. That is corrected — the order runs
the other way:

1. obtain a valid historical opening standardized strength state;
2. use real **week 1–2** margins, where no promoted rerating coefficient has yet
   entered, to identify the point-axis scale;
3. with the opening point domain established, run later-season walk-forward
   **candidate rerating vectors**;
4. estimate residual dispersion / `game_sd_points` from **out-of-sample
   residuals**, once the deterministic mean model exists.

No value at any step is estimated in this lane.

---

## 11a. Corpus tiers (audit finding 4)

The single `pregame_state_contract` field list conflated raw observation with
model state, which would have asked a raw data supplier to manufacture model
output. It is now three contracts:

| Tier | Contract | Owner | Contents |
|---|---|---|---|
| **A** | `raw_observation_contract()` | historical observation corpus | `game_id`, `season`, `week`, `order_key`, both canonical team ids, subject-oriented `venue`, `actual_margin`, `source`, `observed_at`, `recorded_at`; `opponent_division` where relevant |
| **B** | `derived_model_state_contract()` | historical replay / expected-margin layer | `subject_pregame_points`, `opponent_pregame_points`, `strength_domain`, `state_origin`, `state_effective_through_week`, `expected_margin`, `venue_adjustment_points`, `axis_anchor`, `status` |
| **C** | `experiment_metadata_contract()` | calibration harness | `candidate_id`, `parameter_vector_id`, `model_version`, `experiment_config_sha`, `dataset_sha`, `split_sha`, `authority_id`, `formula_id` |

The three tiers are disjoint, and a test asserts it. **Tier A is the whole of
what a raw corpus owes**, so this composes with
`claude/v3-historical-observation-corpus-r6` without that lane producing a single
model output.

### Axis anchor enforcement (minor finding)

`axis_anchor_authority` was a free-form string: any caller-invented token
unlocked a number. It is now an `AxisAnchor` whose `kind` must come from a closed
set — `GOVERNED_REGISTER_RULE`, `EMPIRICAL_WEEK_1_2_SCALE_CALIBRATION`,
`PROVISIONAL_2026_POINTS_PER_SD_REUSE` — carrying `anchor_id`,
`points_per_sd_status` and `source`, all required. A bare string is refused.

The residual limit is stated rather than hidden: the module cannot verify that a
named source says what the caller claims. That remains **`NON-BLOCKING_ADVISORY`**
for calibration composition.

---

## 12. State

- Tests **656 full / 597 V3**, up from 602 / 543 at the frozen base. 54 in this
  lane. No existing fail-closed behaviour weakened; the only tests rewritten are
  the ones that asserted the conclusions audit findings 1–4 corrected.
- Formal blockers **8 before, 8 after**, same set. None opened, none retired.
- No parameter promoted. `v3_experimental.json` untouched; all six calibration
  values remain `null`. No canonical config writer created.
- HFA `3.5` unchanged, FCS Elo `1250` unchanged, FCS mapping still `None`.
- Board custody, Board SHA, V2.1 SHA and the three path tiers unchanged.
- No simulation run. No probabilities. No Monte Carlo of any tier.
- Carry-forward advisories A–E untouched; none was necessary to prevent an
  authority bypass here.
