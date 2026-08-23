# OPERATION SYTHALAX — V3 Chairman Model-Design Rulings R1

Branch: `claude/v3-chairman-model-design-rulings-d0yk86`
Machine-readable record: `reference/dynamic_weekly_mc_v3/V3_CHAIRMAN_MODEL_DESIGN_RULINGS_R1.json`
Code: `src/ncaaf_engine/simulation/dynamic_weekly_mc_v3/chairman_model_design_r1.py`
Tests: `tests/dynamic_weekly_mc_v3/test_r1_chairman_model_design_rulings.py`

Disposition: **AUTHORITY RECORDED — FCS ADAPTER INPUT MISSING**

No calibration value was promoted, no blocker retired, no configuration file
edited, no season simulated, and no probability artifact produced.

---

## 1. What this lane is

Seventeen Chairman model-design decisions are written down once, in a form the
later autonomous V3 model-run supervisor can consume without re-reading prose.
Some of those decisions are **fixed values** and some are **specifications for a
sweep that has not run**. The artifact keeps the two apart, because collapsing
them is how a design convention gets reported as an empirical finding.

Three epistemic classes are used and never mixed:

| Class | Meaning | Applies to |
|---|---|---|
| `FIXED_V3_POLICY` / `FIXED_V3_GLOBAL_POLICY` / `FIXED_V3_SYNTHETIC_SCALE` | True by Chairman decision | blowout cap 25.0, point scale 14.0, prior decay, HFA 3.5, FCS Elo 1250 |
| `DESIGN_TUNING_REQUIRED` → `FIXED_BY_V3_*_DESIGN` | Selected by a declared sweep against declared model-behaviour diagnostics | coefficient, `game_sd_points`, recent-form lambda |
| `ADVISORY_ONLY` / `EXTERNAL_WITNESS_ONLY` / `SYNTHETIC_FIT_RESULT` | Reported, witnessed, or owned elsewhere | 10-slot rank rule, real football, sample-size regularization |

`EMPIRICALLY_IDENTIFIED` is defined in the module for exactly one purpose: so
`reject_empirical_identification_claim` can refuse it. Nothing in this round
carries it, and a test walks the whole parameter register to prove it.

---

## 2. The fixed values

| Parameter | Value | Status |
|---|---|---|
| `BLOWOUT_TREATMENT` | `CAP_UPDATE_DRIVING_MARGIN` | `FIXED_V3_POLICY` |
| `BLOWOUT_MARGIN_CAP_POINTS` | `25.0` | `FIXED_V3_POLICY` |
| `point_scale` | `14.0` | `FIXED_V3_SYNTHETIC_SCALE` / `NOT_EMPIRICALLY_IDENTIFIED` |
| `WEEKLY_RANK_MOVEMENT_ADVISORY_SLOTS` | `10` | `ADVISORY_ONLY` |
| Preseason prior, weeks 0–7+ | `1.00 / 0.80 / 0.60 / 0.50 / 0.40 / 0.30 / 0.20 / 0.15` | `FIXED_V3_POLICY` |
| `GLOBAL_HOME_FIELD_ADVANTAGE_POINTS` | `3.5` (neutral `0.0`) | `FIXED_V3_GLOBAL_POLICY` |
| `FCS_ELO` | `1250` | `FIXED_V3_POLICY` |
| First promoted rerating | after Week 2 | preserved |
| MC feedback firewall | `SIMULATED_MC_OUTCOMES_NEVER_UPDATE_THE_GOVERNED_WEEKLY_RATING_STATE` | frozen |

The cap is `update_margin = sign(actual) * min(|actual|, 25.0)` and it lives
**inside the update calculation only**. The final score and the actual game
margin are inputs to it and are never written back — a test passes a 59–17
scoreline through the residual path and re-reads the record to prove it.

The 10-slot rule is a reporting threshold, not a bound. A 40-slot move emits
`LARGE_WEEKLY_RANK_MOVE` carrying team, prior rank, new rank, slot change,
underlying point change, performance residual and cap-hit status — and the move
itself stands at 40. There is deliberately no code path that adjusts a rank.

---

## 3. Recent form: residual, never result

```text
performance_residual = observed_update_margin - expected_margin   # capped at ±25
weight(k)            = lambda ** k                                # k = 0 is most recent
```

Lambda candidates are exactly `FAST 0.60`, `MEDIUM 0.75`, `SLOW 0.90`, and all
three enter the sweep. `reject_win_loss_as_residual` refuses `"W"`, `"L"`, `"T"`
and their long forms, and refuses booleans too — `True` would otherwise slip
through as `1.0`.

The two cases the ruling names are pinned as tests:

* beating a 30-point underdog by 3 → residual **−27**, signal negative;
* losing by 2 as a 21-point underdog → residual **+19**, signal positive.

The signal is the weight-normalized mean of the history, so a five-game and a
twelve-game run of the same residual produce the same pressure rather than the
longer run simply accumulating more of it.

---

## 4. The 500-path design matrix

`3 coefficient × 3 game-SD × 3 lambda × 500 paths = 13,500` simulated paths —
an **experiment workload**, not a 13,500-path production season. Every cell
consumes the same frozen post-Week-2 state and the same common seed schedule,
and no cell's simulated outcomes reach another cell or the frozen state.

The total is derived from the axis sizes rather than written down, so changing
an axis cannot leave a stale count behind.

`executable_now` is `false`. Two of the three axes are bound; the third is not.

### 4.1 Coefficient axis — reserved, not invented

The instruction says to reuse an existing declared search universe rather than
invent one. It was searched for:

| Location | Finding |
|---|---|
| `config/.../experimental/calibration_regimes.json` | `regimes: []`, and the file's own governance block says the emptiness is deliberate — "authoring them would invent calibration data" |
| `config/.../v3_experimental.json` | coefficient is `null` |
| `V3_CALIBRATION_DATA_CONTRACT.json` | declares required fields; records the coefficient as unidentifiable without a named rating-to-margin transform. No candidate values |
| `V3_CALIBRATION_EVIDENCE_DISCOVERY_R5.json` | evidence discovery. No universe |
| `calibration.py` | regime/experiment machinery. No values |

So the axis reserves three deterministic slots — `LOW / MIDDLE / HIGH` — and
binds no numbers. `coefficient_candidates()` with no universe raises
`COEFFICIENT_SEARCH_UNIVERSE_SOURCE_MISSING`. Supply a governed universe and the
refinement is deterministic (sorted → min / median / max) with the full source
universe carried alongside the result.

The selection preference — *the lowest coefficient producing meaningful weekly
responsiveness without pathological oscillation* — is recorded as prose.
`selection_threshold_numeric` is `null` on purpose: converting it to a number
here would invent the selection rule the Chairman reserved for review.

All fourteen required diagnostics are declared, from mean absolute weekly point
movement through to probability volatility.

### 4.2 Game-SD axis — the fallback grid applies

The synthetic 2024/2025 generating provenance was inspected first:

* the 2024/2025 prior enters the model **only as rating carry-forwards**
  (TrueSkill `μ2026 = 25 + 0.70·(μ2025 − 25)`, 2025 Baxter ridge, Litkenhous
  offseason adjustment). The population statistics on that sheet are per-family
  *rating* SDs, not game-result dispersions;
* the 2025 Baxter margin fit is the closest thing to a generating process, but
  only its derived rating columns are mounted — the fit artifact itself is not in
  the repository, so no residual dispersion is recoverable from bytes;
* the `Normal(0, 20.2)` in `V2_1_STATIC_CONTROL!Methodology` is the **2026**
  control's own dispersion, carrying the superseded 4.0 HFA, and traces to
  `ENG-CAL-MARGIN` — an OPEN item recorded as *above* its own 16–18 band.

No defensible independent generator game-SD exists, so the Chairman-approved
fallback grid governs: **LOW 16.0 / MIDDLE 20.0 / HIGH 24.0**, under identical
common seeds. Had a generator SD existed, the grid would be 0.80× / 1.00× /
1.20× of it; that branch is implemented and tested rather than merely described.

`sigma_elo = 68` is refused by name. It is `CCG-SIGMA_ELO`, "Rating uncertainty
per iteration" in the Elo namespace — a different axis, and preserved in the
artifact as `REFUSED_WRONG_AXIS` rather than quietly omitted.

---

## 5. FCS adapter — `FCS_ADAPTER_INPUT_ELO_VECTOR_MISSING`

The approved method is recorded and implemented:

```text
FCS_ELO_Z            = (1250 − mean(FBS_2026_ELO)) / sd(FBS_2026_ELO)
FCS_V3_NEUTRAL_POINTS = 14.0 × FCS_ELO_Z
```

It cannot be evaluated, because its one input does not exist in the mounted
corpus. What was searched:

| Candidate | Why it is not the vector |
|---|---|
| `2026_CFB_..._Unified_Power_Ratings.xlsx!Master Ratings` | The current V3 rating axis: 78 columns over 121 FBS teams — TrueSkill, Litkenhous, Board, Baxter, Billingsley, Markov, Unified Master Z, Unified Neutral-Field Points. **No Elo column at all.** |
| `POWER_CRUNCH...!Reconciled Master.scheme_master_primary_elo` | The only per-team Elo in the corpus. Its own Build Manifest states `primary_elo = 999.986237 × board_power_H + 1099.999878` — the Board I-H axis re-expressed, i.e. the closed route. Also 134 entities rather than 121, `rating_authority = BOARD_I-H`, and `model_use_authorized = FALSE`. |
| `2025_Preseason_Elo_CARRY_v1.xlsx` | `REFERENCE (UNRATIFIED)`, "REJECT FOR CURRENT USE", `R-ELO-01`/H1 blocks adoption. Historical 2025, and not mounted here in any case. |
| `CCG-HFA_ELO 65` / `CCG-SIGMA_ELO 68` / `CCG-R_REF 1893.3` | Elo-layer scalars. Parameters, not a team population; they convert nothing. |

So `compute_fcs_adapter()` fails closed naming the dependency, and no numeric
adapter candidate is frozen. `locate_governed_2026_fbs_elo_vector()` exists as
the single seam a later lane mounts a real vector through, so the adapter cannot
grow an inline fallback.

The SD convention is likewise unresolved and is **not defaulted**: it must match
the governed 2026 Elo population definition, and that definition is exactly what
is missing. Supplying a vector without stating `POPULATION_SD_DDOF0` or
`SAMPLE_SD_DDOF1` is refused, as is supplying one without naming its source.

This missing calculation invalidates nothing else. Every other ruling in the
round is complete, and `blocks_other_rulings` is `false`.

### 5.1 FCS home-field advantage

`+3.5` to the designated home side of every non-neutral governed game, `0.0` at
a neutral venue, unchanged when the home side is a schedule-only FCS entity.
`venue_adjustment_points(neutral=...)` takes no team argument — a signature that
accepted one would be the seam a per-team modifier entered through — and
`reject_fcs_specific_hfa` refuses any modifier, including the plausible `1.0`
that POWER_CRUNCH carries for every FBS team.

---

## 6. What this lane deliberately did **not** do

The preseason decay ruling disagrees with what is mounted. The configuration
still carries the earlier placeholder schedule, which reaches `0.00` after Week 5;
the ruling sets `0.50 / 0.40 / 0.30 / 0.20` for Weeks 3–6 and a `0.15` floor
thereafter, and states the prior never reaches zero during the 2026 season.

This lane **records authority and builds specifications**; promotion is a
separate lane with its own gate. So the configuration is left exactly as
audited, and the disagreement is written into
`config_alignment_required` — naming both `v3_experimental.json`'s `prior_decay`
and `config.py`'s `DEFAULT_PRIOR_DECAY` / `prior_weight_after_week`, with
`promoted_by_this_lane: false` on each. A test asserts the disagreement is live
and recorded, so it cannot be forgotten and cannot be silently resolved.

The same holds for the blowout cap: `calibration.blowout_treatment` remains
`null` and remains a blocker. All six calibration gates are still null and V3
execution is still blocked, which a test also asserts.

Also not done, per the instruction: no final 500 DEV, 2,000 ANALYSIS or 10,000
PUBLISH run; no coefficient, game-SD or lambda promoted; Agent-3's regularization
result untouched and un-pre-empted; no real data mixed into the synthetic fit; no
historical evidence rewritten; `main` not merged.

---

## 7. Identifiers and lineage

The rulings carry locally assigned `MDR1-` convergence IDs. `R1_` is already
taken by the round-1 *blocker audit* baseline in `blocker_report`, and
`R2-`/`R3-`/`R4-` belong to the governance convergences in `rulings.py`. These
are model-design rulings from a different instruction, so they carry their own
prefix and their own tuple, and are deliberately **not** folded into
`rulings.ALL_RULINGS` — merging two lineages would make the succession
unreadable in the one place it has to stay readable.

`chairman_ruling_id` is `null` on all seventeen. The instruction issued the
decisions but supplied no Chairman ruling identifiers, and one is never invented.
The artifact's `containing_commit_sha` is `null` for the same reason it is in the
governance-status artifacts: a committed file cannot contain the SHA of the
commit that contains it.

---

## 8. Verification

The artifact is emitted by `chairman_model_design_r1.write_rulings` and compared
to the committed file **byte for byte**, so the JSON and the code cannot drift.
Emission is LF-pinned and repeat-stable, and the file is registered in the
runtime-portability governed-artifact list.
