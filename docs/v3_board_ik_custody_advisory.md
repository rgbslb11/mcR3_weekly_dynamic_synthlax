# Board I-K Custody Hardening Advisory

Post-freeze Lane A. Scope: Board-of-Record custody only. Nothing here decides
calibration, FCS scale, SOR, SRS, SOS/OWP/OOWP, the common-opponent formula,
postseason, G5, or Monte Carlo.

## What was wrong

Five defects were reported and all five were reproduced against the frozen base
`eb5e3e7` before anything was changed:

| # | Reported | Verified |
|---|----------|----------|
| 1 | Loader expects a filename lacking `(3)` | Yes — `board_of_record.py` compared `path.name` against a constant without the suffix |
| 2 | Computes a SHA-256 but does not enforce an expected digest | Yes — the digest was recorded into a status dict and never compared |
| 3 | Does not expose usable Board rows | Yes — `BoardOfRecord.rows` was hard-coded to `0` |
| 4 | Would reject the approved artifact on filename | Yes — as delivered, `...REISSUE(3).xlsx` fails the name test |
| 5 | No approved artifact mounted in the checkout | Yes — no Board workbook was present under `reference/.../inputs` |

The deeper problem was defect 2 combined with the configuration gate. The gate
asked only whether a file *existed* at the configured path. A 49-byte text file
carrying the right name cleared it — and the test harness was mounting exactly
such a file.

## The authority rule

**Content identity is authoritative. A filename is never authority.**

This is not a stylistic preference; it is forced by how the artifact is
delivered. Four copies of the approved bytes were found under four different
names, all four with the identical digest
`6b4cec1e…cbd4c9a`:

```
2026_Board_I-K_CANONICAL_APPROVED_R1_REISSUE.xlsx
2026_Board_I-K_CANONICAL_APPROVED_R1_REISSUE(3)(1).xlsx
2026_Board_I-K_CANONICAL_APPROVED_R1_REISSUE(3)(1) (1).xlsx
2026_Board_I-K_CANONICAL_APPROVED_R1_REISSUE(3)(1) (2).xlsx
```

The `(3)` and `(1)` suffixes are browser download de-duplication, not governed
identity. `Board_I-K_Artifact_Register_R1-R3_FINAL.xlsx` registers the artifact
without any suffix, with status `APPROVED CANONICAL — CURRENT`. That resolves
the filename discrepancy without promoting the filename to authority: the name
is a label, the digest decides.

The rule cuts both ways, and the suite tests both directions:

* approved bytes verify under **any** name, including a deliberately misleading
  `Board_I-H_historical_evidence.xlsx`;
* non-approved bytes are refused under **every** name, including the exact
  canonical filename.

## Two digests, not one

Custody binds two independent digests, mirroring the treatment the schedule
artifact already receives in `provenance.py`:

* **binary** — SHA-256 of the `.xlsx` file. Certifies the exact distributed
  artifact. Registered value `6b4cec1e…cbd4c9a`, 57 179 bytes.
* **content** — SHA-256 of `'Board I-K'!A3:Q124` serialized under HASH-SPEC-V1.
  Certifies the governed rows independently of workbook packaging. Registered
  value `23f83a34…11ecde`.

The content digest is *reproduced*, not asserted. HASH-SPEC-V1 specifies
"exact stored value with round-trip precision"; the value that actually
reproduces the registered digest is `%.17g`, and Python's shortest round-trip
`repr` does **not**. The difference is silent — every cell still round-trips —
so the format is pinned explicitly in `_hash_spec_v1_cell` rather than left to a
default. Anyone re-deriving this hash will hit the same trap.

Both digests must verify. A re-saved copy keeps its content hash and loses its
binary hash; for the schedule a ruling accepts that trade, but **no ruling
accepts it for the Board of Record**, so a re-save is refused even though its
rows are provably intact. Tracking both is what lets a reviewer tell "the file
was re-saved" (custody) from "the rows were edited" (fatal).

## What the loader now enforces

Ordered so the most specific refusal wins, and no Board row is exposed until
every gate passes:

1. configured → 2. mounted → 3. approved binary digest → 4. readable `.xlsx`
container → 5. reproduced content digest → 6. schema → 7. identity →
8. governed universe (when a canonical index is supplied).

Mismatches are **named**, not merely refused. `KNOWN_NON_APPROVED_SHA256`
identifies the superseded predecessor, the unapproved candidates and the
predecessor board by digest, so an operator gets "you mounted the superseded
predecessor" rather than "hash mismatch".

Schema is exact: 17 declared columns in declared order, header at row 3, exactly
121 data rows. A renamed or reordered column is a failure, not a tolerable
variant — the content digest is computed over the declared order, so tolerating
drift there would silently invalidate the hash.

Identity is bound to the governed universe: 121 unique `Master Team ID`s,
ranks 1–121 contiguous, equal as a set to the 121 `FBS_MEMBER` master ids in the
canonical index. Schedule-only FCS entities carry no `master_team_id` at all, so
an FCS row can only arrive as an id the FBS mapping does not contain, and is
refused as an unexpected entity rather than silently dropped. The universe is
unchanged: **121 FBS_MEMBER, 13 SCHEDULE_ONLY_FCS, 134 schedule identities**.

## Downstream requirement

Consumers (CCG-TB3, A8/ECL-TB3, CFP selection) rank on an ordered tuple of
schedule ids. The Board publishes `Master Team ID`. `order_by_schedule_id`
maps between them through the canonical team index and **never** through team
names, which are not governed identifiers. The columns actually required
downstream are `Rank I-K` and `Master Team ID`; `Team`, `Short`, `Conference`,
`Committee` and `Power` are carried for diagnostics and tie inspection.

## What this deliberately does not decide

Mounting the Board of Record answers a custody question. It must not be read as
answering a governance question that no ruling has answered:

* **COMMITTEE-TB4 first-November fallback** stays open.
  `committee_policy.FIRST_BOARD_TB4_BLOCKER` is untouched. Board I-K is the
  Board of Record, but nothing designates it as the TB4 fallback, and this lane
  does not designate it either. A test pins that.
* **Board I-H** remains at `08_BOARD_IH_TOP25` as historical/superseded
  evidence. It was not substituted, moved, or edited.
* The approved workbook was **not edited**. It was copied byte-for-byte and its
  digest re-verified after the copy.

## Internal tension worth recording

The approved workbook's own `Rulings` sheet carries a row `STATUS → CANDIDATE`
("Publication-ready; not promoted"), while its title row and filename say
`APPROVED CANONICAL — R1 REISSUE`. This is not a defect in the mount: the
R1–R3 FINAL artifact register — the later, governing record — lists this exact
digest as `APPROVED CANONICAL — CURRENT`, and ruling R2-BOARD-OF-RECORD names
it as the Board of Record. The in-workbook `STATUS` row is an earlier
self-description that the register supersedes. It is recorded here so a
reviewer who opens the workbook and sees `CANDIDATE` is not left to wonder.

## Residual risk

* Custody proves the artifact is the approved one. It does not prove the
  *numbers* are right; the workbook's own `Validation` sheet reports its
  invariants and is taken as evidence, not re-derived here.
* `KNOWN_NON_APPROVED_SHA256` is an aid, not a boundary. An unknown digest is
  refused exactly as firmly as a known-bad one; the register only improves the
  message.
* If the Chairman re-issues the Board, both registered digests change. They are
  module constants with the register named in their comments, and the negative
  paths will fail loudly rather than drift.
