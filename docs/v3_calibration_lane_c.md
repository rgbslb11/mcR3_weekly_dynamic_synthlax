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

---

## 9. Successor — ruling R6-CAL-TEMPORAL-ORDER

Everything above is the lane record as issued and is not rewritten here. One
clause of the contract has since been reissued, and this section says which and
why, so the SHA recorded in section 3 is read as the *first issue* rather than
as the current file.

**What was wrong.** The contract required `event_time` of every observation. The
governed historical corpus does not carry one for every observation: the staged
calibration evidence census found zero authentic time-of-day values, 2006 and
2007 survive only as canonical source-row sequence, later historical seasons
carry date/week/source-order evidence as available, and the modern 2024/2025
walk-forward evidence is ordered by date and stage. The historical source
packages state that chronology was not invented.

So the clause as written offered a supplier two options, and both were bad. One
was to withhold real ordering evidence. The other was to generate a noon
kickoff — and a fabricated instant cannot be told apart from a measured one once
it is written down.

**What changed.** `event_time` becomes *conditional*, not optional:

- where a source recorded a timestamp, `event_time` remains authoritative;
- where a source recorded none, `event_time` MUST stay null and no synthetic
  noon, midnight or other default may be generated;
- such an observation may instead be admitted on governed temporal order, with
  precedence exactly `EXACT_EVENT_TIME` > `EXACT_GAME_DATE` > `WEEK_STAGE_DATE`
  > `GOVERNED_SOURCE_SEQUENCE`;
- and it must carry `temporal_order_basis`, `temporal_order_key`,
  `temporal_order_source` and `temporal_order_source_sha256`, all four or none,
  so the ordering claim is re-checkable against pinned bytes.

The causal-order guarantee `event_time` carried is replaced rather than dropped.
`require_temporal_split_integrity` still governs datasets that carry real kickoff
times, and its behaviour for those datasets is unchanged; it now routes each
supplied `event_time` through the same admission gate rather than comparing bare
strings, so it cannot admit a value its successor would refuse. That successor,
`require_governed_temporal_split_integrity`, proves the same forward-only
property across mixed granularities without ever comparing across granularities
it does not have: inside one ordering domain it compares native values at the
coarser of the two granularities involved, and across domains it can prove
ordering only by season. Where two splits hold same-season observations in
different domains the boundary is unprovable and is refused rather than assumed,
and same-day ordering is never claimed under day granularity.

### 9.1 The ordering value is named fields, not a grammar

The first cut of this work packed a WEEK_STAGE_DATE value into
`<anchor-date>|<STAGE>|<WW>`. That was wrong twice over. The ruling authorised
temporal semantics, evidence precedence, provenance and anti-fabrication
behaviour; it did not authorise a key grammar, and a format chosen for
serialization convenience would have become a governance rule nobody issued.
Worse, it did not fit the evidence. The staged corpus carries:

| Span | What the source actually records |
|---|---|
| 2006–2011 | `chronology_sequence` on every row; a week that is sometimes an ordinal and sometimes a label such as `P1`; a game date resolved on some rows and not on others; a quality flag and tier saying which |
| 2024–2025 | `game_date`, `event_order`, `global_sequence`; week labels `0`–`15` and `PS`; phase labels including `CCG`, `Bowl`, `QF`, `R1`; **undated** postseason rows carrying a stage label and a sequence and no date at all |

A mandatory anchor date could not represent a week-ordered row with no date —
the exact 2008 shape — without inventing one, which is the thing the ruling
forbids. And a fixed stage vocabulary would have had to rank `P1` against `PS`
against `Bowl`, a precedence no source states.

So the ordering value is `TemporalOrderValue`: named, separately validated,
source-derived fields — `season`, `game_date`, `week_ordinal`, `week_label`,
`stage_label`, `sequence` — serialized as a self-describing canonical JSON
object. A positional packed string is refused rather than parsed. `week_label`
and `stage_label` are carried verbatim as provenance and are **never** parsed for
ordering; only a source-supplied `week_ordinal` orders anything, and a row that
has only a label falls back to `GOVERNED_SOURCE_SEQUENCE`. A bare `YYYY-MM-DD`
under `EXACT_GAME_DATE` and a bare integer under `GOVERNED_SOURCE_SEQUENCE` are
still accepted, because each of those directly *is* the evidence.

Ordering domains follow from what the value can actually prove: dated evidence
lands in `CALENDAR`, dateless week evidence in a source-scoped `SEASON_WEEK`
domain, and a source sequence in its own source-scoped domain. A
`GOVERNED_SOURCE_SEQUENCE` value may not carry a `game_date` at all — that would
silently upgrade sequence evidence to date-level evidence.

### 9.2 One executable door

`register_dataset` is registration only. It establishes identity, digest, record
count, shape and column admissibility, and it reads no observation values, so a
registered dataset is not an admitted one. The single executable entrypoint is
`load_admitted_observations`, which re-verifies the registered digest, admits
every row through the temporal gate, proves the partition forward-only, and
returns an `AdmittedObservationSet`. That type *is* the receipt: it carries a
private construction token, so it cannot be forged by a caller who skipped the
gate, and no public function returns raw observation rows from a registered
dataset. Consumers call `require_admitted_observations`, which refuses a
`CalibrationDataset` handed over in its place. The invariant is:

    executable calibration observation
        -> temporal admission
        -> temporal split validation
        -> calibration use

### 9.2.1 Where the chain terminates

Stamping was not enough. A bound promotion record that carries
`observations_admitted: False` is still promotion-eligible evidence, and a caveat
inside a promotion-eligible record is read by nobody at the moment it matters. So
`bind_promotion_evidence` fails closed: a bound result requires the
`AdmittedObservationSet` the loader issued **for those exact bytes**. The full
chain, and where each link is proven:

| Link | Proven by |
|---|---|
| registered source | `register_dataset` |
| digest verified | `load_admitted_observations`, and again by `_require_digest_continuity` at binding |
| rows temporally admitted | `admit_observation_temporal_order` |
| partition proven forward-only | `require_governed_temporal_split_integrity` |
| calibration/scoring result | `ExperimentRecord` |
| promotion evidence binding | `bind_promotion_evidence` |

There is no supported route from the first link to the last that skips the middle
three. Three things are refused by name: a bare `CalibrationDataset` handed over
where the receipt belongs; a receipt issued for other bytes; and an evidence
payload that *asserts* admission — `observations_admitted`, `rows_admitted` and
their spellings are rejected outright, because admission is established by the
receipt and by nothing else. Binding also re-hashes the file, so a receipt issued
before the bytes changed is stale and cannot be reused.

The unbound path survives exactly as it was, and is now explicitly marked
`promotion_eligible: false`. It is the only route that works without a receipt,
and it is the one that claims nothing.

The fixture that used to exercise bound binding registered a dataset with no
temporal columns — a shape this ruling no longer admits. It was updated rather
than kept working: a fixture that can only be bound by skipping the gate is a
fixture that documents the bypass. It now carries the smallest valid temporal
evidence the contract admits, and it is a fixture, not calibration data.

One boundary is worth stating plainly. `_ADMISSION_TOKEN` is module-private.
That stops a supported or accidental bypass — the failure mode that actually
happens, where a caller reaches for the type because it is what the consumer
wants. It is not a hostile-code security boundary and is not treated as one.

### 9.3 Anti-fabrication is structural

`refuse_default_time_of_day_fill` is a diagnostic and is not the correctness
boundary. Every required refusal is enforced one row at a time, by consistency
between the claimed source evidence, the declared basis, the provenance and the
supplied temporal fields:

- a coarse-basis observation may not carry a time of day in any field;
- an `event_time` may not stand beside a basis weaker than `EXACT_EVENT_TIME` —
  one of the two must have been manufactured;
- `EXACT_EVENT_TIME` may not be declared without an `event_time`;
- the declared basis and the supplied value representation must agree;
- alternate ordering requires complete, re-checkable provenance;
- `GOVERNED_SOURCE_SEQUENCE` may not carry a `game_date`.

A test neutralises the detector and shows that nothing new gets in. Note what is
*not* claimed: nothing here proves that a timestamp asserted to be authentic is
historically true. Software cannot infer that. What it enforces is consistency,
which is what a fabricated value has to break — because it has to be declared as
something.

`GOVERNED_SOURCE_SEQUENCE` establishes relative causal order only. It is never
serialized as an inferred kickoff timestamp: `ResolvedTemporalOrder.as_dict`
emits `event_time: null` and an explicit `inferred_kickoff_time: null` for it.

**What did not change.** No dataset is mounted. Random split stays prohibited,
the holdout stays `SCORED_ONCE_AT_THE_END_NEVER_FOR_SELECTION`, Baxter Rating
RMSE stays the primary out-of-sample objective, Colley and SRS stay separate
witnesses with no weighted composite, FLOW/public-money and injury inputs stay
refused, margin SD 20.2 stays unapproved, all six calibration values stay
unresolved and the execution blocker count stays at eight.

The four `temporal_order_*` columns were added to the governed observation
allowlist **because the ruling requires them**, not because a fit wanted them.
The four fields in section 6 are unchanged and still unadmitted.

Artifacts: `V3_CALIBRATION_DATA_CONTRACT.json` is reissued as contract revision
`R1-TEMPORAL-ORDER-SUCCESSOR` under the same contract ID, so the section 3 SHA
`d2b015be…` is the first-issue value and no longer matches the file.
`V3_CALIBRATION_TEMPORAL_ORDER_SUCCESSOR_R1.json` is the successor evidence and
status record, and carries the audit remediation record for 9.1, 9.2 and 9.3.

The whole-season partition the corpus would be split into — training 2006–2011,
validation 2024, holdout 2025 — is proven *representable* by test, over a
training half that mixes all three kinds of historical evidence. That is a
structural claim only: no dataset is mounted, no adapter is built, nothing is
scored, and it is not a promoted calibration policy.
