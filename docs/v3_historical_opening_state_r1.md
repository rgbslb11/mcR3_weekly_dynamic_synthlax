# OPERATION SYTHALAX — Historical Opening State (R1)

Branch: `claude/v3-historical-opening-state-r1`
Frozen base: `5479f2ae7687c36c0ed4117334171289693dd5c9`
Disposition: **BLOCKED ON COMPONENT EVIDENCE — CONSTRUCTION MIRRORED AND PINNED**

Machine-readable artifacts: `reference/dynamic_weekly_mc_v3/historical_opening_state_r1/`.

No parameter was promoted, no blocker retired, no allowlist widened, no canonical
writer built, no FCS point adapter installed, no football point emitted, and no
season Monte Carlo run.

---

## 1. The short version

The V3 preseason construction was verified against its own workbook and
reimplemented exactly. It reproduces all 121 published 2026 Unified Master Z
values to within 1e-12, from the native columns, through the same weights.

It cannot be run for 2021, 2022, 2023 or 2024, because **all four component
families begin at the synthetic 2025 season or later**. This is not a gap in
the search. It is a property of the rating lineage: the TrueSkill chain is
*initialised* at 2025 Week 1 with an equal prior of mu 25 for every team, and
Litkenhous, Pure Baxter and both boards each trace back to 2025 or 2026
artifacts. There is no earlier state to carry forward, because there was never
an earlier state.

Two artifacts carry a 2021-2024 label and neither is a preseason rating. Both
are fits over their own season's games.

So the answer to "can the historical opening state be supplied" is: the method
is ready and pinned by test; the inputs do not exist. Those are different
findings and separating them is the result of this lane.

---

## 2. What the 2026 construction actually is

Verified from `2026_CFB_2026_Preseason_Unified_Power_Ratings.xlsx`
(SHA-256 `4b253545…30807a4a`), and encoded in
`historical_opening_state.V3_PRESEASON_FAMILIES`.

| Family | Weight | Native field |
|---|---:|---|
| TrueSkill | 0.25 | `TrueSkill 2026 Preseason μ` |
| Litkenhous | 0.25 | `Litkenhous Adjusted Power` |
| Pure Baxter | 0.25 | `2026 Pure Baxter Rating` |
| Board family | 0.25 | mean of standardized Board I-H and Board J-B |

`Unified Master Z = Σ weight × family Z`.
`Unified Master Power Index = 100 + 10 × Z`.
`Unified Neutral-Field Points = 14 × Z`.

The lane instruction's description was correct. Two details of it were only
recoverable by recomputing the workbook, and both matter for a reconstruction.

**The divisor is the sample standard deviation, `ddof=1`.** The workbook's own
sheet titles that block "Population Statistics". Reading the label as a
specification gives a different number for every team: over the 121-team field
the population deviation for TrueSkill is `4.3412374`, and the value the
workbook divides by is `4.3592884`. Recomputing with `ddof=1` reproduces every
published family Z to within 1e-14; `ddof=0` reproduces none of them. This is
recorded as measured, not as documented, and
`test_the_divisor_is_the_sample_deviation_and_the_population_one_would_be_wrong`
asserts both halves so the wrong reading cannot creep back in.

**The board family is an average of two Z scores, not a Z score of an
average.** Board I-H and Board J-B are standardized separately against their
own field deviations (`0.14339719` and `0.12762457`) and then averaged.
Standardizing the mean of the two natives instead is a different number,
because the two natives have different dispersions.

Both are pinned against the workbook itself rather than against constants
copied into a test, so a replacement workbook that changes the rule fails the
suite instead of silently changing the meaning of every historical value built
on the old one.

---

## 3. Why 2021-2024 cannot be reconstructed

Every candidate is in
`historical_opening_state_source_manifest.json` with its digest and its refusal.

### TrueSkill — no state exists before 2025

`Operation_Sythalax_TrueSkill_2025_2026_Thread_Consolidation.xlsx`
(SHA-256 `4b7d84d8…6c7dfc79`) is the whole TrueSkill lineage. Sheet
`21 2026 P0 Params` records `population_mu 25` and `population_sigma 8.333333`
as the **initial** prior, and sheet `14 2025 Rating History` shows every 2025
Week 1 row carrying `pregame_mu 25` and `pregame_sigma 8.333333` for both
participants. The 2025 season opened with an equal prior for all teams.

The 2026 transition is `mu_2026 = 25 + 0.70 × (mu_2025 − 25)`, which consumes a
2025 posterior. An equivalent 2021 opening state would need a 2020 posterior.
None exists, and by the chain's own construction none ever did.

### Litkenhous — chain starts at 2025

`2026_Synthetic_FBS_Litkenhous_Preseason_Three_Layer.xlsx` carries an
*Inputs and Lineage* sheet naming exactly one rating input: the 2025 final
ratings. Its Methodology sheet defines pure carryover as "60% of each team's
2025 Litkenhous power margin after recentering the 2026 field". No 2020-2023
Litkenhous rating was located anywhere on the filesystem.

### Board I-H and Board J-B — 2026 only

Every located board artifact — I-H, I-I, I-K, J-A, J-B, J-C — is 2026. There is
no 2021-2024 board of any letter.

### Pure Baxter — the near miss, and why it is refused

`Baxter_Ratings_2024.csv` (SHA-256 `b7d3e084…9863920b`) is the most tempting
artifact in the register. It carries a 2024 label and a Baxter rating, which at
a glance is a component family for a season in scope.

It is a ridge fit over 2024's own games. Its header carries a `games` column and
its first rows read `Notre Dame … 14` and `Ohio State … 12` — counts obtainable
only after the season. The package README states the coverage plainly:
2006-2011, 2024, 2025.

A 2024 *preseason* Pure Baxter would have to carry a 2023 fit forward, the way
the 2026 value carries 2025 forward. There is no 2020, 2021, 2022 or 2023 fit to
carry. So even the one family with a 2021-2024-labelled artifact has no
preseason value for any season in scope.

### The one leak-free opening state on disk, and why it is worthless

`pregame_states_2024_2025.csv` is a genuine walk-forward state with no leakage.
Its season-opening rows carry **exactly one distinct value across both seasons**:
`elo_a_pre` and `elo_b_pre` are `1500.0` for every team in 2024 week 0, and
likewise at the start of 2025. The package's own `season_config_2024.json`
explains why — `preseason_prior: false`, `previous_season_carryover: false`.

A population with zero dispersion has no deviation to divide by.
`population_mean_sd` refuses it explicitly rather than returning zeros, because
zeros would read as "every team is exactly average" rather than as "this source
says nothing". It is also a foreign scale — research Elo, base 1500 — and not
any of the four families.

---

## 4. Population: unresolved, and the disagreement is the finding

Z scores are defined only against a population, so this is not a detail.

Two sources state a historical population and they do not agree.

| Season | Conference distribution | Phase5J registry |
|---|---:|---:|
| 2021 | 130 | — |
| 2022 | 131 | — |
| 2023 | 133 | — |
| 2024 | **133** | **118** |

`Synthetic_NCAA_Conference_Distribution_2021_2026.xlsx` (SHA-256
`376a6f62…2588e2ac`) gives a per-season subdivision and conference for 251
entities. Membership is settled before a season starts, so the class is
leakage-clean. But its Methodology sheet names one upstream,
`Synthetic_CFB_2021_2026_Walkover_RERUN.csv`, and a filesystem sweep did not
find that file. The chain is documented and cannot be closed to bytes here.

`team_registry_2024.csv` inside the Phase5J package asserts 118 FBS teams for
2024 under `universe_policy: REGISTRY_ONLY`. The two disagree about membership,
not merely about rating eligibility — the registry carries Colgate and Cornell
as FBS in a conference named ECL.

`resolve_population` therefore returns:

* `UNRESOLVED_SOURCE_NOT_MOUNTED` for 2021, 2022 and 2023 — one candidate,
  lineage open;
* `UNRESOLVED_CONFLICTING_CANDIDATES` for 2024 — two candidates, no ruling.

Three unresolved states are distinguished rather than collapsed into one
because they need different remedies: a missing source needs finding, an open
lineage needs closing, a conflict needs a ruling. And mounting one of two
disagreeing candidates does not resolve the conflict — it only picks a side —
so the resolver refuses that too.

---

## 5. The reconstruction frame, and what "251" means

`historical_membership_frame_2021_2024.csv` (1,004 rows, SHA-256
`ad93c7c7…4c4d08b`) is committed so an auditor without the original workbook can
regenerate every count here from repository bytes. Its provenance file records
the open upstream and the 2024 conflict.

It is labelled `CANDIDATE_FRAME_NOT_AUTHORITY` everywhere it appears. It fixes
which team-seasons are *reported on*; it is not a ratified population, and no
standardization is ever performed over it.

Per season it carries all 251 entities:

| Season | FBS | FCS | Division II | Inactive |
|---|---:|---:|---:|---:|
| 2021 | 130 | 118 | 1 | 2 |
| 2022 | 131 | 117 | 1 | 2 |
| 2023 | 133 | 115 | 1 | 2 |
| 2024 | 133 | 115 | 1 | 2 |

Total team-seasons: **1,004**. Fully reconstructed: **0**. Partially
reconstructed: **0**. Unavailable: **1,004**, each with an explicit reason.

---

## 6. Identity: the synthetic 2026 scope is not historical truth

Historical division and canonical `entity_scope` are kept on separate axes, and
the test suite asserts they disagree in both directions:

* North Dakota St. is `FBS_MEMBER` in the synthetic 2026 master and is FCS in
  all four historical seasons.
* Arkansas St. is `SCHEDULE_ONLY_FCS` in that master and is FBS in all four.

If the canonical scope were leaking into the frame, one of those two would be
wrong. The FBS counts are 130/131/133/133 and never 121, which is the 2026
number.

Binding to the canonical master is by **exact key only** — `schedule_id`,
`team_name` or `abbreviated_name`. No expansion, no punctuation folding, no
nearest match. 420 of the 1,004 rows bind; 584 do not, and every one of them is
**preserved with its division**, because dropping historically valid programs
would silently shrink every population a later lane computes over. `NC St.` is
one of the unbound: any rule loose enough to fold it onto `NC State` is also
loose enough to fold two distinct programs onto one. Binding is refused
outright when two historical entities would land on one canonical id in the
same season.

---

## 7. Week 1 / Week 2 readiness

V3 governance runs Weeks 1-2 off preseason opening strength and promotes the
first rerating after Week 2, so this count is the size of the cleanest
early-season calibration subset obtainable with no in-season state.

| Season | Games with both opening states |
|---|---:|
| 2021 | 0 |
| 2022 | 0 |
| 2023 | 0 |
| 2024 | 0 |

The zero is on **opening-state grounds and holds for any schedule**: no
team-season is `FULLY_RECONSTRUCTED`, so no pair can be. The coverage report
records `schedule_mounted: false` alongside it, because a zero from an absent
schedule and a zero from absent strength are different findings and the next
lane needs to know which one applies. Here it is the second, and mounting a
schedule would not change the count.

A real 2021-2024 schedule does exist in this programme — the sibling lane
`claude/v3-historical-observation-corpus-r6` holds 2,241 NCAA-sourced
observations across exactly these four seasons, with kickoff instants. It is
unmerged, and this lane did not reach across a branch to borrow it, because the
count it would produce is zero either way.

---

## 8. Points, and the decision this lane does not make

No football point value is emitted for any team-season.

`14 × Z` is reproducible and reproduced — the test confirms the workbook's own
`Unified Neutral-Field Points` column equals `14 × Unified Master Z` — and that
is a statement about arithmetic, not authority. The workbook itself calls the
value "Initial points per standard deviation; recalibrate against game
margins", which makes it provisional even for 2026. Reusing it across seasons
is a strictly larger claim and belongs to the parallel expected-margin audit.

`candidate_points_if_14x_z` exists for QA. It refuses to run without
`research_only=True`, and returns a dict rather than a float so the
`NON_AUTHORIZED_RESEARCH_ONLY` stamp travels with the number instead of being
left behind at the call boundary. Nothing in this lane calls it, and no artifact
contains its output.

`opening_unified_z` is emitted in standard-deviation units, which is the form
that makes either later ruling a multiplication rather than a rebuild.

---

## 9. FCS

No opening point strength is derived from Elo 1250 or anything else.
`refuse_fcs_opening_points` raises unconditionally.

The 465 FCS team-seasons in the frame are **preserved** — real participants in
real games — and carried with `OUTSIDE_POPULATION` and no strength. Existence
and strength are recorded separately, because "we saw this program and gave it
no rating" is a different fact from "this program never appeared".

`model_scale.FCS_ELO_1250_TO_V3_POINT_SCALE_ADAPTER` remains open and untouched.

---

## 10. Artifacts

Seven, all deterministic, all LF, all sorted-key JSON, none carrying a
timestamp — a `generated_at` field would defeat the byte-identity requirement on
the second run. Provenance travels in the SHA manifest and in git, both of which
record *when* without putting it inside the bytes being hashed.

| Artifact | SHA-256 |
|---|---|
| `historical_opening_state_source_manifest.json` | `51dedc62e48f48d8752bff09611590521afd0bb15c58239426bba5a800ad4b6b` |
| `historical_opening_state_population_manifest.json` | `39d15723bdf8be73ad55529c73a0165666edb5b61803f670e89d150b5e613daf` |
| `historical_opening_state_standardization_manifest.json` | `3e613d8bd37ef559315a56a11971fa8e32d2e3f635a050952bcea8f9321f3bbb` |
| `historical_opening_state_component_table.json` | `ce4f0c184a3364dfe578642bfc60f06d8a5f8337a00d38cef0e161ab56187bc1` |
| `historical_opening_state_unified_z_table.json` | `fcc6341aefe658e7bbecda3f8966ae2daf53fdda3b28eb6152a9d499707ea1a8` |
| `historical_opening_state_coverage_report.json` | `806aa6a7f96c06a755aa5666d023667c337b0ae4d28fb24ff9c0acd606b18ac3` |
| `historical_opening_state_status.json` | `968262c639a148de441f1c9d20cc3029cad452e510c52f6314763e531a188178` |
| `historical_membership_frame_2021_2024.csv` | `ad93c7c71131c59947d5f84677d10679461e3239e5028ceb03fd04f774c4d08b` |

The frame's digest is checked on load. A frame edited in place would change
every count in every artifact while everything else continued to look
consistent, so a mismatch refuses rather than proceeds.

---

## 11. What Agent 2 can be handed today

If the point-axis question resolves tomorrow, this lane can supply the
*construction* immediately and cannot supply the *values*.

Concretely, the moment a governed 2021-2024 component source is mounted:

1. `standardize_family` produces family Z scores and a full standardization
   record — formula, population, mean, SD, ddof, directionality, missing-value
   handling — with no further derivation from a spreadsheet;
2. `combine_unified_z` produces `opening_unified_z` under the same weights that
   reproduce 2026 exactly;
3. `unified_power_index` applies without a governance gate, being unit-free;
4. if `14 × Z` is ruled historically reusable, the conversion is one
   multiplication over the emitted `opening_unified_z` column, and if it is
   ruled *not* reusable, nothing needs to be withdrawn, because no points were
   ever emitted.

What is missing is not method. It is any measurement of a 2021-2024 team taken
before that team played.

---

## 12. To unblock

1. Supply, or rule on, a **preseason** rating source for 2021-2024 covering all
   four families. Nothing short of all four produces a combined state, by
   design. A source covering fewer families would still be worth mounting — the
   component table carries natives per family — but would yield
   `PARTIALLY_RECONSTRUCTED`, not a unified Z.
2. Close the lineage on `Synthetic_CFB_2021_2026_Walkover_RERUN.csv`, or name a
   different governed historical membership authority.
3. Rule on the 2024 population conflict: 133 by the conference distribution,
   118 by the Phase5J registry. The two disagree about membership, so this is a
   ruling and not a reconciliation.
4. Separately, and not required for this lane: the point-axis question in the
   expected-margin audit, and the FCS adapter.

Item 1 is the binding constraint. Items 2 and 3 matter only once item 1 is
satisfied, because a population is only needed when there is something to
standardize over it.

---

## 13. State

- Tests: **663 full**, **604 V3** — up from 602 / 543 at the frozen base, +61
  new, no existing test modified.
- `config.py` untouched. `v3_experimental.json` untouched; all six calibration
  values remain `null`.
- `V3_CALIBRATION_DATA_CONTRACT.json` untouched; `governed_allowlist` unchanged.
- Blockers: **8 before, 8 after.** None retired, none opened.
- No season simulation of any path count was run.
