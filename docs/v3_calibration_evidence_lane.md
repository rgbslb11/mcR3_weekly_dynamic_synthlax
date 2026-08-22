# OPERATION SYTHALAX — Calibration Evidence Lane

## Governed historical observation corpus

Branch: `claude/v3-calibration-evidence`
Frozen base: `1a79c942386cf2441f1f64ae091f972030c713bc`
Disposition: **BLOCKED ON SOURCE DATA — EVIDENCE PIPELINE HARDENED, CORPUS REFUSED ON PROVENANCE**

Machine-readable record: `reference/dynamic_weekly_mc_v3/V3_CALIBRATION_EVIDENCE_DISCOVERY_R5.json`.

No parameter was promoted, no blocker retired, no allowlist widened, no canonical
writer built, no FCS point adapter installed, and no season Monte Carlo run.

---

## 1. The short version

Historical game data does exist locally, in quantity — roughly 5,100 games across
eight seasons, staged and well documented. Almost all of it is **synthetic**, and
the sources say so themselves, in their own control documents, unprompted.

The one genuinely observed subset is **550 real 2024 FBS regular-season games**.
It fails every one of the contract's four minimum-volume floors, and eleven of the
twenty governed fields are missing from it — including every pregame field the
primary objective is built on.

So the answer to "is there evidence?" is: there is a great deal of data, and no
admissible evidence. Those are different findings and the difference is the whole
result of this lane.

---

## 2. What was searched

The repository first, then the staged and adjacent local project locations. The
sweep covered every `csv`/`tsv`/`xlsx`/`xls`/`parquet`/`jsonl`/`db`/`sqlite` file
outside system directories — 11,359 files — narrowed to 6,189 football-relevant
paths, then to 1,250 CSVs which were grouped by header schema into 283 distinct
schemas, of which 68 carry result-like columns. Every corpus reported below was
opened and profiled directly.

`C:/Local-mcR3_audit_outputs` contains discovery reports from a prior lane. They
were read as pointers and every claim taken from them was re-derived from bytes
here. No web retrieval was performed; the instruction does not authorise it.

---

## 3. What was found, and why each is refused

| Source | Seasons | Games | Class | Disposition |
|---|---|---|---|---|
| Phase 4M verified week-by-week | 2006–2011 | 3,667 | RESEARCH_ONLY | Refused — synthetic |
| Phase 4H calibration base | 2006–2011 | 3,667 | RESEARCH_ONLY | Refused — same corpus |
| Power Crunch event stream | 2024–2025 | 1,481 | MIXED | 550 real, 931 synthetic |
| 2025 Synthetic Season LOCKED v3 | 2025 | 757 | SIMULATED | Refused — scores simulated |
| Power Crunch pregame states | 2024–2025 | 1,481 | ENGINE_OUTPUT | Refused — foreign scale |
| Baxter Ratings v1 | 2006–11, 24–25 | — | ENGINE_OUTPUT | Refused — season-final |
| Repository governed inputs | 2026 | 743 fixtures | GOVERNED | Refused — no scores |

Each refusal rests on the source's own words rather than on inference.

**2006–2011.** `PHASE4M_WEEK_BY_WEEK_CLEANUP_REPORT.md` opens: *"This package
consolidates the source-derived chronological sequence, week, and date fields for
all synthetic games from 2006 through 2011. ... No external or real-world schedule
was used."* The archive's `archive_scope.md` lists under **Excluded**: *"Claims
that historical synthetic results are real-world evidence."* Its `limitations.md`
records that the 2011 neutral-site narrative was withdrawn after *"contamination
between synthetic score blocks and auxiliary real-world/TV schedule notes"* was
found, and that *"all historical conclusions remain research-only."*

The data agrees with the documents. 2006 Week 1 in this corpus carries BYU 17 –
Florida 35, Texas 30 – California 24, and Duke 7 – NC St. 56. None of those are
real 2006 results.

**2025.** The `Certification` sheet of `2025 Synthetic Season LOCKED v3.xlsx`
carries a `provenance` field whose value is, verbatim:

> `SCHEDULE SYNTHETIC. SCORES SIMULATED. NCG result user-specified. Bowl names fictional.`

Its `Team Season` sheet carries `power_rating`, `target_rank` and `delta` columns:
the season was generated to hit a target rating structure. `GOVERNING_RULES.md`
states *"Every game in the certified season ledgers is official synthetic data."*

This is the corpus that would most improve a fit — 757 games, with `overtime_games
= 13` actually populated, which is the field `game_sd_points` most needs. It is
also the corpus the contract most clearly refuses, and the two facts are related:
fitting `game_sd_points` to simulated margins would measure the variance of the
score generator and report it as football's.

**2024.** The event stream carries its own `provenance` column, which is what made
this lane possible at all:

| provenance | season | games |
|---|---|---|
| `REAL` | 2024 | 550 |
| `SYNTH_BLOCK` | 2024 | 68 |
| `SYNTH_FILL` | 2024 | 90 |
| `SYNTH_POST` | 2024 | 16 |
| `OFFICIAL_SYNTHETIC_2025_LOCKED` | 2025 | 757 |

The 550 `REAL` rows are genuine observed results, traced in `INPUTS.md` to a
sports-reference 2024 schedule-and-results PDF.

---

## 4. One provenance chain, independently verified

`INPUTS.md` declares `registry/teams_2024.csv` at SHA-256
`f4c3114178eebec50d8a2912613a15bfd5a831e6dfe6131b944cea161472fb97`. The local file
`10_Source_Rulings/teams 2024.csv` hashes to exactly that value.

That matters. It means the declared lineage is hash-consistent against bytes that
are actually here, not merely a narrative. It is the reason the rest of the
`INPUTS.md` declaration is treated as credible.

It also has a limit. The **root** of that chain — the source PDF — is recorded as
living in an ephemeral uploads mount, and a filesystem sweep did not find it. The
chain is documented and one link is confirmed, but it cannot be closed to bytes in
this environment. Under the hardened pipeline that is a refusal, not a caveat.

---

## 5. The real subset, measured against the contract

550 games. One season. Regular season only.

| Contract floor | Required | Available | |
|---|---:|---:|---|
| Distinct seasons | 3 | 1 | fail |
| Total observations | 1,500 | 550 | fail |
| Holdout observations | 300 | 183 best case | fail |
| Weeks per team per season | 8 | 11 teams below | fail |

The holdout line deserves a note: 183 is one third of 550. There is no temporal
three-way partition of a 550-row corpus that clears a 300-row holdout floor. This
is not a split that needs tuning; it is a corpus that is too small by construction.

Field-by-field, of the twenty governed fields:

- **Available directly:** `season`, `week`, `actual_margin`.
- **Derivable deterministically:** `venue` (from `a_is_home` + `neutral`),
  `game_result`, `subsequent_outcomes`, `split`, `source_provenance`, and
  `game_id` — though the shipped key is not usable as-is (see §7).
- **Missing:** `event_time`, `pregame_team_rating`, `pregame_opponent_rating`,
  `expected_margin`, `prior_rating_state`, `observed_at`, `recorded_at`,
  `model_version`, `configuration_version`, and `team`/`opponent` as canonical ids.

Three available, six derivable, eleven missing — and the eleven are the
load-bearing ones. Every pregame field the primary objective is defined over is
absent.

---

## 6. The four fields awaiting admission

Availability was established. Admission was not requested, granted, or assumed,
and `governed_allowlist` is unchanged.

| Field | Availability on the real subset | Status |
|---|---|---|
| `games_played_to_date` | Available — `games_a_pre` in the pregame states | Still requires ruling |
| `game_type` | Derivable from `phase`, but constant on the real subset (regular season only) | Still requires ruling |
| `overtime_periods` | **Missing** — 0 of 550 rows populated; present only where scores are simulated | Still requires ruling |
| `opponent_division` | Degenerate — all 1,481 stream rows are FBS-vs-FBS | Still requires ruling |

The `overtime_periods` row is the sharpest finding here. The contract wants that
field specifically because untagged overtime inflates `game_sd_points` — *"the
exact direction of the unexplained 20.2 observation."* It is available only in the
part of the corpus where the scores were simulated.

---

## 7. Integrity findings

**Duplicate `game_id` — contract violation.** `T073vT114` appears twice. The key
scheme is team-pair keyed (`T<a>vT<b>`), so a repeated matchup collides:

```
T073vT114  2024 W0   SYNTH_BLOCK  Oregon State 16-24 Washington State  (no date)
T073vT114  2024 W13  REAL         Oregon State 41-38 Washington State  2024-11-24
```

The contract requires `game_id` to be *"unique within the dataset and stable across
re-ingestion."* Reported, not repaired — repairing a key inside a refused corpus is
work spent making an inadmissible source look conforming.

**No kickoff instant.** Zero of 550 real rows carry a time component; `game_date`
is date-only. The package's own block register flags this for 174 synthetic 2024
games; the gap is in fact total. `event_time` is the field the contract calls the
only one that can order two games inside a week, and therefore the only one that
can prove a holdout game post-dates its training data.

**2006–2011 chronology gaps.** 210 of 3,667 rows have no clean week, 330 no clean
date, 266 are `DATE_UNRESOLVED`. Recorded for completeness; immaterial while the
corpus is refused on provenance.

---

## 8. Identity reconciliation: designed, deliberately not performed

The deterministic design is: resolve free-text names through
`2026_TEAM_CANONICAL_MASTER_v2_LLM_GROUNDING.md`
(SHA-256 `fd8fcb1b…c48a83a0`), refuse rather than drop unresolved names, and carry
the unresolved list into the evidence envelope.
`calibration_evidence.IdentityReconciliation` enforces exactly that and refuses an
incomplete mapping.

It was not run against the 550 real games, and the reason is substantive. The
canonical universe is the project's **synthetic 2026 FBS** — it contains
conferences and members that never existed in real 2024, and omits real 2024
members. A high name-match rate between the two would be an artifact of schools
sharing names, not evidence that the same competitive entities are being compared.
Producing that mapping would have made an inadmissible corpus look one step closer
to admissible, which is the opposite of what this lane is for.

---

## 9. Source data is necessary, not sufficient

Even a perfect corpus would not yield `expected_margin` today.

The contract requires `expected_margin` in V3 point units **and** a named
rating-to-margin transform, because without the transform
`weekly_performance_residual_coefficient` is unidentifiable: any residual can be
absorbed by rescaling the transform instead. V3 has no ratified transform.
`sor.py` records `P_TO_STRENGTH_TRANSFORM` and `REFERENCE_HFA` as unratified, and
all six calibration values in `v3_experimental.json` remain `null`.

A future lane that mounts a conforming corpus will still be blocked here.

---

## 10. CAL-R2, closed

The weakness was reproduced before it was fixed.

`calibration.register_dataset` reads real bytes and records a real digest. But
`CalibrationDataset` is an ordinary frozen dataclass, and
`bind_promotion_evidence` compares `experiment.dataset_sha256` against
`dataset.sha256` — two caller-supplied strings. So this binds:

```python
typed = CalibrationDataset(
    dataset_id="HISTORICAL_GAME_RESULT_OBSERVATION_SET",
    path=tmp_path / "never-written.csv",   # never created
    sha256="00" * 32,                      # never computed
    rows=1500,                             # never counted
    columns=REQUIRED_OBSERVATION_COLUMNS,
)
bind_promotion_evidence(regime, evidence={...: 0.0001},
                        experiment=..., dataset=typed)
# -> {"evidence_bound": True, ...}
```

No file is opened anywhere in that path. The digest is a field agreeing with
another field. That probe is retained as the **first test** in
`test_r5_calibration_evidence_binding.py`, so the fix is anchored to a
demonstrated defect rather than an asserted one.

### The fix

`src/ncaaf_engine/simulation/dynamic_weekly_mc_v3/calibration_evidence.py`.

The fix is not a stronger comparison between two strings. It is to **re-derive the
evidence from bytes at binding time**. The mount receipt is re-read and re-hashed;
the dataset is re-registered from disk, so schema, row count, allowlist,
duplicate-column, ragged-row and forbidden-signal checks all re-run against the
bytes present *now*.

Ten bindings are required, and they are the ten the instruction names:

`actual_bytes` · `sha256` · `source_authority` · `retrieval_record` · `schema` ·
`row_count` · `team_identity_reconciliation` · `temporal_split` ·
`experiment_input_digest` · `experiment_output_digest`

An envelope missing any one is refused whole, because a partial chain reads as a
complete one once it is summarised.

Also added:

- **Source authority classes.** Only `GOVERNED_RESULT_SOURCE` may be mounted.
  `RESEARCH_ONLY`, `ENGINE_OUTPUT`, `SIMULATED_OR_SYNTHETIC` and `UNKNOWN` are all
  refused — `UNKNOWN` included, because an unclassified source is the one nobody
  has checked.
- **Synthetic refusal at mount.** A source whose declared provenance matches
  `SYNTHETIC_PROVENANCE_PATTERNS` is refused before it is hashed, so a refused
  source never acquires a digest that could later be quoted as an acceptance. The
  test for this uses the exact string the 2025 workbook carries.
- **Minimum volume, now enforced.** The contract stated four floors and nothing
  refused a corpus that failed them. `require_minimum_volume` does, and it is a
  required step in envelope assembly. Its test asserts refusal of the precise
  shape this lane found: one season, 550 observations, 183 holdout.

The strongest output the module can produce is
`EVIDENCE_BOUND_BYTES_REVERIFIED_AT_BINDING`, which reports
`promotion_authorised: false` and `writes_canonical_config: false`. It is a
description of evidence, not an authorisation.

`calibration.bind_promotion_evidence` was **not** tightened. This lane has no
authority to narrow ruling R2-CAL-OBJECTIVE, so the weaker path keeps its
behaviour and its `EVIDENCE_UNBOUND` stamp; the stronger path is purely additive.

---

## 11. FCS scale — evidence insufficient, blocker retained

`FCS Elo = 1250` is untouched and not reopened. No algebraic conversion was
attempted and no point value was produced.

There are **zero admissible FBS-vs-FCS observations**:

- All 1,481 rows of the 2024–2025 stream are FBS-vs-FBS.
- The 550 real 2024 observations contain no FCS opponent.
- The 2006–2011 corpus has 69 games involving an FCS side — but 63 fall in 2011
  alone, and the whole corpus is refused as synthetic and research-only.

`model_scale.FCS_ELO_1250_TO_V3_POINT_SCALE_ADAPTER` remains open. FCS model-scale
research is recorded separately from calibration-parameter research and neither
borrowed evidence from the other.

---

## 12. On margin SD 20.2

The signed margin standard deviation of the 550 real 2024 observations is
**19.764 points**. It sits close to the recorded 20.2, and that proximity is not
corroboration.

19.764 is the *unconditional* dispersion of outcomes. A pregame model that
explains any strength difference at all must produce a residual SD below it. So
the figure bounds `game_sd_points` from above under this corpus and does nothing
to locate it — and the corpus is a season short and 950 observations short in any
case. Open item `ENG-CAL-MARGIN` is untouched and 20.2 remains unpromoted.

---

## 13. The decision this lane cannot make

There are roughly 4,600 locally available synthetic games with scores, weeks,
sites, overtime tags, and leak-free walk-forward pregame states. They are refused
by one clause: `synthetic_content: REFUSED`.

That clause was almost certainly written to stop the V2.1 static control workbook
— 10,000 simulated seasons of the engine's own beliefs — from being scored against
the engine that produced it. Whether it also reaches a *project synthetic
universe*, which is the universe the V3 model actually predicts, is a different
question, and a live one: the 2026 season V3 forecasts is itself synthetic, so a
literal reading refuses every corpus the model's own domain can ever produce.

Both readings are defensible and they lead to opposite programmes. Resolving it by
picking the convenient one is exactly the failure mode the contract exists to
prevent, so it is raised as a ruling request and nothing was mounted under either
reading.

One distinction is worth putting in front of that ruling: the 2025 ledger's scores
were generated against a target rating structure (`power_rating`, `target_rank`,
`delta`). Even a ruling that admits the synthetic universe in general should
probably not admit a season whose margins were fitted to a rating table, because
`game_sd_points` fitted to it would recover the generator's dispersion rather than
the universe's.

---

## 14. To unblock

1. Supply a real-world corpus of ≥3 seasons, ≥1,500 observations, ≥300 holdout,
   ≥8 games per team per season, **with kickoff instants**; or
2. Issue a ruling defining a governed synthetic-universe observation authority and
   stating explicitly whether `synthetic_content` reaches it (see §13);
3. Ratify `P_TO_STRENGTH_TRANSFORM` and `REFERENCE_HFA`, without which
   `expected_margin` cannot exist in V3 units (§9);
4. Rule on the four unadmitted fields, with §6's availability evidence in front of
   the decision.

Steps 1-or-2 and 3 are both required. Neither alone unblocks calibration.

---

## 15. State

- Tests: **546 full**, **487 V3** — up from 520 / 461 at the frozen base, +26 new,
  no existing test modified.
- `config.py` untouched, in both locations. `v3_experimental.json` untouched; all
  six calibration values remain `null`.
- `V3_CALIBRATION_DATA_CONTRACT.json` untouched; `governed_allowlist` unchanged.
- Blockers: **8 before, 8 after.** None retired, none opened.

Two environment defects were cleared to reproduce the baseline, neither a
repository defect: `sqlalchemy`, `alembic`, `fastapi` and `httpx` are declared in
`pyproject.toml` but were absent from the interpreter, and pytest's default
`basetemp` is not enumerable here, so runs use an explicit `--basetemp`.
