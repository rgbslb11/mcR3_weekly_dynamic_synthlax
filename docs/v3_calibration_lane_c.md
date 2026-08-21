# OPERATION SYTHALAX — Post-Freeze Lane C

## Dynamic Weekly Calibration

Branch: `claude/v3-calibration`
Frozen base: `eb5e3e7f546217809a94692bf0e502882b7d51c0`
Disposition: **BLOCKED ON GOVERNED DATA — HARNESS HARDENED, CONTRACT ISSUED**

Owned blockers, all seven still open:

1. `calibration.weekly_performance_residual_coefficient`
2. `calibration.weekly_movement_cap_points`
3. `calibration.recent_form_weights`
4. `calibration.blowout_treatment`
5. `calibration.game_sd_points`
6. `calibration.sample_size_regularization`
7. `governance.GAME_SD_CALIBRATION_OPEN`

No parameter was promoted. No experiment was run, because no experiment could
be run against evidence.

---

## 1. Baseline reproduction

`409` full-suite tests and `350` V3 tests reproduce exactly at the frozen base.

Two environment defects had to be cleared first, neither of which is a repository
defect:

- `sqlalchemy` and `alembic` are declared in `pyproject.toml` but were absent
  from the interpreter, so `tests/test_models.py` failed at collection and
  aborted the whole run. Installed at the declared bounds.
- `pytest`'s default `basetemp` under `%LOCALAPPDATA%\Temp` was not enumerable,
  so every `tmp_path` fixture errored at setup. Runs use an explicit
  `--basetemp`.

---

## 2. Harness audit

Confirm or refute, against the code rather than the build report:

| Claim | Verdict | Evidence |
|---|---|---|
| Dataset registration exists | **CONFIRMED** | `calibration.register_dataset` — format-aware, fail-closed, SHA-256 recorded |
| Experiment ranking exists | **CONFIRMED** | `calibration.rank_experiments` |
| Promotion gate exists | **CONFIRMED** | `promote_regime`, `promote_regime_r2`; approval token required in both |
| Train/validation/holdout separation exists | **CONFIRMED, INCOMPLETE** | `require_split_separation` proved disjointness only, and was wired to nothing |
| Objective is Baxter OOS margin RMSE | **CONFIRMED, UNENFORCED** | `PRIMARY_CALIBRATION_METRIC` correct; `require_primary_objective` existed but no ranking path called it |
| Witnesses are independent | **CONFIRMED** | `INDEPENDENT_WITNESSES`, `reject_witness_composite`; ACC-EXT-12 blend recorded NOT ADOPTED |
| Forbidden FLOW protections exist | **CONFIRMED** | `FORBIDDEN_SIGNAL_PATTERNS` matched as substrings, so renaming a column does not evade the denylist |
| Promotion requires explicit approval | **CONFIRMED, WEAKLY BOUND** | Token enforced; the *evidence* behind a mathematical promotion was an unvalidated caller-supplied dict |

The harness was sound in design. Seven reachable gaps were confirmed by direct
probe, each closed and each now covered by a test:

1. `rank_experiments` ranked against any named metric, so a regime could be
   declared best under a criterion chosen after seeing the results.
2. `ExperimentRecord` carried no split, so a training score and a holdout score
   were indistinguishable in the provenance record.
3. `promote_regime_r2` accepted a hand-written
   `{out_of_sample_baxter_rating_rmse: 0.0001, split: "holdout"}` and returned a
   valid mathematical-authority promotion. Nothing tied that number to a
   measurement.
4. `rows` counted physical lines, so a quoted embedded newline overstated a
   governed dataset's size.
5. Ragged rows registered successfully; field-wise reads of them return whatever
   sits at the index.
6. A conforming header with zero observations registered as a mounted dataset.
7. Duplicate columns registered; which copy a reader takes is positional.

Gap 3 is the serious one. It let the mathematical-authority branch — the branch
that exists specifically to require measurement — be satisfied by typing.

---

## 3. What was changed

All changes are calibration-owned. **`config.py` was not modified**, neither
`src/ncaaf_engine/config.py` nor the V3 `config.py`. The canonical
`v3_experimental.json` is untouched and its six calibration values remain `null`.

- `calibration.py` — the seven fixes above, plus `rank_experiments_governed`,
  `bind_promotion_evidence`, and `require_temporal_split_integrity`.
- `calibration_contract.py` — new; the ingestion contract.
- `test_calibration_contract_and_hardening.py` — new; 31 tests.
- `V3_CALIBRATION_DATA_CONTRACT.json` — new; the contract as a reviewable
  artifact, deterministic, SHA-256
  `d2b015bef5eb2649161227c89801bee135db85439fe42b4bedecaef552b36c79`.

An unbound promotion is still permitted, because ruling R2-CAL-OBJECTIVE does
not forbid it and this lane has no authority to tighten a ruling. It is now
stamped `EVIDENCE_UNBOUND_NOT_SUFFICIENT_FOR_CANONICAL_WRITE` in its own
provenance record, so the weaker path cannot later be mistaken for the stronger.

---

## 4. Data inventory

### AVAILABLE GOVERNED DATA

| Artifact | Content | Usable for calibration? |
|---|---|---|
| `2026_FBS_Schedule_LOCKED_v5.xlsx` | 743 fixtures (736 REG + 7 CCG) | **No.** Zero score columns. Fixtures are the question, not the answer. |
| `2026_CFB_..._Preseason_Unified_Power_Ratings.xlsx` | 121-team preseason priors | **No.** Predictors with no outcomes attached. |
| `POWER_CRUNCH_..._Master_134_v2_2.xlsx` | 134-entity identity reconciliation | **No.** Identity only; no games. |
| `Model_Parameters_v2_5_APPROVED.xlsx` | Parameter/governance registers | **No.** Records that margin-SD calibration is OPEN; holds no per-game observations. |
| `aac_divisions_2026_R2_SUCCESSOR.csv` | AAC 8/8 membership | **No.** Structure, not results. |

### AVAILABLE NON-GOVERNED RESEARCH DATA

| Artifact | Content | Status |
|---|---|---|
| `V2_1_STATIC_CONTROL_...Monte_Carlo.xlsx` | 10,000 synthetic seasons | **Simulation output.** Registering it would score the engine against its own beliefs and report the result as accuracy. |
| `Model_Parameters_v2_5!17_V3_COMEBACK_RESEARCH` | 12 comeback-bucket targets | Marked `ACCEPTED AS RESEARCH INFORMATION` / `NOT IMPLEMENTED / NOT VALIDATED`. `PCV3-CB-12` states the board recomputes *on real-2025 ingestion* — direct evidence that real 2025 results have never been ingested. |
| `Model_Parameters_v2_5!CALIBRATION` | Target bands vs achieved | Achieved margin SD `20.2` against band `16–18`, from the Jul 13–14 engine run. |

### MISSING REQUIRED DATA

**A historical game-result observation set. It does not exist in this
repository in any form.** The only CSV present is the AAC divisions file. No
parquet, no JSONL, no database, no results sheet in any workbook.

---

## 5. Two prior measurements, independently checked

**Margin SD `20.2` — verified, and verified as *not* promotable.** It appears in
`Model_Parameters_v2_5!CALIBRATION` as the *achieved* value of a July engine run,
explicitly annotated "Above band", against that sheet's own `16–18` target. It is
an engine self-observation, not a historical measurement, and open item
`ENG-CAL-MARGIN` keeps it open. Two of four recorded achieved metrics on that
sheet fall outside band. Nothing in this lane admits it.

**Baxter 2025, 757 games, OLS RMSE `11.3026`, ridge 0.1 `11.3080` — NOT
VERIFIABLE.** A full-text search of the repository returns no such measurement.
The only `757` matches are `talent_pts_757` (a 247Sports talent-points field) and
a substring of an unrelated SHA-256. There is no 2025 season dataset, no
regression output, and no artifact recording an RMSE of `11.3026`. These figures
may well be correct, but **they arrive from outside the evidence set and this
lane cannot corroborate them.** They were not used.

---

## 6. The calibration-data contract

Full machine-readable form: `reference/dynamic_weekly_mc_v3/V3_CALIBRATION_DATA_CONTRACT.json`.

Twenty required fields, each carrying the coefficient that needs it and the
provenance that makes it admissible. Four of them are *not* in the governed
observation allowlist and are raised as **ruling requests, not additions** —
widening the allowlist because a fit needed the column is exactly how an
unreviewed signal enters a governed model:

| Field | Needed by | Why it cannot be skipped |
|---|---|---|
| `games_played_to_date` | `sample_size_regularization` | The coefficient is a function *of* this count. Today it is only reachable inside the opaque `prior_rating_state` blob, so the shrinkage schedule would be fitted against a field no reviewer can see. |
| `game_type` | `blowout_treatment`, `game_sd_points`, `recent_form_weights` | V3 freezes strength after Selection Day. Without it, a bowl blowout is fitted as though it were a Week 4 result. |
| `overtime_periods` | `game_sd_points`, `blowout_treatment` | College overtime manufactures margins no pregame model predicts. Folding them into an untagged residual pool inflates game SD — **the exact direction of the unexplained 20.2.** |
| `opponent_division` | `game_sd_points`, `blowout_treatment`, `sample_size_regularization` | The FCS-to-V3 point scale is itself an open blocker. Until it closes, FCS games must be identifiable so they can be excluded rather than fitted on an unresolved scale. |

Two whole-dataset provenance requirements deserve emphasis, because without
either one the primary coefficient is unidentifiable rather than merely noisy:

- **`rating_scale_declaration`** — the units of `pregame_team_rating` and
  `expected_margin`. A residual computed across two scales is arithmetic, not
  evidence.
- **`expected_margin_transform`** — the named rating-to-margin transform. Without
  it, any residual can be explained by re-scaling the transform instead of by
  `weekly_performance_residual_coefficient`, and the two are not separable.

**Split policy is temporal only.** Weekly reratings are a sequential process; a
randomly assigned holdout sits earlier in time than training games that already
absorbed its result, so its measured "out-of-sample" error is nothing of the
kind. Holdout is scored once, at the end, never for selection.

**Minimum volume:** ≥3 distinct seasons (three ordered partitions need three
seasons), ≥1500 observations total, ≥300 holdout, ≥8 weeks per team per season.

**Refused outright:** any public betting flow, handle, ticket or steam signal
under any spelling; any injury adjustment; and any synthetic or simulated
observation set.

---

## 7. Why no experiments were run

Step 6 of the lane instruction governs. No governed calibration observation
dataset is available, so no experiment was run, no candidate surface was
produced, and no parameter was promoted.

`config/dynamic_weekly_mc_v3/experimental/calibration_regimes.json` still ships
zero regimes. Authoring candidate coefficient values with nothing to score them
against would be inventing calibration data, which is the specific prohibition
this lane exists to respect. An empty regime list is the honest state.

---

## 8. To unblock

Supply an observation set satisfying the contract, then:

1. Obtain a ruling admitting the four unadmitted fields, or an explicit ruling
   that each is excluded and how the affected coefficient is identified without it.
2. Register it via `calibration.register_dataset` — SHA-256 and record count are
   recorded at registration.
3. Prove the partition with `require_temporal_split_integrity`.
4. Score candidates and rank with `rank_experiments_governed`.
5. Report Colley and SRS independently. Never blended.
6. Bind promotion evidence with `bind_promotion_evidence`.
7. Promotion remains a human-controlled gate under ruling R2-CAL-OBJECTIVE.
   Nothing above promotes anything.
