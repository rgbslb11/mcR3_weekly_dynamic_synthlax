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

Not the transform — the **axis**. `Unified Neutral-Field Points = 14 × Unified
Master Z`, and both halves are 2026-specific.

**Population closure.** Unified Master Z is standardized over a *closed*
121-team FBS population. Another season is another population; re-standardizing
yields a different axis, so two seasons' point values are not commensurable. No
register issues an anchoring rule. The canonical 2026 universe is itself
synthetic — it contains members no real season had.

**Scale provisionality.** The `14` points/SD is marked in its own source
"initial scale pending margin calibration", and `ENG-CAL-MARGIN` is OPEN. It is
provisional against exactly the calibration this expected margin would feed.

The second point is not a caveat, it is an identification failure. Scaling the
axis by `k` and the residual coefficient by `1/k` leaves every predicted margin
unchanged, so **no objective over margins can distinguish them**. That is the
unidentifiability the data contract already names under
`expected_margin_transform` — this lane locates it precisely: it is between the
*axis scale* and the coefficient, not between a missing transform and the
coefficient.

`HISTORICAL_STRENGTH_AXIS_ANCHOR` is recorded as a **model-identification
dependency, not a formal blocker**. It gates no V3 execution path — V3 runs the
2026 population, where the axis is fully defined — and no governed authority
requires blocker registration for it.

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

## 5. Weeks 1–2 are a genuine identification subset

Conditional on the anchor, and on a corpus this repository does not hold.

Stage A uses only weeks 1–2, depends on no calibration coefficient and on no
rerating formula, and could support an initial residual-dispersion estimate.
Three honest limits: two weeks per season is a thin base; the estimate inherits
the anchored scale directly; and opening weeks are not a random sample of a
season — they are systematically heavy in mismatches. It bounds and informs. It
does not settle `game_sd_points`. Nothing was estimated.

The full dependency graph is `expected_margin.IDENTIFICATION_STAGES` (A opening
weeks → B outer walk-forward → C HFA as an experimental witness → D holdout).

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

`expected_margin.pregame_state_contract()` — deliberately **narrower** than
`calibration_contract.REQUIRED_CONTRACT_FIELDS`, which is the superset the six
coefficients need. This is the subset the *predictor half* needs:

`game_id` · `season` · `week` · `order_key` · `subject_team` · `opponent_team` ·
`venue` (subject-oriented) · `subject_pregame_points` ·
`opponent_pregame_points` · `strength_domain` ·
`state_effective_through_week` · `state_origin` · `home_field_modifier` ·
`source`

Two that a supplier will not expect and that are load-bearing:

- **`venue` must be subject-oriented.** The V3 schedule stores venue
  home-oriented (`models.Venue` is `HOME|NEUTRAL`, away-ness positional). The
  orientation must be stated, never inferred from column order.
- **`strength_domain` must be declared per row.** A residual computed across two
  axes is arithmetic, not evidence.

`actual_margin` is *not* required here — it is the outcome half, needed by
calibration, not by this construction. Neither is `game_sd_points`.

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
| `game_sd_points`, residual coefficient | `EMPIRICALLY_CALIBRATABLE`, gated on the anchor |
| Weeks 3+ rerating formula | `EVIDENCE_MISSING` — no governed formula exists |
| Historical corpus | `EVIDENCE_MISSING` — already raised by the prior lane |
| **Historical strength axis anchor** | **`HUMAN_GOVERNANCE_REQUIRED`** |

Only the last one survives. A Z-score carries no information about the scale of
the population it was taken over, so recovering an anchor from the mounted corpus
would need a second governed quantity on the same axis in a second season — and
there is none.

**Minimum ruling question**, unbundled:

> For a historical season outside the closed 2026 121-team FBS population, is
> there a governed rule placing that season's pregame team strengths on the V3
> unified neutral-field point axis — and if so, does it fix the points-per-SD
> scale independently of margin calibration, or does the provisional 14 remain
> subject to it?

Not bundled with the synthetic-universe admissibility question (already raised),
the FCS adapter, or the two SOR-B items.

Note that this **replaces** step 3 of the evidence lane's §14 unblocking list.
Ratifying the SOR-B items would not advance expected margin; anchoring the axis
would.

---

## 12. State

- Tests **640 full / 581 V3**, up from 602 / 543. 38 new. No existing test
  modified or weakened.
- Formal blockers **8 before, 8 after**, same set. None opened, none retired.
- No parameter promoted. `v3_experimental.json` untouched; all six calibration
  values remain `null`. No canonical config writer created.
- HFA `3.5` unchanged, FCS Elo `1250` unchanged, FCS mapping still `None`.
- Board custody, Board SHA, V2.1 SHA and the three path tiers unchanged.
- No simulation run. No probabilities. No Monte Carlo of any tier.
- Carry-forward advisories A–E untouched; none was necessary to prevent an
  authority bypass here.
