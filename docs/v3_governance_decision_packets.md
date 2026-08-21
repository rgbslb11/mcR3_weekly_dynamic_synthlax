# V3 Governance Decision Packets

Prepared against `main` @ `3b46e561b8d939e10ba5d6ff2f69923d963a148e`, tested V3 baseline `6353567d`.
Updated for the **R2 governance convergence** against audited head
`e3e1e41bcec3b8c8e00e90087914824afaec7897`.

V3 remains **EXPERIMENTAL**. Nothing in this document resolves a governance question on its own.
Each packet records the evidence found, the values in conflict, and — where a Chairman ruling has
since been issued — the ruling that closed it and the deterministic validation that had to pass
before the corresponding blocker actually cleared.

## Blocker accounting

Counted by blocker ID, not by narrative. Earlier revisions of this document quoted a collapsed
count of "distinct rulings" that matched neither the packet table below nor
`blocker_report.summary()`; that figure is withdrawn. The three sets below are frozen in
`blocker_report.py` and asserted for exact set equality by
`tests/dynamic_weekly_mc_v3/test_r2_blocker_regression.py`.

| Checkpoint | Count | Source |
| --- | ---: | --- |
| R1 baseline (tested build) | 18 | `V3_BUILD_MANIFEST.json`, `blocker_report.R1_BASELINE_BLOCKERS` |
| R1 audited live (head `e3e1e41`) | 17 | `blocker_report.R1_AUDITED_LIVE_BLOCKERS` |
| **R2 live** | **11** | `blocker_report.R2_EXPECTED_LIVE_BLOCKERS`, live `show-blockers` |

**Retired by R2 rulings (9).** Each required both an issued ruling and a passing deterministic check.

| Blocker ID | Ruling | Validation that had to pass |
| --- | --- | --- |
| `provenance.SCHEDULE_BINARY_HASH_MISMATCH_VS_MODEL_PARAMETERS_V2_5` | `R2-SCHED-V5-AUTH` | Certified Games content reproduces; mounted file is not the superseded v4 binary |
| `governance.FIVE_13_GAME_SCHEDULE_EXCEPTIONS_UNRATIFIED` | `R2-SCHED-13GAME` | Exactly 13 W1–W14 REG rows for each of the five; no duplicate `game_id`; no duplicate opponent/date; no CCG template counted; no unapproved team above 12 |
| `hfa_baseline_points` | `R2-HFA-3P5` | Config carries 3.5; legacy 4.0 refused by name |
| `governance.V3_HFA_BASELINE_CONFLICT_4P0_VS_3P5` | `R2-HFA-3P5` | Same ruling; both register rows left unedited |
| `fcs_translation_policy` | `R2-FCS-ELO-1250` | Config carries `FIXED_ELO_1250`; Board equivalents and transform inversion refused |
| `governance.FCS_SOURCE_MODEL_USE_AUTHORIZED_FALSE` | `R2-FCS-ELO-1250` | Build Manifest preserved unedited and recorded as superseded for V3 use |
| `committee_tiebreak_strength_source` | `R2-COMMITTEE-TB` | Obsolete field null and refused if populated; structured chain configured |
| `inputs.aac_divisions_csv` | `R2-AAC-SUCCESSOR` | Successor artifact mounted and digest-verified; legacy artifact recorded missing, not reproduced |
| `governance.A8_ECL_FINAL_BOARD_TIEBREAK_ORDERING_NOT_EXPLICIT` | `R2-A8-ECL-ORDER` | TB-3 board proven post-CCG and pre-G5-seeding |

**Opened by R2 (3).** Newly issued governance names artifacts and mathematics this repository does
not hold. Each is a narrow gate replacing an assumption, not a regression.

| Blocker ID | Why |
| --- | --- |
| `inputs.board_of_record_i_k` | `R2-BOARD-OF-RECORD` names Board I-K; it is not mounted and Board I-H may not substitute |
| `governance.OWP_OOWP_DENOMINATOR_SEMANTICS_NOT_GOVERNED` | `R2-SOS` fixes the weights; no authority defines the OWP/OOWP denominator, exclusion or instance weighting |
| `governance.FCS_FIXED_ELO_1250_TO_UNIFIED_POINTS_SCALE_NOT_GOVERNED` | `R2-FCS-ELO-1250` fixes an Elo; no register maps it onto the unified neutral-points axis |

**Carried forward, unchanged (8).** Six `calibration.*` fields, `governance.GAME_SD_CALIBRATION_OPEN`
and `governance.POSTSEASON_QUARTERFINAL_MAPPING_NOT_EXPLICIT`. No ruling substitutes for calibration
evidence that does not exist, or for a bracket edge the official artifact never states.

| Packet | Blockers covered | Status after R2 |
| --- | --- | --- |
| [1. Schedule provenance](#1-schedule-provenance) | `provenance.SCHEDULE_GAMES_HASH_REPRODUCTION_MISMATCH`, `provenance.SCHEDULE_BINARY_HASH_MISMATCH_VS_MODEL_PARAMETERS_V2_5` | **Both resolved** — 1a by reconciliation, 1b by `R2-SCHED-V5-AUTH` |
| [2. Thirteen-game exceptions](#2-thirteen-game-schedule-exceptions) | `governance.FIVE_13_GAME_SCHEDULE_EXCEPTIONS_UNRATIFIED` | **Resolved** — `R2-SCHED-13GAME` |
| [3. AAC division membership](#3-aac-division-membership) | `inputs.aac_divisions_csv` | **Resolved** — `R2-AAC-SUCCESSOR` |
| [4. FCS source authority](#4-fcs-source-authority-and-translation) | `fcs_translation_policy`, `governance.FCS_SOURCE_MODEL_USE_AUTHORIZED_FALSE` | **Resolved** — `R2-FCS-ELO-1250`; opens the unified-points scale gate |
| [5. HFA baseline](#5-hfa-baseline-40-vs-35) | `hfa_baseline_points`, `governance.V3_HFA_BASELINE_CONFLICT_4P0_VS_3P5` | **Resolved** — `R2-HFA-3P5` selects 3.5 |
| [6. Committee strength source](#6-committee-final-strength-tiebreak-source) | `committee_tiebreak_strength_source` | **Resolved by retirement** — `R2-COMMITTEE-TB` |
| [7. A8/ECL ordering](#7-a8ecl-ordering-circularity) | `governance.A8_ECL_FINAL_BOARD_TIEBREAK_ORDERING_NOT_EXPLICIT` | **Resolved** — `R2-A8-ECL-ORDER` |
| [8. Quarterfinal mapping](#8-cfp-quarterfinal-mapping) | `governance.POSTSEASON_QUARTERFINAL_MAPPING_NOT_EXPLICIT` | **Narrowed, still open** — `R2-NO-RESEED` removes reseeding; slot edges remain unstated |
| [9. Calibration program](#9-rerating-calibration-program) | six `calibration.*`, `governance.GAME_SD_CALIBRATION_OPEN` | **Open** — objective now governed by `R2-CAL-OBJECTIVE`; no data mounted |
| [10. Board of Record](#10-board-of-record) | `inputs.board_of_record_i_k` | **Resolved** — artifact mounted and SHA-256 verified; see [B1 custody](#b1--board-of-record-artifact-custody) |
| [11. SOS semantics](#11-sos-denominator-semantics) | `governance.OWP_OOWP_DENOMINATOR_SEMANTICS_NOT_GOVERNED` | **Open** — weights ruled, semantics not |

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

### 1b. Binary hash — RESOLVED by ruling `R2-SCHED-V5-AUTH`

**Resolution.** Schedule v5 is authoritative, and a binary-copy identity difference does not block V3 when the source is the verified v5 schedule and its certified Games content reproduces. It does. Option A below was not taken and Option B was not taken either: the registered hash `db26c3ff…` is **not** rewritten to match the mounted copy. All three binary hashes stay recorded, `provenance_anomalies` still reports the mismatch as an observation, and only `blocking_provenance_anomalies` narrows. A content-certification failure still blocks, and a mounted superseded v4 artifact still blocks.

The evidence below is unchanged.


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

**RESOLVED by ruling `R2-SCHED-13GAME`.** ARK, GAST, UK, VAN and WVU are approved. The blocker cleared only after `schedule_exceptions.validate_13_game_exceptions` confirmed, against the mounted schedule, that each carries exactly 13 W1–W14 REG rows, that no CCG template row is countable, that no `game_id` or opponent/date pair repeats, and that no unapproved team sits above 12 games. `OI-SCHED-13` and `RAT-002` are left unedited; the ruling supersedes RAT-002's recorded safe default rather than changing it.


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

**RESOLVED by ruling `R2-AAC-SUCCESSOR`** — Option A below was impossible and Option B was declined. Instead a **new** governed artifact was issued: `aac_divisions_2026_R2_SUCCESSOR.csv`, 554 bytes, sha256 `92fd7f78…`, derived under R-CCG-07 from the hash-verified canonical master, with a provenance sidecar recording source rule, source artifact hashes, columns, `recorded_at` and successor status. The legacy 577-byte artifact is recorded `NOT_MOUNTED_IN_REPOSITORY` with `reproduction_attempted: false` — its lineage is preserved and its digest was never faked. The gate accepts either digest and nothing else.


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

**RESOLVED by ruling `R2-FCS-ELO-1250`** — with one narrow gate opened in its place.

Both sub-questions below are now answered: the source is authorised for V3 use (the Build Manifest's `Model use authorized: FALSE` is preserved unedited and recorded as superseded), and the treatment is a fixed **Elo 1250** requiring no later toggle. The Board equivalents (`0.294` / `0.297` / `0.297514`) are refused as a conversion rule and `invert_board_transform` raises rather than computing.

**What the ruling does not settle.** V3 rates teams in unified neutral points, and no governed register maps Elo onto that axis. That gap is surfaced as `governance.FCS_FIXED_ELO_1250_TO_UNIFIED_POINTS_SCALE_NOT_GOVERNED` rather than filled by inverting the transform the same ruling forbids.


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

**RESOLVED by ruling `R2-HFA-3P5`: the V3 football-point HFA is 3.5.**

### What the registers actually say

An earlier revision of this packet described the two values as symmetrically authoritative —
"both are marked authoritative in their own registers", and "the conflict is genuine, not a
stale-label artifact". That was an incomplete reading of the evidence and is corrected here.

| | 4.0 | 3.5 |
| --- | --- | --- |
| Register row | `ENG-HOME-FIELD` | `SCHED-HFA-BASE` |
| `02_PARAMETER_REGISTER` status | **`HISTORICAL`** | `LOCKED` |
| `02_PARAMETER_REGISTER` implementation status | **"conflicts with current HFA families"** | "active team-edge baseline" |
| `02_PARAMETER_REGISTER` validation status | **`NOT CURRENT`** | `SOURCE-VERIFIED` |
| `02_PARAMETER_REGISTER` note | **"Legacy drive-engine HFA; do not conflate with schedule HFA or Elo HFA"** | `team_home_edge_points = modifier * 3.5` |
| `ENGINE_PARAMS` sheet | `HOME_FIELD_PTS = 4`, status `VERIFIED`, "Calibrated up from initial 2.4" | not present |

So 4.0 is `VERIFIED` **in `ENGINE_PARAMS` only**. The master parameter register carries it as
`HISTORICAL` / `NOT CURRENT` and warns in as many words against conflating it with the schedule
HFA. The evidence was never symmetric, and the register's own note anticipated the ruling.

### What the ruling does and does not change

* **V3 football-point HFA is 3.5.** `hfa_baseline_points` carries it; `require_governed_hfa`
  refuses 4.0 by name, citing its `HISTORICAL` / `NOT CURRENT` status rather than merely
  reporting a mismatch.
* **4.0 is preserved, not deleted.** Both register rows are unedited. `hfa.HFA_REGISTER` records
  4.0 with its status so the historical value stays visible.
* **The Elo layer is untouched.** `CCG-HFA_ELO = 65` (LOCKED under R-CCG-06 / DEF-CCG-6) is a
  separate parameter in a separate layer. The ruling does not globally replace every HFA-shaped
  value with 3.5, and a test asserts the register still reads
  `{SCHED-HFA-BASE: 3.5, ENG-HOME-FIELD: 4.0, CCG-HFA_ELO: 65.0}`.
* **V2.1 is unchanged.** The static control was produced under the legacy engine and its digest
  `39055662…` is unmodified. A V3-versus-V2.1 comparison now blends a rerating effect with a
  0.5-point HFA difference; that is a consequence of the ruling and is recorded, not hidden.

`13_SUPERSESSION_LOG` still contains no entry superseding either row. The ruling is the
superseding authority, and it is recorded in `rulings.py` rather than written into the workbook.

**Execution blocked:** no. Both `hfa_baseline_points` and
`governance.V3_HFA_BASELINE_CONFLICT_4P0_VS_3P5` are cleared by this single ruling.

---

## 6. Committee final-strength tiebreak source

**RESOLVED BY RETIREMENT — ruling `R2-COMMITTEE-TB`.** Neither option below was selected, because the question itself presumed a board that ranks on a hidden number. The field `committee_tiebreak_strength_source` stays `null` and is refused if populated; `require_v3_strength_tiebreak_policy` now raises for every input including its two former answers. In its place `committee_tiebreak_policy` carries the deterministic chain COMMITTEE-TB1 head-to-head, TB2 common-opponent performance, TB3 SOS, TB4 previous week's board, and the weekly product publishes a Top 25 ordering and the current bracket only.

One edge case stays fail-closed and only that one: on the first November board there is no previous board for TB4, and no repository authority designates a fallback. Board I-K is the Board of Record but nothing names it as the TB4 stand-in, so `break_committee_tie` raises there rather than substituting one.

The evidence below is unchanged and still explains why the original framing was unusable.


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

**RESOLVED by ruling `R2-A8-ECL-ORDER`** — and not by picking any of the three options below. The cycle is broken causally: A8 and ECL play no CCG, each determines its own champion independently, and A8/ECL-TB3 consults the committee board computed **after** the seven CCGs and **before** any G5 automatic-bid seeding. That board is built from completed football results, so it never consumes the champion flag it is being used to resolve, and the closing edge of the cycle is gone. `require_post_ccg_board` refuses a board that is pre-CCG or post-seeding. Cross-conference A8-versus-ECL comparison is refused outright.

The cycle map below is preserved as the superseded reading that motivated the ruling.


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

**NARROWED by ruling `R2-NO-RESEED`, still open.** There is no reseeding, so `RESEED_BY_ORIGINAL_SEED` is superseded and refused. Every edge the official artifact actually states is now bound: byes 1–4, play-in G1 = 12v13 and G2 = 11v14, first round 5v12 / 6v11 / 7v10 / 8v9, quarterfinal hosts E=1 F=2 G=3 H=4, semifinals W(E)vW(H) and W(F)vW(G), and P-3.

What the artifact still never states is **which first-round winner fills E, F, G or H**. The full `.xlsx` was re-inspected for this convergence — five sheets, no cell comments, no hidden content — and the string `E = 1 v W(R1); F = 2 v W(R1); G = 3 v W(R1); H = 4 v W(R1)` is the whole of it. Binding an edge here would invent bracket topology, which the same ruling forbids, so `require_governed_quarterfinal_slot_edges` fails closed and `governance.POSTSEASON_QUARTERFINAL_MAPPING_NOT_EXPLICIT` remains live.


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

**OBJECTIVE now governed by ruling `R2-CAL-OBJECTIVE`; the blockers remain.** The primary criterion is out-of-sample **Baxter Rating RMSE**, minimised. Colley Matrix and SRS are independent witnesses reported separately, and any weighted composite of the three is refused — ACC-EXT-12 records that blend as PROPOSAL ONLY / NOT ADOPTED. Training, validation and holdout stay separated. Promotion requires a named authority, either governed calibration evidence from the holdout split or explicit Chairman justification, **and** the human approval token; the record names which was used.

Dataset registration was hardened after the previous audit: format-aware CSV/TSV/JSON parsing, unknown format refused rather than guessed, invalid encoding refused, a governed observation allowlist, and substring matching that catches `public_money_percentage`, `bet_pct`, `sharp_money` and a TSV header that a comma parser would have read as one column.

No historical observation set is mounted, so all six coefficients stay `null` and registration still returns **`BLOCKED_ON_CALIBRATION_DATA`**.


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

## 10. Board of Record

**OPEN — opened by ruling `R2-BOARD-OF-RECORD`.**

The Board of Record is `2026_Board_I-K_CANONICAL_APPROVED_R1_REISSUE.xlsx` (Board I-K R1–R3 FINAL
/ re-issued governance lineage). Board I-H must **not** be substituted for it.

That artifact is not mounted in this repository. What is present is Board I-H v2, as sheet
`08_BOARD_IH_TOP25` of Model Parameters v2.5, and it stays exactly where it is as historical and
superseded evidence.

Board rows are load-bearing for four separate governed decisions: CCG-TB3 (the last board before
Championship Saturday), COMMITTEE-TB4 (the previous week's board), A8/ECL-TB3 (the post-CCG board),
and CFP selection itself. `require_board_of_record` therefore fails closed, and
`reject_historical_board_substitution` refuses any other board offered in its place.

**Required to clear:** mount the named artifact.

**Execution blocked:** ~~yes~~ — **cleared by the B1 mount.** The paragraphs above are
preserved as the state R2 through R4 recorded. See
[B1 — Board-of-Record artifact custody](#b1--board-of-record-artifact-custody) for the
resolution.

---

## 11. SOS denominator semantics

**OPEN — opened by ruling `R2-SOS`.**

The ruling fixes the committee SOS definition exactly: `SOS = 0.25 * WP + 0.50 * OWP + 0.25 * OOWP`.
One quantity, one direction, one definition. Mean opponent Elo is not it, and the retired
`schedule_path_score` + `resume_ceiling_index` double count is not revived (both RETIRED in the
Bracket Regime Deferred Register; DEF-2 records `sos_index` as "REPORTED, never scored").

What no repository authority defines is what the weights are applied *to*. The precise ruling
required, reproduced by `sos.required_ruling_text()`:

1. Are an opponent's games **against the evaluated team** removed from that opponent's record
   when computing OWP?
2. Is OWP **team-averaged** or **schedule-instance-weighted**?
3. How is a **repeated opponent** treated — once, or once per meeting?
4. How is **OOWP constructed** — the mean of each opponent's OWP, or the mean over every
   opponent-of-opponent directly?
5. How do **schedule-only FCS opponent records** enter WP, OWP and OOWP?
6. What happens to a team with **zero qualifying games**?

Each is a live fork, not a formality: tests demonstrate that questions 1, 4, 5 and 6 each change
the numbers, and question 1 alone decides the Chairman's own common-opponent example.

**The nearest authority answers none of them.** `V2_1_STATIC_CONTROL…xlsx!Methodology!A11`
records V2.1's committee chain as "Winning percentage → average opponents winning percentage →
conference champion → head-to-head → unified preseason power". It names an OWP-like quantity,
defines no denominator, exclusion or weighting rule, contains **no OOWP at all**, and belongs to
a chain that ruling `R2-COMMITTEE-TB` has since replaced.

`18_ACC_POLICY_REFERENCE` is next closest and also does not answer them: ACC-EXT-03 (alternate
game-count tied sets) and ACC-EXT-08/09 (common-opponent and sweep cascades) are all recorded
**OPEN — REQUIRES RULING**, and ACC-EXT-10 records that the external vendor ranking the ACC
policy names "does not disclose variables, weights, or formula".

**These are not cosmetic.** On the Chairman's own common-opponent example — Lehigh 11-1 and USF
11-1, each 2-1 against Harvard 7-5, Rice 4-8 and UCF 9-2 — the two resumes are *numerically
identical* under question 1 answered "no", and separate cleanly under "yes", because beating a team
lowers that team's record for you and raises it for the other. A deterministic fixture reproducing
all five records asserts both outcomes. Choosing an answer here would silently pick a committee.

**Required to clear:** issue the OWP/OOWP denominator, opponent-exclusion and schedule-instance
weighting semantics.

**Execution blocked:** yes — `governance.OWP_OOWP_DENOMINATOR_SEMANTICS_NOT_GOVERNED`.

---

## Remaining work, by blocker ID

Sequenced so each item is decidable without depending on a later one. Listed by blocker ID rather
than by a collapsed count.

1. **`inputs.board_of_record_i_k`** — mount the named Board-of-Record artifact. Four governed
   tiebreak paths and CFP selection all wait on it, so nothing downstream is decidable first.
2. **`governance.OWP_OOWP_DENOMINATOR_SEMANTICS_NOT_GOVERNED`** — issue the SOS semantics. They
   feed COMMITTEE-TB2, COMMITTEE-TB3 and A8/ECL-TB2.
3. **`governance.POSTSEASON_QUARTERFINAL_MAPPING_NOT_EXPLICIT`** — state the four R1-winner to
   quarterfinal slot edges, or supply an artifact that does. Independent of 1 and 2.
4. **`model_scale.FCS_ELO_1250_TO_V3_POINT_SCALE_ADAPTER`** — issue or calibrate an
   Elo-to-unified-points scale rule for the 13 schedule-only FCS entities. A model-scale
   item, not an FCS policy question.
5. **The six `calibration.*` fields and `governance.GAME_SD_CALIBRATION_OPEN`** — last, and gated
   on calibration data existing at all. The objective is now governed; the observations are not
   mounted.

One further edge case is fail-closed without being an execution blocker: `COMMITTEE-TB4` on the
first November board, where no previous board exists and no authority designates a fallback.

## Is V3 ready for a governed experimental 10,000-path run?

**No.** Three independent obstacles stand beyond the five items above:

* **The Board of Record is not mounted.** No governed selection or tiebreak can run on real rows.
* **No calibration data exists.** Even with every ruling issued, the six rerating coefficients
  would still be unset, because there is nothing to calibrate against.
* **Production execution is not implemented.** `cli.py` reaches the full-run gate and raises by
  design, and this convergence did not change that.

The structural harness passes, 191 V3 tests and 250 tests overall are green, and the fail-closed
gates are real and adversarially tested. V3 remains **EXPERIMENTAL**, every calibration value
remains `null`, no probabilities were produced and no simulation was run.

---

## Appendix: R2 audit challenge adjudications

Five specific convergence claims were challenged after the R2 handoff. Each was re-adjudicated
against the mounted artifacts rather than against any prior summary. Two changed the outcome.

### 1. SOR reference Elo — **corrected: R_ref is governed**

The challenge supplies a SOR-B specification stating `2026 R_ref = 1901`, method "90th-percentile
preseason canonical Elo, frozen at season start", and asks that R_ref not be reported as missing
governance unless a higher authority explicitly supersedes it.

**A higher authority does, and it is in the repository.**

| Coordinate | Contents |
| --- | --- |
| `02_PARAMETER_REGISTER!E25` | `CCG-R_REF` = `1893.3`, status `LOCKED`, validation `SOURCE-VERIFIED`, note "SOR reference Elo (unchanged)." |
| `20_CANON_MANIFEST_INGEST!C15` | "…fixed-rating in parts; **R_ref 1901 now stale**", artifact status `SUPERSEDED`, superseded "by 2026_Board_I-H_v2 + 2026_HARDENED_Run_v2_IH (**R-MC-V2**)", note "Retain for audit; **do not use for decisions**." |
| `20_CANON_MANIFEST_INGEST!B24` | change log, "2026-07-14: … **R_ref 1901->1893.3**; field UNCHANGED." |
| `11_VALIDATION_REGISTER!D15` | `8000 / 20260714 / 0.85 / 68 / 65 / 1893.3` |

So the 2026 SOR reference Elo **is** governed, at **1893.3**, under ruling **R-MC-V2** dated
2026-07-14. 1901 is its superseded predecessor. The prior handoff's phrasing — that a governed
SOR-B season R_ref distinct from the MC-domain value was missing — is withdrawn: there is one
ratified value serving both domains, tagged by namespace so neither can write the other
(REJ-012, "Keep domains separate"). `sor.py` now carries 1893.3 as the governed 2026 value and
refuses **both** 1901 (superseded) and 1684.9 (stale library default) by name.

The spec's stated *method* ("90th-percentile preseason canonical Elo") is not verifiable here —
the string `percentile` appears in no mounted workbook or in the canonical master.

**Remaining SOR-B ratification items, distinct from R_ref and narrower than it:**
`P_TO_STRENGTH_TRANSFORM` and `REFERENCE_HFA`. `compute_sor_b.py` is not mounted anywhere on this
filesystem, so neither can be verified; both are stamped on every SOR row rather than assumed.
Neither is an execution blocker — the report is `RESEARCH_REPORT_ONLY` and never committee input.

### 2. SRS solver — **equivalence proven for the mathematics, not for canonical anchors**

The challenge requires proof across seven properties before the exact solver may replace the
iterative one, and says to request changes if equivalence cannot be demonstrated.

| Property | Result |
| --- | --- |
| Solves the same governed system | **Proven.** Residuals of `n_i·r_i − Σ m_ij·r_j − margins_i` ≤ 2.8e-13 across leagues of 4 to 121 teams. |
| Reproduces the iterative ordering | **Proven where the iteration converges.** Gauss-Seidel converged in every tested league; max value difference 9.6e-13; orderings identical wherever no two ratings sit closer than that. |
| Reproduces historical validation anchors | **Cannot be demonstrated — no anchors are mounted.** |
| Preserves centering | **Proven.** Per-component `|Σr|` ≤ 1.7e-14. |
| Preserves the ±24 game-margin cap | **Proven.** A 300-point margin yields ratings identical to a 24-point one. |
| Preserves `srs_over_40` semantics | **Cannot be demonstrated — the term appears in no mounted artifact.** |
| No early-week disconnected-graph instability | **Fixed and proven.** The solver now works per connected component, so a week-1 graph of isolated pairs solves and centres cleanly instead of raising. |

**Why the solver was changed at all:** on the three-team fixture A beat B by 30 (capped 24) and
beat C by 7, the exact solution is A = 31/3, C = A−7, B = A−24, ordering `A, C, B`, residuals
≈ 1e-16. A Jacobi sweep oscillates rather than converging; after 10,000 iterations it returns
`A = 0.0, B = −8.5, C = 8.5` with residuals of −31.0, 15.5 and 15.5 and the ordering `C, A, B`.
That is not a rounding difference — it is a wrong answer that a max-iteration cutoff presents as
a result.

**Two properties cannot be proven here because their evidence does not exist in this repository.**
No canonical SRS specification, no `compute_srs.py`, and no historical validation anchor is
mounted — searched across every cell of all eight governed workbooks, the canonical team master,
and the whole filesystem. The only in-repo mention of SRS as a model is
`18_ACC_POLICY_REFERENCE!C14`, "z(SRS capped ±24)" inside a Body-of-Work Index proposal marked
**PROPOSAL ONLY / NOT ADOPTED**.

Accordingly this module does **not** claim to be canonical SRS.
`srs.require_canonical_validated_srs()` raises, `srs.require_srs_over_40()` raises, and the
witness payload reports `canonical_validation_status: NOT_VALIDATED_AGAINST_CANONICAL_ANCHORS`.
Mount the specification and the anchors and the remaining two properties become checkable.

### 3. G5 seed #5 — **corrected: the fail-closed guard is removed**

The prior convergence raised a `GovernanceBlock` when the G5 automatic-bid champion ranked inside
the top four, on the grounds that seed-5-exact and Bracket Regime `S2` ("The FOUR HIGHEST-RANKED
TEAMS OVERALL receive a first-round bye") disagreed. That was wrong: Chairman authority is
explicit and later, so this is a **supersession**, not a fresh decision.

`S2` is now recorded as superseded to exactly the extent of the conflict — the bye seeds remain
1–4, and the team that would otherwise have been 5th moves up into the vacated bye.

Verified at every natural committee position named in the challenge:

| Natural rank | Assigned seed | Field a permutation | Others in rank order | In a play-in |
| ---: | ---: | --- | --- | --- |
| 1 | **5** | yes | yes | no |
| 3 | **5** | yes | yes | no |
| 5 | **5** | yes | yes | no |
| 8 | **5** | yes | yes | no |
| 14 | **5** | yes | yes | no |

Seed 5 is exact in both directions: a champion ranked 1st is displaced *down* to it and one
ranked 14th is pulled *up* to it. In every case the 14 seeds are a bijection onto the same field,
with no duplication and no omission, and exactly one G5 automatic bid is issued.

### 4. Quarterfinal source mapping — **unchanged: the blocker is correctly retained**

See packet 8 above for the coordinate-level re-inspection. The source establishes quarterfinal
*hosts* and no quarterfinal *opponents*; all 24 bijections remain consistent with everything the
artifacts state.

### 5. FCS 1250 versus the V3 point scale — **reclassified, policy not reopened**

The Chairman policy `FCS Elo = 1250` is settled and is not reopened. What was previously
namespaced `governance.` is now `model_scale.FCS_ELO_1250_TO_V3_POINT_SCALE_ADAPTER`, so it
cannot be read as questioning the rating policy.

The bridge is genuinely required, not hypothetical: all 13 schedule-only FCS entities carry
`preseason_strength_points = None`, they appear in 15 regular-season games across weeks 2, 3, 4,
5 and 12, and `engine._initialize_states` raises on the first of them today. The V3 engine rates
in unified neutral points (observed FBS range −17.46 to +32.88); 1250 is an Elo.

The bridge V2.1 used is precisely the route the ruling closes.
`V2_1_STATIC_CONTROL…xlsx!Methodology!A8`: "13 schedule-only opponents use the canonical
R-FCS-RATING-01 operator composite **translated from Board I-H equivalent to unified points**."

### 6. OWP / OOWP — **unchanged: one narrow blocker, six questions**

See packet 11 above. `governance.OWP_OOWP_DENOMINATOR_SEMANTICS_NOT_GOVERNED` is retained, and
the required ruling is stated in full rather than inferred.

---

# R3 — PR #3 final convergence

Converged against the R2 adjudicated candidate
`bbc353e823f8c5e49ee241d412a265481daf9cb0`, base
`3b46e561b8d939e10ba5d6ff2f69923d963a148e`.

Two Chairman rulings were issued and both are encoded. Nothing else moved: no calibration value
was promoted, the FCS point-scale adapter was not constructed, and no simulation was run. The
live blocker set goes **11 → 9**, and the two that left are exactly the two the rulings retire.

| Checkpoint | Blockers | Tests |
| --- | ---: | ---: |
| R2-A head `bbc353e` (independently re-verified) | 11 | 286 (227 V3) |
| **R3 final convergence candidate** | **9** | **352** (293 V3) |

## R3-SOS-OWP-OOWP-SEMANTICS — OWP / OOWP semantics

**DIRECT_CHAIRMAN_AUTHORITY.** Retires
`governance.OWP_OOWP_DENOMINATOR_SEMANTICS_NOT_GOVERNED`.

The R2-SOS weights are unchanged — `SOS = 0.25·WP + 0.50·OWP + 0.25·OOWP`. What the ruling
supplies is the semantics underneath them, answering all six open questions:

| # | Question | Ruling |
| --- | --- | --- |
| 1 | Opponent's games against the evaluated team | **Excluded** from OWP |
| 2 | OWP averaging | **Schedule-instance weighted**, not team-averaged |
| 3 | Repeated opponent | **Once per completed meeting** — two meetings, two contributions |
| 4 | OOWP construction | **Mean of each opponent's own governed OWP**, once per instance |
| 5 | Schedule-only FCS records | Governed available records only; otherwise **UNAVAILABLE** |
| 6 | Zero qualifying observations | **UNAVAILABLE / NULL** — never `0`, `0.0` or `0.500` |

Only games completed through the applicable week participate, so no future result can leak into a
weekly value.

**Unavailability is a value, not a number.** `sos.UNAVAILABLE` (`None`) propagates: an unavailable
WP, OWP or OOWP makes the SOS itself unavailable rather than silently becoming numeric.
`sos_report_row()` stamps it with provenance; `rank_by_sos()` fails closed rather than ordering on
a component that does not exist. For tiebreaks, a criterion that cannot be evaluated because a
required governed component is unavailable **does not resolve the tie** — `break_committee_tie`
advances to the next already-governed stage, which is deliberately distinct from the two sides
being equal.

**The common-opponent guardrail held.** The `0.25 / 0.50 / 0.25` common-opponent shape was *not*
newly promoted on the strength of this ruling, and no result-weighted alternative was adopted
either. What changed here is only the denominator semantics, which this ruling explicitly
governs. The formula itself was governed later, by `R4-COMMON-OPP-FORMULA` — see below. The
implementation still distinguishes two teams with identical common-opponent records where the
underlying strength evidence supports it, and that fixture is a behavioural check — not
governance authority.

## R3-CFP-FIXED-TOPOLOGY — fixed 2026 bracket

**SUCCESSOR_DIRECT_CHAIRMAN_AUTHORITY.** Retires
`governance.POSTSEASON_QUARTERFINAL_MAPPING_NOT_EXPLICIT`.

```
PI-A = 12 v 13          R1-A = 7 v 10           QF-E = 1 v W(R1-B)      SF-A = W(QF-E) v W(QF-H)
PI-B = 11 v 14          R1-B = 8 v 9            QF-F = 2 v W(R1-A)      SF-B = W(QF-F) v W(QF-G)
                        R1-C = 6 v W(PI-B)      QF-G = 3 v W(R1-C)
                        R1-D = 5 v W(PI-A)      QF-H = 4 v W(R1-D)
```

No reseeding. The bracket consumes **final assigned seeds**, not natural committee ranks, and an
upset never alters future slot topology.

**Provenance, stated precisely.** The official playoff workbook is preserved unchanged and is not
reinterpreted. `postseason.QUARTERFINAL_SLOT_EDGES_STATED_IN_ARTIFACT` **stays `False`** and
`governance.inspect_bracket` still reports `quarterfinal_opponent_mapping_explicit: False`,
because `Bracket_Flow!B6` really does say only `E = 1 v W(R1); F = 2 v W(R1); …`. The workbook
supplied prior structural evidence; its generic `W(R1)` labels never bound the four Round-1
winners to E/F/G/H. Direct successor Chairman authority fills that ambiguity through a *separate*
flag, so the resolution reason is recorded as `SUCCESSOR_DIRECT_CHAIRMAN_AUTHORITY` and never as
`SOURCE_WORKBOOK_CONTAINED_MAPPING`.

Bracket Regime LOCKED `S4` ("First Round 5v12, 6v11, 7v10, 8v9") is preserved verbatim in
`BRACKET_REGIME_S4_ROUND_1_TEXT` and superseded to exactly one extent: in a 14-team field seeds
11–14 play in, so seeds 5 and 6 meet play-in winners rather than fixed seed opponents.

**G5 interaction.** `R2-G5-SEED5` is not reopened. The automatic-bid champion is seed 5 exactly
and therefore always meets `Winner(PI-A)` in R1-D. It never enters PI-A or PI-B, stays seed 5 even
when its natural committee rank is top four, and is not reseeded after any result.


## R4-COMMON-OPP-FORMULA — the exact common-opponent formula

**DIRECT_CHAIRMAN_AUTHORITY.** Retires nothing — this is an authority representation
correction, not project execution work.

```
COMMON_OPP_SCORE = 0.25 * WP_common + 0.50 * OWP_common + 0.25 * OOWP_common
```

**The authority.** The Chairman ruling *Common-opponent performance formula* was issued
**APPROVED**, states the formula in terms, and declares that "the coefficients 0.25 / 0.50 / 0.25
are canonical and exact" under the authorization line **DIRECT CHAIRMAN AUTHORITY**. It also
supersedes, explicitly, any earlier wording describing the formula as "some formula that looks
like" this structure — so the exactness of the coefficients is *issued*, not inferred from the
earlier hedged text. That earlier wording is preserved as the prior record and was not edited.
The ruling holds the OWP/OOWP construction semantics unchanged, keeps UNAVAILABLE fail-closed and
advancing to the next governed criterion, and states that it changes none of SOS, CCG rules,
postseason topology, G5 seed #5, FCS Elo policy, calibration parameters, Board authority, SOR or
SRS.

**What was wrong.** The module recorded `COMMON_OPPONENT_FORMULA_IS_CANONICAL = False` on the
grounds that no *mounted workbook* states the formula. Those workbooks predate the ruling, and
older artifact state does not outrank a later direct ruling. The authority hierarchy is:

```
older artifact state / open item  ->  later direct Chairman ruling  ->  successor governed authority
```

**Two layers, kept apart.** Layer A is the formula, governed here. Layer B is the OWP/OOWP
denominator and exclusion construction, governed separately by `R3-SOS-OWP-OOWP-SEMANTICS` and
**not reopened**. The two are asserted independently in both directions: a governed formula over
ungoverned semantics fails closed, and governed semantics under an ungoverned formula fails
closed too.

**The weights are the rule, not a parameter.** `require_governed_common_opponent_formula()` is
the affirmative gate. It checks the formula's status is `GOVERNED`, that the authority source is
the direct Chairman ruling (or a successor to it), that the weights are exactly
`0.25 / 0.50 / 0.25`, that the weights the module actually applies still match that record, that
the bound semantics are the governed R3 ones, and that `UNAVAILABLE` is still fail-closed.
`0.20/0.60/0.20`, `0.25/0.25/0.50` and a weight a hair off all raise. `TEST_FIXTURE`,
`PROPOSAL`, `OPEN`, `UNRESOLVED` and pre-ruling historical evidence cannot promote themselves
whatever numbers they carry. Governed use goes through `governed_common_opponent_score()`;
nothing reads a boolean and hopes.

**Nothing historical was rewritten.** `18_ACC_POLICY_REFERENCE` ACC-EXT-08 stays exactly as it
is and is cited as evidence of the prior state, not as authority against the later ruling. The
previous status string is preserved verbatim as `COMMON_OPPONENT_FORMULA_PRIOR_STATUS`, and
`PRE_RULING_COMMON_OPPONENT_FORMULA` keeps the pre-ruling record constructible so a test can
prove it cannot promote itself. No Chairman ruling ID was fabricated — `chairman_ruling_id`
stays `null`, and `R4-COMMON-OPP-FORMULA` is a locally assigned convergence handle.

**No production path was invented.** The committee and A8/ECL tiebreak chains still receive an
injected scorer exactly as before. The gate exists so future production wiring cannot
legitimately obtain governed authority without validating it first.

**Blockers unchanged at nine** — seven calibration, one Board I-K artifact custody, one FCS
model-scale adapter. None retired, none opened, and no common-opponent blocker was created
because the classification changed.

## What was attempted and could not be completed

| Item | Result |
| --- | --- |
| Board I-K artifact mount | **`BOARD_IK_ARTIFACT_NOT_ACCESSIBLE_TO_AGENT`** |
| Canonical SRS evidence mount | **`CANONICAL_SRS_EVIDENCE_NOT_ACCESSIBLE_TO_AGENT`** |

The approved Board-of-Record binary is not present in this environment. A filesystem-wide SHA-256
sweep of every workbook found no match for
`6b4cec1e48b34cb9eca5c224f5ef8750cca5acc40ecfd0bc42ed62976cbd4c9a`. The only files bearing that
name are ephemeral pytest fixtures of 49 bytes; a test fixture is never promoted to production
authority. Board I-H was not substituted and nothing was fabricated, so
`inputs.board_of_record_i_k` stays open and the expected count is 9 rather than 8.

No canonical SRS specification, reference implementation or validation anchor is present either.
The SRS claim boundary is therefore **unchanged**: `MATHEMATICALLY_VERIFIED`, explicitly
`NOT_VALIDATED_AGAINST_CANONICAL_ANCHORS`. Absence here is absence from this environment, not a
claim that canonical SRS does not exist in the broader project. No new execution blocker was
created, because governed execution does not currently require those anchors.

## Live blockers after R3 (9)

Six `calibration.*` · `governance.GAME_SD_CALIBRATION_OPEN` ·
`model_scale.FCS_ELO_1250_TO_V3_POINT_SCALE_ADAPTER` · `inputs.board_of_record_i_k`

Seven are calibration, one is engineering/model-scale, one is artifact custody. **No governance
blocker remains** — governance work is off the primary critical path.


---

# B1 — Board-of-Record artifact custody

**RESOLVED — by artifact custody, not by ruling.** Base `eb5e3e7`.

`inputs.board_of_record_i_k` was never a policy question, and it is not closed by one. R2
named a single artifact. R3 and R4 went further and recorded the SHA-256 that artifact must
carry — `6b4cec1e…4c9a` — while recording, in the same breath, that a filesystem-wide sweep
found no file with that digest. The approved binary has now been supplied. It hashes to
exactly the digest that was written down before it arrived.

| Item | Value |
| --- | --- |
| Controlled identity | `2026_Board_I-K_CANONICAL_APPROVED_R1_REISSUE.xlsx` |
| Delivered as | `2026_Board_I-K_CANONICAL_APPROVED_R1_REISSUE(3).xlsx` |
| SHA-256 | `6b4cec1e48b34cb9eca5c224f5ef8750cca5acc40ecfd0bc42ed62976cbd4c9a` |
| Bytes | 57,179 |
| Mounted at | `config/dynamic_weekly_mc_v3/governed/2026_Board_I-K_CANONICAL_APPROVED_R1_REISSUE.xlsx` |
| Provenance | `…/2026_Board_I-K_CANONICAL_APPROVED_R1_REISSUE.provenance.json` |
| Authority | SHA-256 digest equality |

## The two filenames

The delivered file carries a `(3)`. That is a duplicate-download marker applied by the
transferring client — not a revision, and not a second artifact. The proof is the digest:
the delivered bytes hash to the value the controlled identity already required, recorded
independently by R3 and R4 before any file was in hand.

Both spellings are therefore kept, and neither record is edited to agree with the other. The
mount carries the controlled identity R2 names; the delivery name is preserved verbatim in
the provenance record and remains what R3 and R4 say it is. Digest reconciles them; neither
filename is authority for anything.

## The gate that actually changed

The custody defect was not the missing file. It was that the gate could not tell the
difference.

* `require_board_of_record` accepted **any** file carrying the controlled filename.
* `config.execution_blockers` cleared the blocker whenever a file merely **existed** at the
  configured path — it did not check the name at all.

Between them, a 49-byte pytest stand-in named
`2026_Board_I-K_CANONICAL_APPROVED_R1_REISSUE.xlsx` — sha256 `f20b2fa5…78ebbc`, the very file
R4's sweep found and dismissed — satisfied production authority. Both gates now require
digest equality. The fixture is refused, and the harness that wrote it has been repointed at
the governed mount, so no test manufactures a board any more.

Rejections are tested, not asserted. Each of these passed the old gate:

| Offered | Refused because |
| --- | --- |
| The 49-byte fixture, correctly named | digest |
| The real board, re-saved through `openpyxl` | digest |
| The real board with one byte flipped, identical size | digest |
| Board I-H (`Model_Parameters_v2_5_APPROVED.xlsx`) under the board's name | digest |
| The correct bytes under a foreign filename | controlled identity |
| Unconfigured / non-existent path | fails closed |

Board I-H remains exactly where it was, as sheet `08_BOARD_IH_TOP25`, historical and
non-substitutable. Nothing about it changed.

## What this does not do

Custody proves *which* artifact is mounted. It does not read Board rows into anything.
CCG-TB3, COMMITTEE-TB4, A8/ECL-TB3 and CFP selection remain governed by their own
authorities and still fail closed on them. `BoardOfRecord.rows` is deliberately `0`.

## Live blockers after B1 (8)

Six `calibration.*` · `governance.GAME_SD_CALIBRATION_OPEN` ·
`model_scale.FCS_ELO_1250_TO_V3_POINT_SCALE_ADAPTER`

Nine to eight, retiring exactly one id, opening none. R3 had already written down which
eight would remain if the board ever mounted
(`R3_EXPECTED_LIVE_BLOCKERS_IF_BOARD_MOUNTED`); the live set now equals that projection
exactly. `blocker_report.board_mount_delta()` computes the transition rather than stating
it, and reports `unrelated_vanished` so a silent disappearance cannot hide behind a count.

Seven of the eight are calibration; one is engineering/model-scale. **Artifact custody has
left the live set** — but the model is no closer to running. Calibration data still does not
exist, and a mounted board is not a runnable model.

---

# F1 — FCS model-scale adapter lane

Lane scope: `model_scale.FCS_ELO_1250_TO_V3_POINT_SCALE_ADAPTER`, and nothing else. The FCS
*rating policy* is settled — ruling `R2-FCS-ELO-1250` fixes Elo 1250 — and is not reopened.

**Outcome: blocker RETAINED.** No governed mapping among Elo, Board rating and unified neutral
points exists in the mounted artifacts. The adapter *interface* and an experimental calibration
harness are implemented; the canonical point value stays unset.

## What the search covered

Every string cell of all eight mounted governed workbooks and the canonical team master, plus
every register, ruling and open item. Two transforms touch these axes. **Both reproduce exactly
from this repository, and neither is quoted rather than recomputed.**

| Transform | Source | Reproduction |
| --- | --- | --- |
| `primary_elo = 999.986237 × board_power_H + 1099.999878` | `POWER_CRUNCH…v2_2.xlsx!Build Manifest` | 121 board-rated rows, max residual `0.014932610474716057`, rounding to the manifest's own `0.0149` |
| `points = 14 × UnifiedMasterZ` | `2026_CFB…Unified_Power_Ratings.xlsx!Ensemble Parameters`, `!Data Dictionary` | 121 FBS rows, error `0.0` for Z, points and power index |

where `UnifiedMasterZ = 0.25·z(TrueSkill) + 0.25·z(Litkenhous) + 0.25·z(PureBaxter) +
0.25·mean(z(Board I-H), z(Board J-B))`.

## Why they do not compose into an Elo → points rule

Three independent reasons, each sufficient on its own.

1. **The direction is closed.** The manifest issues Board → Elo. Ruling `R2-FCS-ELO-1250`
   forbids inverting it and forbids the Board equivalent as a conversion rule.
2. **Board I-H is one eighth of the composite.** Even with the inversion permitted, the output is
   a Board I-H power value carrying 12.5% weight. TrueSkill, Litkenhous and Pure Baxter supply
   **no value for any FCS entity**, and the ratings workbook holds 121 FBS rows and zero FCS
   rows. A Unified Master Z cannot be formed from one eighth of its inputs.
3. **The Board axis is blank by canonical policy for exactly these entities.**
   `Board columns for FCS: BLANK — Board-equivalent recorded not issued`; all 13 rows carry
   `board_power_H = 'UNRATED'`.

Reproduced and recorded so the closed route is unmistakable: the "recorded not issued" Board
equivalent `0.297514` **is** the inverted transform applied to the superseded composite —
`(1397.51 − 1099.999878) / 999.986237 = 0.2975142166881642`. Applying the same inversion to the
newly ruled Elo yields `0.15000218648009245`. That is the same closed route with a new number,
and `fcs_scale.reject_manufactured_board_equivalent` refuses it by name.

## The gap is two gaps

| Gap | Extent | Evidence |
| --- | --- | --- |
| Unified points for an FCS entity | all 13 identities, all 15 FBS-v-FCS games (weeks 2, 3, 4, 5, 12) | `preseason_strength_points = None`; `engine._initialize_states` raises |
| HFA modifier for an FCS entity **hosting** | 3 games: `G0019` SJSU@EMU, `G0213` SDSU@TOL, `G0224` BOISE@WMU | `Team.hfa_modifier = None`; `SCHED-HFA-BASE` is `modifier × 3.5`; the engine reads `home_team.hfa_modifier or 1.0`, which would silently grant an ungoverned entity the full FBS home edge |

The second gap was not previously surfaced. It is recorded as evidence requirement `FCS-SCALE-C1`
rather than patched, because choosing a modifier is exactly the invention this lane refuses.

## Exact evidence required to close the blocker

Either route closes it. Both need `FCS-SCALE-C1` and `FCS-SCALE-C2`.

**Route A — issued scale rule**

- `FCS-SCALE-A1` — the exact unified neutral-field points value at Elo 1250, or an explicit
  Elo-to-points function with its coefficients stated in the ruling itself.
- `FCS-SCALE-A2` — an express statement that the value is *issued*, and derived neither from the
  Board I-H equivalent nor from inverting the Elo/Board transform.
- `FCS-SCALE-A3` — whether one value covers all 13 entities or each is rated separately. Every
  mounted source treats the 13 as undifferentiated; carrying that onto the points axis would be
  an assumption, and refusing to carry it would be another.
- `FCS-SCALE-A4` — whether the value participates in weekly rerating or stays fixed. V2.1 froze
  ratings for the season; V3 reretes weekly, and an FCS entity plays exactly one game.

**Route B — calibrated scale rule**

- `FCS-SCALE-B1` — a mounted governed **historical** observation set of completed FBS-v-FCS games
  with actual margins, passing `calibration.register_dataset`. None is mounted. The 15 fixtures in
  this repository are 2026 games that have not been played; they are the thing to be predicted and
  can never be their own training data.
- `FCS-SCALE-B2` — a named evaluation objective for this parameter.
- `FCS-SCALE-B3` — training / validation / holdout separation, promotion evidence from holdout.

**Both routes**

- `FCS-SCALE-C1` — the FCS home-venue HFA modifier (above).
- `FCS-SCALE-C2` — the explicit human token `APPROVE_V3_FCS_POINT_SCALE_PROMOTION::<RULING_ID>`
  plus a named promotion authority. The calibration token is a separate namespace and does not
  authorise this parameter.

## Explicitly insufficient

Recorded in `fcs_scale.INSUFFICIENT_EVIDENCE` so a reviewer can see each was considered and
rejected rather than overlooked: inverting the Elo/Board transform; the Board equivalents
`0.294` / `0.297` / `0.297514`; the Board equivalent computable from Elo 1250; reading `1250` or
`1397.51` as football points; running the four-family ensemble for an entity supplying none of the
families; fitting any affine, logistic or inverse transform on the 121 FBS rows and extrapolating
it outside that population; and V2.1's bridge, which is the closed route itself.

## What was built

- `fcs_scale.py` — the reproductions, the recorded search result, the `FcsPointScaleAdapter`
  interface, the fail-closed `GovernedFcsPointScaleAdapter`, the never-consumable
  `ExperimentalFcsPointScaleAdapter`, the refusal surface, the evidence register, and the
  experimental promotion gate.
- `config/dynamic_weekly_mc_v3/experimental/fcs_point_scale_regimes.json` — ships with **zero**
  regimes. Authoring a candidate points value would invent the calibration the blocker records as
  missing.
- `CANONICAL_FCS_UNIFIED_POINTS` and `CANONICAL_FCS_HOME_HFA_MODIFIER` are `None`, and no harness
  path can set either. Promotion never writes canonical config.
- 100 lane tests: both reproductions, all 13 identities individually, all 15 FBS-v-FCS games
  individually, the three FCS-hosted games, every refusal, the interface, the harness, the
  promotion gate, and the two blocker epochs below.

No blocker was retired, none was opened, no calibration value was promoted, no simulation was run
and no probability artifact was produced.

## Lane epoch — this section was written against the nine-blocker base

Lane F1 ran on frozen base `eb5e3e7`, where the live set was the nine listed under *Live
blockers after R3*. Lane B1 ran independently on the same base and retired exactly one id,
`inputs.board_of_record_i_k`, on artifact-custody evidence. Both are recorded above.

F1 retired nothing and opened nothing, so the integrated live set is B1's eight — the seven
calibration items plus `model_scale.FCS_ELO_1250_TO_V3_POINT_SCALE_ADAPTER`. This lane's own
blocker is live in both epochs and is unaffected by the mount: a Board-of-Record artifact
carries no FCS row and no Elo-to-points rule. `blocker_report.f1_integration_delta()` computes
the lane-base → integrated transition rather than stating it, and
`V3_GOVERNANCE_STATUS_F1.json` records the nine as
`live_blockers_at_lane_base` and the eight as `integrated_live_blockers`, so the historical
observation is not read as the current state.
