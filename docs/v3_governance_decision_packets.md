# V3 Governance Decision Packets

Prepared against `main` @ `3b46e561b8d939e10ba5d6ff2f69923d963a148e`, tested V3 baseline `6353567d`.

V3 remains **EXPERIMENTAL**. Nothing in this document resolves a governance question. Each packet
records the evidence found, the values in conflict, and the consequences of each option, so that a
ruling can be issued from evidence rather than inferred from silence.

Starting blockers: **18**. Legitimately cleared: **1**. Remaining: **17**.

The 17 remaining blockers collapse to **8 distinct rulings**, because several blocker IDs are two
detections of one underlying decision.

| Packet | Blockers covered | Disposition |
| --- | --- | --- |
| [1. Schedule provenance](#1-schedule-provenance) | `provenance.SCHEDULE_GAMES_HASH_REPRODUCTION_MISMATCH`, `provenance.SCHEDULE_BINARY_HASH_MISMATCH_VS_MODEL_PARAMETERS_V2_5` | 1 resolved, 1 missing artifact |
| [2. Thirteen-game exceptions](#2-thirteen-game-schedule-exceptions) | `governance.FIVE_13_GAME_SCHEDULE_EXCEPTIONS_UNRATIFIED` | Human ruling required |
| [3. AAC division membership](#3-aac-division-membership) | `inputs.aac_divisions_csv` | Missing authoritative artifact |
| [4. FCS source authority](#4-fcs-source-authority-and-translation) | `fcs_translation_policy`, `governance.FCS_SOURCE_MODEL_USE_AUTHORIZED_FALSE` | Human ruling required |
| [5. HFA baseline](#5-hfa-baseline-40-vs-35) | `hfa_baseline_points`, `governance.V3_HFA_BASELINE_CONFLICT_4P0_VS_3P5` | Human ruling required |
| [6. Committee strength source](#6-committee-final-strength-tiebreak-source) | `committee_tiebreak_strength_source` | Human ruling required |
| [7. A8/ECL ordering](#7-a8ecl-ordering-circularity) | `governance.A8_ECL_FINAL_BOARD_TIEBREAK_ORDERING_NOT_EXPLICIT` | Human ruling required |
| [8. Quarterfinal mapping](#8-cfp-quarterfinal-mapping) | `governance.POSTSEASON_QUARTERFINAL_MAPPING_NOT_EXPLICIT` | Human ruling required |
| [9. Calibration program](#9-rerating-calibration-program) | six `calibration.*`, `governance.GAME_SD_CALIBRATION_OPEN` | Calibration experiment required |

---

## 1. Schedule provenance

### 1a. Games content hash — RESOLVED BY DETERMINISTIC RECONCILIATION

**Finding.** The mismatch was an implementation defect, not a content defect.

The canonical method is recorded on the schedule workbook's own Certification sheet:

> SHA-256 of Games sheet serialized as UTF-8 CSV with header, LF line endings, and blank for null.

735 of the 743 data rows stop at 12 cells because the trailing `venue_rule` cell is empty; only 8
rows carry all 13. Those absent trailing cells are nulls and the canonical method serializes nulls
as blanks. The previous implementation wrote rows ragged, producing a different CSV and therefore a
different digest. Padding every row to the header width reproduces the certified digest exactly.

| | Value |
| --- | --- |
| Certified (`integrity_sha256`) | `bd8089f70f6d483a75564e33438272c22daade8e53619fb21a915778975ff221` |
| Reproduced after fix | `bd8089f70f6d483a75564e33438272c22daade8e53619fb21a915778975ff221` |

**The certified hash was not altered.** The reproduction logic was corrected to the documented
method. The Games-sheet fixtures are provably the certified content.

Reproduce:

```bash
python -m pytest tests/dynamic_weekly_mc_v3/test_provenance_reconciliation.py -v
```

### 1b. Binary hash — MISSING AUTHORITATIVE DATA

**Finding.** Source-copy mismatch. The fixtures are intact; the artifact custody chain is not.

| | Value |
| --- | --- |
| Registered v5 binary (Model Parameters `19_SCHEDULE_V5_CHANGE`) | `db26c3fff15a61ce8e7efa3b93100fa017e02248c96076d291495b55e855da12` |
| Mounted file | `b0f2c2cdbb3b47fa35bfcffdf4bd04850731355f3a8599a9494673ca9fcc24b8` |
| Superseded v4 binary | `8d4d5112aa52cfb51895c95d104e3c5e1821813e3b481a4f1b3067668d0af57b` |

The mounted file is **not** the stale v4 artifact, and its Games content **is** certified. A
workbook re-save preserves content hash and destroys binary hash; the converse cannot happen. This
is consistent with the mounted file being a re-saved copy of the correct v5 content.

Note that `V3_BUILD_MANIFEST.json` certifies the mounted copy at `b0f2c2cd…`, while Model Parameters
v2.5 certifies `db26c3ff…`. Two governed registers disagree about which bytes are authoritative.

**Options.**

| Option | Consequence |
| --- | --- |
| **A. Supply the registered v5 workbook** | Full provenance restored, both registers agree. Requires the original artifact, which is not in this repository. |
| **B. Ratify the mounted copy** | Blocker clears by ruling; the registered binary hash in Model Parameters must be updated to `b0f2c2cd…` and the divergence recorded in the supersession log. Content certification already supports this. |
| **C. Defer** | Execution remains blocked on artifact custody even though fixtures are verified. |

**Execution blocked:** yes, until A or B.

---

## 2. Thirteen-game schedule exceptions

**Evidence.** Open item `OI-SCHED-13` is **OPEN**, P0, owner Chairman, naming five teams:
**ARK, GAST, UK, VAN, WVU**. Recommended action: "Resolve or explicitly ratify exception."

Ratification packet `RAT-002` ("Five 13-game teams") carries **no `chairman_decision`** — the column
is populated for `RAT-001` and `RAT-006` (both `APPROVED`) and blank here. Its recorded
`safe_default_if_deferred` is explicit:

> Block final season run

**No ratification exists.** The governed safe default is to block, so this blocker is not merely
unresolved — the sources affirmatively instruct blocking while it stands.

**Options.** (A) Correct the five schedules to 12 games; (B) explicitly ratify the 13-game
exceptions; (C) defer, which the source says means blocking the run.

Consequence of B: unequal game counts propagate into conference win%, which is the primary key for
both CCG participant selection (R-CCG-01) and A8/ECL standings championships (R-CCG-08). Open item
`OI-ACC-TIEDSET` already flags unequal-game-count tied sets as an unresolved pressure point.

**Execution blocked:** yes.

---

## 3. AAC division membership

**Evidence — the ratification exists.**

* `R-CCG-07`: "AAC division membership ratified (8 American / 8 Athletic). Load-bearing: feeds CCG
  participants -> record -> SOR." Status **RATIFIED**.
* `SUP-010`: `aac_divisions_2026.csv NEEDS-RATIFICATION` → `aac_divisions_2026_RATIFIED.csv`.
* Source register and artifact lineage both register the artifact:
  **577 bytes, sha256 `e0f674b4d0bab13ff943d0ced6364c70df40d4e4a1f1a2cde2a4479a13b2cd0f`**, status
  CANONICAL, inspection status FILE-VERIFIED.
* `R-CCG-05` makes the split load-bearing: participants are the American Division winner versus the
  Athletic Division winner.

**Evidence — the membership rows are recoverable.** The governed canonical team master carries a
`2026_conference_division` field assigning exactly **8 American** and **8 Athletic**, covering all
16 AAC teams and matching the ratified count:

| American Division | Athletic Division |
| --- | --- |
| ARMY, ECU, FAU, NAVY, TEM, UAB, USF, USM | LT, MEM, NMSU, RICE, TLN, TLSA, UNT, UTSA |

**Why the blocker does not clear.** The ratified **artifact** is not mounted, and its exact column
set, ordering and formatting are unrecorded, so its 577-byte digest cannot be reproduced. A locally
minted CSV would carry a different hash. Substituting a self-generated file for a registered
ratified one would manufacture exactly the class of provenance mismatch that packet 1b documents.

The extractor, validators and a fail-closed digest gate are implemented in
`aac_divisions.py`; the gate rejects any file whose digest is not the registered one, including a
correct-looking substitute.

**Options.**

| Option | Consequence |
| --- | --- |
| **A. Supply `aac_divisions_2026_RATIFIED.csv`** | Blocker clears mechanically; the gate verifies the digest and the extractor cross-checks the rows. Preferred if the artifact can be located. |
| **B. Rule that the canonical-master membership substitutes** | Blocker clears by ruling. The membership above becomes authoritative and the registered digest must be superseded. No data is invented — the rows come from a hash-verified governed input. |
| **C. Defer** | CCG participant selection for the AAC cannot run. |

**Execution blocked:** yes. Per the work order this returns
**`BLOCKED_ON_MISSING_RATIFIED_AAC_DIVISION_ROWS`** — qualified by the finding that the rows
themselves *are* present in the canonical master; it is the ratified artifact that is missing.

---

## 4. FCS source authority and translation

Two separate questions, both currently negative.

**A. Is the source authorized for model use?** No. The POWER_CRUNCH Build Manifest records
**`Model use authorized | FALSE`**. No superseding authorization exists in the supersession log.
This value is not overridden.

**B. Is an exact FCS-to-unified-neutral-points translation governed?** No. `R-FCS-RATING-01` fixes
FCS `sim_rating = 1397.51` and a `board_power_H_equivalent` of `0.297514`, but the same manifest
states:

> Board columns for FCS | BLANK — canonical policy preserved; Board-equivalent recorded not issued

"Recorded, not issued" is decisive: the equivalent exists as a note, not as an issued value.

The manifest also carries an Elo↔Board transform
(`primary_elo = 999.986237 * board_power_H + 1099.999878`). **Inverting it to manufacture a
translation would be an ad hoc conversion** and is not done. 13 schedule-only FCS entities are
affected across the 121 FBS / 13 FCS split.

**Options.** (A) Issue an explicit translation rule and an explicit model-use authorization;
(B) keep FCS opponents structurally excluded from rating effects under a governed rule; (C) defer.

**Execution blocked:** yes — both sub-questions must be answered.

---

## 5. HFA baseline: 4.0 vs 3.5

**No ruling is made here. Both values are presented with consequences.**

| | Option A | Option B |
| --- | --- | --- |
| Value | **4.0 points** | **3.5 points** |
| Register row | `ENG-HOME-FIELD` | `SCHED-HFA-BASE` |
| Source | `ENGINE_PARAMS` — cfb_sim.py, status **VERIFIED**, "calibrated up from initial 2.4" in the Jul 13–14 sweep | Team-master locked schedule/model parameter |
| Character | V2 legacy engine constant, empirically calibrated | Current governed schedule baseline |

Both are marked authoritative in their own registers. `13_SUPERSESSION_LOG` contains **no** entry
superseding either. The conflict is genuine, not a stale-label artifact.

**Consequences.**

| | Option A (4.0) | Option B (3.5) |
| --- | --- | --- |
| V2.1 comparability | Preserved. The V2.1 static control was produced under 4.0, so V3-vs-V2.1 deltas isolate the dynamic-rerating change. | Broken. Every V3-vs-V2.1 delta blends a rerating effect with a 0.5-point HFA shift, and the control can no longer serve as a clean baseline. |
| Governed-input consistency | V3 would run on an engine constant that contradicts the locked schedule parameter. | Consistent with the current governed schedule baseline. |
| Effect on margins | Home margin 0.5 points higher than Option B in every home game. Roughly 736 regular-season games per path; the shift is systematic, not noise, and moves home win rate up by a small but consistent amount. | Correspondingly lower. |
| Historical baselines altered | None. V2.1 control is immutable under both options. | None. |
| Affected files | `config/dynamic_weekly_mc_v3/v3_experimental.json` (`hfa_baseline_points`), `test_v2_control.py`, any rerating tests asserting margin behaviour. | Same. |

Note that both blocker IDs — `hfa_baseline_points` and
`governance.V3_HFA_BASELINE_CONFLICT_4P0_VS_3P5` — are cleared by this single ruling.

**Execution blocked:** yes. `hfa_baseline_points` stays `null`.

---

## 6. Committee final-strength tiebreak source

**Use point.** `committee.rank_committee_results_first` orders on
`(-win_pct, -opponent_win_pct, -conference_champion, -strength_tiebreak, team)`. `strength_tiebreak`
is consulted only after win%, opponent win% and champion status all tie exactly. The caller supplies
its value, precisely so V3 cannot silently drift from preseason strength to evolving strength.

**Why this must not feed back.** If the tiebreak drew on committee or resume ranking, the board
would rank on a function of itself: resume ranking depends on board position, which would then
depend on resume ranking. Football strength must be an input to the board, never an output of it.
Both permitted options respect that; the question is *which* football-strength snapshot.

**Evidence status.** The `COMMITTEE` sheet is marked **UNPATCHED** and carries an explicit warning:

> These parameters are recorded for traceability, not endorsement. Do not wire into season.py until patched.

Its defect register lists **D-09: No deterministic tiebreak rule**, alongside D-01 (no
strength-of-schedule component) and D-03 (scale normalization failure). No governed rule designates
a source.

**Options.**

| Option | Consequence |
| --- | --- |
| **`PRESEASON_STRENGTH`** | Frozen, path-independent tiebreak. Maximum V2.1 comparability and reproducibility. A team's tiebreak position never reflects the season it actually played, which is hard to defend late in the year. |
| **`FINAL_WEEKLY_FOOTBALL_STRENGTH`** | Tiebreak reflects the season as played. Introduces a dependency on the rerating chain, so it cannot be ruled on independently of the calibration program (packet 9), and it interacts with `freeze_strength_after_selection`. |

**Test changes required after ruling.** `require_v3_strength_tiebreak_policy` already gates both
values; the config field is populated, and committee-ordering tests gain a case fixing the chosen
source's behaviour at an exact four-way tie.

**Execution blocked:** yes.

---

## 7. A8/ECL ordering circularity

**The cycle.** Mapped explicitly in `ordering.py`:

```
A8_ECL_CHAMPION -> FINAL_COMMITTEE_BOARD -> CONFERENCE_CHAMPION_FLAG -> A8_ECL_CHAMPION
```

| Edge | Authority |
| --- | --- |
| A8/ECL champion needs the final board | `TB-ECL/A8`: TB-3 is the **FINAL** committee ranking, "not pre-CCG" — explicitly distinct from R-CCG-01's pre-Championship-Saturday board |
| The final board needs champion flags | `rank_committee_results_first` keys on `conference_champion`; CG-8 routes the G5 auto-bid through champion status |
| Champion flags include A8/ECL champions | `R-CCG-08`: A8/ECL champions are decided on conference win% at end of W14, standings-only |

**When it binds.** Only when an A8 or ECL standings race survives TB-1 (head-to-head) and TB-2 (mini
round-robin) and actually reaches TB-3. Unbroken races never consult the board. The implementation
distinguishes "structurally circular" from "binds on this path" and fails closed only on the latter —
a run must not be blocked by a hazard that never materializes, nor proceed through one that does.

**Options** (none selected, none implemented):

1. `PRELIMINARY_BOARD_BEFORE_CHAMPION_FLAG` — compute a preliminary board without champion flags,
   use it for TB-3, then compute the final board with flags. Deterministic and acyclic; cost is that
   TB-3 no longer uses the literal "final board" the rule names.
2. `CHAMPION_RESOLUTION_BEFORE_FINAL_BOARD_WITH_CHAMPION_BLIND_TIE_BOARD` — resolve all champions
   first using a champion-blind tie board, then build the final board. Preserves "champions are
   settled before the final board"; cost is a second ordering concept to govern and test.
3. `EXPLICIT_SOURCE_SUPPORTED_ALTERNATIVE` — any alternative a governed source actually supports.

**Execution blocked:** yes, whenever the cycle binds. `require_resolved_ordering` raises
`GovernanceBlock` rather than silently breaking the cycle.

---

## 8. CFP quarterfinal mapping

**What is governed.** The Playoff Calendar `Bracket_Flow` sheet fixes:

```
Byes           Seeds 1-4 (top-4 overall)
Play-In        G1 = 12 v 13 (Minneapolis); G2 = 11 v 14 (Atlanta)
Round 1        Games A-D: seeds 5-10 + 2 play-in winners
Quarterfinals  E = 1 v W(R1); F = 2 v W(R1); G = 3 v W(R1); H = 4 v W(R1)
Semifinal A    W(E) v W(H)      Semifinal B  W(F) v W(G)
Integrity P-3  Seeds 1 & 2 in opposite halves; cannot meet before the NCG. Verified.
```

Bracket Regime `S4` fixes Round 1 as 5v12, 6v11, 7v10, 8v9 at the higher seed.

**What is not governed.** Which first-round winner fills E, F, G or H. The placeholders are generic
by construction — `inspect_bracket` already reports
`quarterfinal_opponent_mapping_explicit: False`.

**Options.**

| Option | Deterministic consequence |
| --- | --- |
| **`FIXED_BRACKET_MAPPING`** | Quarterfinal opponent follows the bracket slot regardless of who wins it (classic pairing: 1 v W(8v9), 2 v W(7v10), 3 v W(6v11), 4 v W(5v12)). Bracket path is known before Round 1 is played; an upset carries the underdog's slot forward, so seed 1 can face a lower-ranked survivor than seed 4 does. |
| **`RESEED_BY_ORIGINAL_SEED`** | Highest remaining seed plays lowest remaining survivor. Preserves seeding advantage across rounds; bracket path is not knowable until Round 1 completes, and broadcast slotting cannot be fixed in advance. |

Both satisfy every recorded constraint including P-3, and they diverge exactly when an upset changes
the surviving seed order — which is most of the interesting probability mass. Choosing by inference
would silently pick a bracket shape the sources do not endorse.

**Execution blocked:** yes. `require_governed_quarterfinal_mapping` fails closed.

---

## 9. Rerating calibration program

**No canonical coefficients are chosen.** All six values remain `null` in the canonical config.

| Field | State |
| --- | --- |
| `weekly_performance_residual_coefficient` | null |
| `weekly_movement_cap_points` | null |
| `recent_form_weights` | null |
| `blowout_treatment` | null |
| `game_sd_points` | null |
| `sample_size_regularization` | null |

**Game SD specifically.** The only recorded figure is margin SD **20.2**, from the Jul 13–14
calibrated run. It sits **above** its own harness band of 16–18, and open item `ENG-CAL-MARGIN` is
**OPEN** with recommended action "Rerun current engine calibration". The `CALIBRATION` sheet adds:

> Do not tune the committee engine against an unvalidated stat universe.

20.2 is therefore **not** treated as approved. That V2 used it is not authority.

**What was built.** An experimental harness (`calibration.py`) that lets candidates be tested
without being promoted:

* Candidate regimes load only from `config/dynamic_weekly_mc_v3/experimental/`; loading from the
  canonical config raises.
* Every experiment record carries experiment ID, model version, configuration version, seed,
  candidate values, dataset ID and SHA-256, run timestamp, metrics, and V2.1 control comparison.
* `promote_regime` refuses without an explicit `APPROVE_V3_CALIBRATION_PROMOTION::<RULING_ID>`
  token, refuses malformed tokens, and refuses on the strength of a top ranking alone. Even an
  authorized promotion reports `writes_canonical_config: False`.
* `rank_experiments` raises without a named `EvaluationObjective` — no regime can be called best
  against an unstated goal.
* Public-money and injury columns are rejected at dataset registration. Public money creates flow,
  not belief; injuries remain deferred.

The shipped regimes file contains **zero regimes**, deliberately: authoring candidate coefficient
values would be inventing calibration data.

**Blocking finding.** No historical calibration observation set is mounted in this repository — the
schedule carries fixtures, not results. No experiment can be scored. Per the work order this returns
**`BLOCKED_ON_CALIBRATION_DATA`**: harness and tests only, no fabricated observations.

**Execution blocked:** yes.

---

## Recommended order for remaining rulings

Sequenced so that each ruling is decidable without depending on a later one.

1. **Schedule binary provenance (1b)** and **13-game exceptions (2)** — independent of everything
   else, and both concern whether the input set is trustworthy at all. The 13-game question also
   feeds conference win%, which several later rules key on.
2. **AAC membership (3)** — mechanical if the artifact is located; unblocks AAC CCG selection.
3. **HFA (5)** — independent, and it fixes the margin scale every later calibration is measured on.
   Ruling on calibration before HFA would calibrate against a scale that may then shift.
4. **FCS authority and translation (4)** — independent; determines whether 13 entities affect ratings.
5. **Committee strength source (6)** — depends on the HFA and rerating scale being settled if
   `FINAL_WEEKLY_FOOTBALL_STRENGTH` is chosen.
6. **A8/ECL ordering (7)** — depends on the committee board definition from 6.
7. **Quarterfinal mapping (8)** — independent of 1–7, but only matters once a field can be selected.
8. **Calibration program (9)** — last, and gated on calibration data existing at all. Requires 5 and
   6 settled first.

## Is V3 ready for a governed experimental 10,000-path run?

**No — and not merely for want of rulings.** Two independent obstacles stand beyond the eight
decisions above:

* **No calibration data exists.** Even with all eight rulings issued, the six rerating coefficients
  would still be unset, because there is nothing to calibrate against.
* **Production execution is not implemented.** `cli.py` reaches the full-run gate and raises by
  design: "Full 10,000-path + postseason execution is intentionally unreachable until the governed
  rerating and remaining data policies are unblocked and implemented."

The structural harness passes and the fail-closed gates are real, so the path to a run is clear —
but the run itself is gated on rulings, then data, then implementation, in that order.
