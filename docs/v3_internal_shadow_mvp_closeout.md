# V3 INTERNAL / SHADOW / TEST_ONLY MVP model closeout

What this lane did, what it is entitled to claim, and what it is not.

## Scope, in one line

`INTERNAL_SHADOW_TEST_ONLY_MVP`. Read-only, non-value-bearing, and calibrated
against a **synthetic control corpus**. Not a real-world calibration, and not a
claim to be one.

| | |
|---|---|
| Calibration status | `SYNTHETIC_CONTROL_CALIBRATED` |
| Real-world status | `POST_MVP_REAL_WORLD_VALIDATION_REQUIRED` |
| Evidence domain | `GOVERNED_SYNTHETIC_CONTROL` |
| Value-bearing | No. No market action, no deployment, no production state touched. |

`mvp_control.assert_not_real_world_labelled` is applied to every artifact this
lane emits, so the prohibition is enforced rather than merely written down.

## The rulings

| Ruling | Retires | Reason |
|---|---|---|
| `R-V3-FCS-SCALE-01` | `model_scale.FCS_ELO_1250_TO_V3_POINT_SCALE_ADAPTER` | Governed FCS Elo 1250 maps to **-31.0** V3 unified neutral-field points. |
| `R-V3-FCS-VENUE-01` | nothing | An unresolved FCS home-field modifier is **1.0**, the governed league-average venue modifier. |
| `R-V3-MVP-CONTROL-CORPUS-01` | the six `calibration.*` values and `governance.GAME_SD_CALIBRATION_OPEN` | The canonical 2025 synthetic season is authorised for `MVP_CONTROL_CALIBRATION_ONLY`. |
| `R-V3-POST-MVP-REAL-VALIDATION-01` | nothing | Real historical calibration remains required after the MVP. |

## Two scopes, kept apart

`blocker_report.DISPOSITION_REGISTER` is the **formal global** register and is
unedited. Globally the eight blockers are still live, because global closure
means a real-world calibration and R-V3-POST-MVP-REAL-VALIDATION-01 keeps that
outstanding.

`blocker_report.internal_shadow_mvp_delta()` reports the **MVP** scope: the same
eight, retired against a corpus authorised for that scope and no wider. Eight to
zero. The counts are never merged and neither is reported as the other.

The retirements are computed, not asserted. Each depends on a registry that
checks evidence:

* `fcs.fcs_unified_scale_governed()` — an adapter installed through the
  registration gate that checks derivation, provenance, issuance and token.
* `mvp_control.game_sd_calibration_governed()` — a promotion record installed
  with byte-bound holdout evidence and a measured `game_sd_points`.

Writing a number into a configuration file clears neither. A test pins that: the
MVP configuration on its own still carries two blockers.

## Expected margin

`V3-EXPECTED-MARGIN-001`, taken from production code (`game.simulate_game`), not
from a research artifact:

```
expected_subject_margin = subject_strength - opponent_strength + venue_adjustment
venue_adjustment = +hfa * modifier at HOME, -hfa * modifier at AWAY, exactly 0.0 at NEUTRAL
```

HFA is the locked **3.5** of ruling R2-HFA-3P5. It is applied and never fitted.
The formula has no free parameter and consumes no calibration coefficient.

`P_TO_STRENGTH_TRANSFORM` and `REFERENCE_HFA` are **not** used. Both are
Elo-domain SOR-B items that no point-domain code path reads; the names existing
in a report artifact is not a reason to resurrect them.

## The strength axis

The canonical axis — `14 x Unified Master Z` over the closed 121-team FBS
population — is untouched. V3 still reads the finished points column verbatim.

For the control corpus the lane applies the *same construction* (a standardised
rating over a closed population, scaled to points) to the 2025 control
population, and identifies that population's own points-per-SD empirically:

```
margin - venue = beta * (z_home - z_away) + error       (fitted on training stages only)
```

This is identification, not choice. The prior expected-margin lane recorded a
scale/coefficient confounding that requires *both* to float; here the left side
is in observed football points and the venue term is fixed at 3.5 in the same
units, so the scale is pinned by the data. `beta` is a control-scope
experimental quantity and is never written to the canonical axis.

## Walk-forward

Opening state comes from the **preceding** season's rating layer. Every
prediction consumes only that layer plus completed games of earlier stages. The
control season's own final ratings are an external witness and never a pregame
feature — a test perturbs them and asserts not one prediction moves.

Weeks 1 and 2 both open on preseason strength; the first promoted rerating is
after Week 2; strength freezes after Championship Saturday. Those are governed,
not calibrated.

## The six parameters

| Parameter | Value |
|---|---|
| `weekly_performance_residual_coefficient` | 0.30 |
| `weekly_movement_cap_points` | 10.0 |
| `recent_form_weights` | geometric decay, ratio 0.7, six terms |
| `blowout_treatment` | `cap_margin`, 35.0 points |
| `game_sd_points` | 16.75 |
| `sample_size_regularization` | `none` |

Selected on three rolling-origin validation folds, each with its opening axis
refitted on the stages that strictly precede its window. The holdout was scored
once, at the end, and never used for selection. Definition, unit, role,
admissible domain, interactions, objective contribution and validation behaviour
for each parameter are emitted with the calibration record; so is a re-measured
sensitivity table, so the numbers in the record cannot drift from the code.

`game_sd_points` is estimated rather than searched: it does not enter the
expected margin, so the primary objective cannot select it. It is the
out-of-sample residual dispersion of the selected model on the holdout — not the
unconditional margin spread, which bounds it from above and locates nothing.

The one identification failure found is reported rather than resolved by fiat:
the residual coefficient and the sample-size shrink both scale the same weekly
delta and trace a shallow ridge. The objective prefers the no-shrink end, and the
governed preseason prior-decay schedule already regularises the early weeks.

## The FCS adapter

`-31.0` neutral-field points, installed through `register_fcs_scale_adapter`
under `DIRECT_CHAIRMAN_AUTHORITY`. Every previously refused route stays refused
by name. The adapter embeds **no** home-field advantage: venue is applied
afterwards by ordinary V3 logic, identically for FBS and FCS participants, so
there is no double HFA and none at a neutral site.

The venue clause needed one further resolution. Three scheduled games place an
FCS entity at a HOME venue, and their `home_field_advantage_modifier` is recorded
`UNRESOLVED`. Ruling **R-V3-FCS-VENUE-01** issues that modifier directly as
**1.0**, the governed league-average venue modifier, under
`DIRECT_CHAIRMAN_AUTHORITY`. The evidence it records is checkable on the same
sheets: all 121 governed FBS members carry exactly 1, so the league average is 1
exactly, and the canonical master names the convention
(`hfa_modifier_league_average`). It has its own gate and its own approval token —
the point-scale adapter's token is not accepted for it — and the pre-ruling
refusal is still the behaviour until it is installed.

At the R5 closeout this same value was installed as a *disclosed assumption*
rather than an issued ruling. R-V3-FCS-VENUE-01 supersedes that disclosure. Only
the authority classification changed; the number, the mathematics and every
simulation output are unchanged.

## What this does not establish

Stated with the numbers rather than discovered later:

* The corpus declares its own scores simulated. Parameters fitted against it
  measure a score generator, not football.
* One season. Inter-season out-of-sample error is unmeasured; the holdout shares
  a season, a schedule and a generator with the training block.
* The corpus carries almost no home-field effect, so it cannot confirm the
  governed 3.5.
* Its unconditional margin dispersion is far wider than the dispersion recorded
  for real observed games in the prior evidence lane, and `game_sd_points`
  inherits that width.
* No FBS-versus-FCS game exists in the control season, so the -31.0 adapter is
  bound by ruling and tested structurally, never calibrated here.

`calibration_contract` — the real-world ingestion contract, including its
`synthetic_content: REFUSED` clause and its three-season minimum — is left
completely unedited. This lane does not satisfy it and does not claim to.
