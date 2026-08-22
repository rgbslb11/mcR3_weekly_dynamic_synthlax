# OPERATION SYTHALAX — Historical Observation Corpus (R6)

## What this lane produced

A real, provenance-bound corpus of **2,241 college-football scored-game
observations** across four seasons (2021–2024), built from bytes retrieved from
the NCAA's own scoreboard feed, reconciled to the governed canonical team
identity system, keyed by a collision-free game identifier, ordered by
source-published start instants, and partitioned into whole-season
training / validation / holdout splits that pass every minimum-volume floor the
data contract states.

It calibrates nothing. It promotes nothing. It retires no blocker. All eight
formal blockers stand, the six calibration values remain `null`, FCS Elo remains
1250 with no unified-point mapping, and `experiments_run` is 0.

R5 ended `CALIBRATION_EVIDENCE_BLOCKED_ON_SOURCE_DATA` after finding no
admissible corpus anywhere on the filesystem. This lane did not re-search the
filesystem. It went and got the data.

---

## 1. The short version

| | R5 finding | R6 outcome |
|---|---|---|
| Admissible corpus | none mounted | 2,241 observations, 4 seasons |
| Kickoff instants | zero | every admitted row |
| Game identity | team-pair key, collided on `T073vT114` | NCAA game id, season-namespaced, 0 collisions |
| Repeat matchups | collapsed into one colliding key | 12 carried with distinct identifiers |
| FBS-vs-FCS observations | zero admissible | 43 identified and inventoried |
| Minimum volume | failed on all four floors | passes all four |
| Temporal split | not constructible | training 1,080 / validation 598 / holdout 563 |

What R6 did **not** solve is as important, and is set out in §8.

---

## 2. The source

`https://data.ncaa.com/casablanca/scoreboard/football/{division}/{season}/{week}/scoreboard.json`

This is the feed behind the NCAA's own published scoreboard — the NCAA
publishing its own results, which is tier 1 of the lane's source hierarchy. It
is addressable per season, per division and per week, so acquisition is a list
of URLs rather than a crawl, and every retrieval is exactly repeatable.

174 files were captured across seasons 2021–2025 and both the `fbs` and `fcs`
scoreboards, totalling 11,777,373 raw bytes. Each is stored gzip-wrapped with
`mtime=0` and bound by **two** digests: `stored_sha256` over the container git
holds, and `raw_sha256` over the response body inside it. `raw_sha256` is the
digest custody is asserted over.

The gzip wrapper is not compression for its own sake. `.gitattributes`
normalises `*.json` to LF on checkout, and a raw capture that a checkout can
rewrite is not a raw capture. `.json.gz` falls under the `* -text` rule and is
preserved byte for byte.

Two sources were considered and not used. `api.collegefootballdata.com` returns
401 without a registered key. Sports-reference material was avoided: R5's one
real subset traced to a sports-reference PDF whose first link could not be
re-read in this environment, and an aggregator whose lineage cannot be
re-verified is exactly what the source hierarchy warns against.

---

## 3. Division is read from the source, not inferred

The `fbs` and `fcs` scoreboards are distinct game sets. A game appears in both
exactly when it crosses divisions. So:

- in `fbs` only → both participants FBS
- in both → one FBS, one FCS
- in `fcs` only → both FCS

Team division then follows from appearing in an FBS-only game. Nothing is
inferred from a conference name, which matters because a hand-written
conference allowlist is an assumption wearing a lookup table — and the feed
reports `Top 25` as a conference, so such a list would have needed exceptions
from the start.

---

## 4. Team identity

Resolved against `2026_TEAM_CANONICAL_MASTER_v2_LLM_GROUNDING.md`, pinned at
`fd8fcb1bec40e26168d600e9cdb8fbf2de6a421fe13218face588a48c48a83a0` — the same
digest R5 recorded. Three rules, tried in order, each requiring an **exact** hit
on a canonical key:

1. **`EXACT_CANONICAL_KEY`** — the NCAA short name is already a canonical
   `schedule_id`, `team_name`, `abbreviated_name` or `aka_name`.
2. **`NCAA_CHAR6_CANONICAL_KEY`** — the NCAA's own six-character team code is a
   canonical key. This is the source's identifier matching the master's
   identifier; it is not an alias authored here. It is what resolves
   `Southern California` → `USC` and `Army West Point` → `ARMY`.
3. **`NCAA_ABBREVIATION_EXPANSION`** — one of the NCAA house-style
   abbreviations (`St.` → `State`, `Mich.` → `Michigan`, …) is expanded and the
   result must land on an exact canonical key. A wrong expansion produces no
   match rather than a wrong match.

Anything else is `UNRESOLVED_ENTITY`. Its games are excluded with a reason and
its name is listed. 116 source entities went unresolved — almost all FCS
schools the 2026 master does not carry, plus roughly a dozen real FBS programs
it also does not carry (Akron, Ball State, Bowling Green, Kent State, Ohio,
Liberty, James Madison, Massachusetts, Miami (OH), and others).

Two safety properties are enforced rather than hoped for:

**Source-side qualifiers are never stripped.** `Miami (FL)` resolves through the
NCAA char6 code `MIAMI`; `Miami (OH)` (char6 `MIA OH`) resolves to nothing and
its games are excluded. Discarding a disambiguator to force a match is precisely
the silent mis-mapping the resolver exists to prevent.

**Resolution is injective within a season.** Two NCAA entities landing on one
canonical `schedule_id` refuses both, because no source fact says which is
correct.

### The canonical universe is synthetic, and it shows

The 2026 canonical master is authoritative for a **synthetic** universe, and its
membership is not the membership of any real season. It classifies Toledo,
Western Michigan, Arkansas State, Charlotte, Eastern Michigan, Louisiana,
Louisiana-Monroe and Western Kentucky as `SCHEDULE_ONLY_FCS`, and it classifies
Colgate, Cornell, Harvard, Holy Cross, Lehigh, Penn, Princeton, Yale and North
Dakota State as `FBS_MEMBER`.

Those are facts about a synthetic 2026 season, not about 2021–2024 football.
This corpus therefore keeps two axes strictly apart:

- **observed division** — FBS or FCS, read from the NCAA feed. This is what
  admission uses and what the counts report.
- **canonical `entity_scope` / `2026_division`** — identity metadata about the
  synthetic universe. Never reported as the division of a historical game.

Arkansas State carries a canonical FCS label, is observed FBS, and is in the
corpus. Colgate carries a canonical `FBS_MEMBER` label, is observed FCS, and is
excluded as cross-division. Both directions are asserted in the test suite.

---

## 5. Game identity

**Scheme: `NCAA-<season>-<ncaa_game_id>`.**

The NCAA publishes its own game identifier, which is the authoritative
disambiguator the mission's hierarchy names first. It is namespaced by season
because the feed reuses identifier spaces across seasons — one bare identifier
does recur across the retrieved range.

R5's failure was a team-pair key, `T073vT114`, colliding on a repeated Oregon
State / Washington State matchup. That failure mode is gone: the corpus carries
**12 repeat matchups** — regular-season games and their conference-championship
rematches, plus Hawaii and New Mexico State meeting twice in 2021 — each with
distinct identifiers, distinct weeks and distinct start instants.

The converse problem is real too, and is refused rather than repaired. The feed
sometimes publishes one game twice under two identifiers. Two records sharing a
season, a canonical team pair and a source week are one game published twice —
two teams never meet twice in one week — so **both are refused** under
`DUPLICATE_OR_AMBIGUOUS_GAME_ID`. Picking one would be choosing which of two
disagreeing records is true.

21 further rows were refused as `MISSING_SOURCE_GAME_IDENTIFIER`: the source
published them with an empty `gameID`, so no authoritative identity exists to
key them on.

---

## 6. Chronology and walk-forward safety

Every admitted observation carries `event_time`, derived from the source's
`startTimeEpoch` — a Unix instant, so unambiguous without a timezone
assumption. R5's stream had zero kickoff instants; this one has no row without
one.

Precision is stated exactly and not overstated. These are **scheduled start
instants published by the source**, not observed kickoffs, and they are not
represented as observed kickoffs anywhere.

The walk-forward rule that follows is deliberately conservative:

> A game may be ordered before another only on a strictly earlier start instant.
> Games sharing an instant are simultaneous and neither may inform the other.
> Because a game's result is observable only after it *ends*, and no end instant
> is published, a start-instant ordering is sufficient to **order** games but
> **not** sufficient to prove that an earlier-starting game had finished before a
> later-starting one began. Any walk-forward feature derivation must therefore
> key on a completed-game boundary this source does not supply, or restrict
> itself to whole-day or whole-week boundaries.

That limitation does not touch the splits, which are whole seasons: every
ordering comparison the temporal-split gate makes is separated by months.

No team plays two admitted games at one instant. The feed carries no bowl or
playoff games in any retrieved season, so the corpus contains no postseason
observation at all — which removes the postseason leakage path rather than
managing it.

---

## 7. FACT / DERIVED / ASSUMPTION / BLOCKED

**FACT** — read directly from admitted source bytes:
`season`, `week`, `event_time`, `recorded_at`, `source_provenance`, and the raw
scores and participants behind the derived fields.

**DERIVED** — computed deterministically from admitted facts:
`game_id`, `team`, `opponent`, `actual_margin`, `game_result`, `split`.

**ASSUMPTION** — **none.** Where a fact was unavailable the field is classified
BLOCKED and omitted. Nothing was filled in to make the corpus look complete.

**BLOCKED** — required by the contract, not supplied here:

| Field | Why |
|---|---|
| `venue` | The feed designates home and away but publishes **no neutral-site indicator**, and none was found on any NCAA endpoint. Emitting `HOME` for every designated home team would assert that no game in four seasons was played at a neutral site. |
| `observed_at` | No per-row zoned observability instant. The payload's `updated_at` carries no timezone; the HTTP `Last-Modified` header is a CDN stamp identical across every season. |
| `pregame_team_rating`, `pregame_opponent_rating`, `expected_margin`, `prior_rating_state`, `model_version`, `configuration_version` | Model outputs. No V3 run produced them for a 2021 game, and reconstructing them from a rating fitted on the same season is the exact leak the contract names. |

`subsequent_outcomes` is classified `DERIVED_AVAILABLE_NOT_EMITTED`: it is
reconstructible from the corpus by `derive_subsequent_outcomes`, which orders
each team's games by `event_time`. It is not emitted because a denormalised copy
of facts already present is a second place for them to be wrong.

### The venue consequence, stated plainly

Because `venue` is blocked, the subject team of every row is the
**NCAA-designated home team**, and `actual_margin` is signed from that
perspective. Any downstream use that ignores this will misattribute home-field
advantage, and neutral-site games — including every conference championship in
the corpus — are indistinguishable from true home games.

### The four fields awaiting a ruling

R5 identified four requested-but-not-governed concepts. Their governed status is
**unchanged**; what follows is availability evidence for whoever makes the
ruling, not a claim on it.

| Field | Availability under this source |
|---|---|
| `games_played_to_date` | **Derivable** walk-forward from the corpus. |
| `game_type` | **Unavailable.** `contestName` and `bracketRound` are blank on every row, and no postseason game is carried, so regular-season and conference-championship games are present and indistinguishable. |
| `overtime_periods` | **Available.** `finalMessage` carries an overtime label — `FINAL (OT)` for one extra period, `FINAL (<n>OT)` beyond it. The vocabulary is open-ended and is read from the bytes rather than assumed: the fbs feed publishes up to `FINAL (7OT)`, and the admitted corpus reaches `FINAL (8OT)` (Georgia 44–42 Georgia Tech, 2024). The deeper feed label sits on a cross-division game excluded on that ground, not on depth. 101 staged games are overtime games, 91 of them in the admitted corpus. This is the field the contract wanted specifically — untagged overtime inflates `game_sd_points` — and could not get from any prior source. It is still not emitted: availability is not admission, and this lane cannot widen the allowlist. |
| `opponent_division` | **Available** by feed intersection. Used as an admission gate; not emitted. |

---

## 8. What the corpus is not

`calibration.register_dataset` **refuses this corpus**, and a test asserts that
it does:

```
Calibration dataset V3_R6_HISTORICAL_OBSERVATION_CORPUS is missing required
observation columns: ['expected_margin', 'observed_at'].
BLOCKED_ON_CALIBRATION_DATA.
```

That refusal is the point, not an oversight. The corpus is an **observation
set**. Turning it into a calibration dataset would require synthesising a model
output and calling it an observation, which is the failure the entire evidence
contract exists to prevent. The strongest evidence status this lane reaches is
therefore `OBSERVATION_CORPUS_BOUND_BYTES_REVERIFIED`, with
`promotion_authorised = false`, `writes_canonical_config = false`, and no
canonical writer created.

`EVIDENCE_BOUND_BYTES_REVERIFIED_AT_BINDING` is **not reached**, because it
requires a registered `CalibrationDataset` and this corpus cannot be one.

Even a perfect corpus would not close the gap. As R5 recorded, the
rating-to-margin transform (`P_TO_STRENGTH_TRANSFORM`) and `REFERENCE_HFA`
remain unratified, so `expected_margin` cannot be constructed in V3 units at
all. Source data was necessary; it was never sufficient.

---

## 9. Exclusions

Every refused row carries an exact reason code, and the counts reconcile:
**4,355 raw = 2,241 admitted + 2,114 excluded.**

That equation is closed over the **fbs feed**, which is its whole universe:
4,355 rows across 91 files. The fbs feed is the right universe because it is the
superset of the in-scope scored-game observations — an FBS-versus-FCS game is
published in *both* feeds, so no in-scope game is reachable only through the fcs
side. The **fcs feed** — 4,164 rows across 83 files — is a *division
classification oracle* and is deliberately **not a term in that equation**: its
rows are not admitted, not excluded, and not counted as raw. An FCS-versus-FCS
game is outside this corpus's governed scope, not a row it dropped.

| Reason | Rows |
|---|---:|
| `SOURCE_SEASON_NOT_FINALISED` | 878 |
| `UNRESOLVED_TEAM_IDENTITY` | 934 |
| `INSUFFICIENT_TEAM_SEASON_COVERAGE` | 227 |
| `FBS_VS_FCS_OPPONENT_DIVISION_NOT_GOVERNED` | 43 |
| `MISSING_SOURCE_GAME_IDENTIFIER` | 21 |
| `DUPLICATE_OR_AMBIGUOUS_GAME_ID` | 8 |
| `GAME_NOT_FINAL` | 2 |
| `OUTSIDE_GOVERNED_SCOPE_FCS_VS_FCS` | 1 |

**`SOURCE_SEASON_NOT_FINALISED` is a finding, not housekeeping** — and the
finding has two halves that must not be run together.

*Source content fact.* Season 2025 was retrieved in full — 878 fbs-feed games —
in files the source last updated part-way through that season. The census,
counted from the bytes and published as `seasons_refused_source_content_fact`,
is **852 `pre`, 22 `final`, 4 `live`**. It is a mid-season snapshot, not an
empty one, and this document previously said otherwise.

*Evidence admission decision.* That mix is the reason for the refusal, not an
obstacle to it. Admission is by whole finalised season. A season whose own bytes
show it still in progress cannot supply a season-complete observation set, and
admitting only the 22 rows that happen to read `final` would make the corpus a
function of *when the snapshot was taken* — a different capture minute would
give a different corpus. All 878 rows are therefore refused under
`SOURCE_SEASON_NOT_FINALISED`, the `final` and `live` rows included. The bytes
are retained as the evidence for both halves.

**`INSUFFICIENT_TEAM_SEASON_COVERAGE`** is the contract's own per-team floor
being enforced rather than merely reported. A team-season holding fewer than 8
admitted observations cannot inform `recent_form_weights`, which is a decay over
prior weeks. Dropping one team-season lowers its opponents' counts, so the prune
iterates to a fixed point — 5 iterations, 227 rows. Selection is on schedule
structure alone and never on a result, so it cannot bias the corpus toward
outcomes; it does bias composition toward teams whose opponents are in the
canonical master, and the report names every team-season that left.

---

## 10. FBS versus FCS

**43 real FBS-versus-FCS observations** are identified across the four seasons —
the first such sample this project has held. The FCS participants are Cal Poly,
Colgate, Delaware, Duquesne, Holy Cross, Idaho, North Dakota State, Sacramento
State, Southern Utah and Yale.

They are **excluded from the corpus** and inventoried in full. The data contract
asks for `opponent_division` precisely so that FCS games can be "identifiable so
they can be excluded rather than silently fitted on an unresolved scale", and
that scale — `model_scale.FCS_ELO_1250_TO_V3_POINT_SCALE_ADAPTER` — is still an
open blocker.

No mapping is derived. No algebraic conversion is attempted. FCS Elo remains
1250 and the unified-point mapping remains `None`. The inventory exists so that
a later, dedicated FCS-scale lane inherits a reconciled sample instead of
starting from nothing.

The sample is small — roughly 11 games per season. That is a property of the
canonical master, not of the source: 2021–2024 saw hundreds of FBS-vs-FCS games,
but only those whose FCS participant appears in the 134-entity canonical
universe can be reconciled at all.

---

## 11. Splits

Whole seasons, assigned temporally. Season granularity is chosen over any finer
cut because it is the only boundary that needs no argument — the gap between the
last game of one season and the first of the next is months wide.

| Split | Seasons | Observations | Range |
|---|---|---:|---|
| training | 2021, 2022 | 1,080 | 2021-08-28T17:00Z → 2022-12-04T01:00Z |
| validation | 2023 | 598 | 2023-08-26T18:30Z → 2023-12-09T20:00Z |
| holdout | 2024 | 563 | 2024-08-24T16:00Z → 2024-12-08T01:00Z |

Split digest: `d0b84cc3da244ffbb5566bbf5c86fd07aed081ae48b01de293b79863503e3f5b`

Ordering is proved by `calibration.require_temporal_split_integrity` — the same
gate a calibration dataset would face — rather than by a local re-implementation.

All four minimum-volume floors pass:

| Floor | Required | Actual |
|---|---:|---:|
| distinct seasons | 3 | 4 |
| total observations | 1,500 | 2,241 |
| holdout observations | 300 | 563 |
| games per team per season | 8 | 8 |

---

## 12. Artifacts

Under `reference/dynamic_weekly_mc_v3/observation_corpus_r6/`:

| File | Contents |
|---|---|
| `raw/ncaa_scoreboard/**` | 174 immutable gzip-wrapped raw captures |
| `V3_R6_SOURCE_ACQUISITION_MANIFEST.json` | every URL retrieved, with digests, HTTP metadata and retrieval times |
| `V3_R6_SOURCE_CUSTODY_MANIFEST.json` | per-file custody bindings and the re-verification result |
| `V3_R6_TEAM_IDENTITY_RECONCILIATION.json` | resolution rules, rule counts, every unresolved name |
| `V3_R6_GAME_IDENTITY_REPORT.json` | scheme, uniqueness, all 12 repeat matchups |
| `V3_R6_CHRONOLOGY_REPORT.json` | ordering scheme, precision, walk-forward rule |
| `V3_R6_EXCLUSION_REPORT.json` | all 2,114 refused rows with reason codes, plus the FBS-vs-FCS inventory |
| `V3_R6_OBSERVATION_CORPUS.csv` | the corpus, 2,241 rows, 11 governed columns |
| `V3_R6_TEMPORAL_SPLIT_MANIFEST.json` | split boundaries, digest, volume assessment |
| `V3_R6_CORPUS_REGISTRATION_RECEIPT.json` | byte-reverified registration, field classification |
| `V3_R6_EVIDENCE_BINDING_RECEIPT.json` | bindings, and the recorded calibration refusal |
| `V3_R6_OBSERVATION_CORPUS_DISCOVERY_R6.json` | the R6 status record |

R5's artifacts are untouched. These are successors, not replacements.

Regeneration is byte-deterministic: `python scripts/build_observation_corpus_r6.py`
reproduces all eleven derived artifacts identically from the raw captures, and a
test asserts the committed corpus matches a fresh build byte for byte.

Corpus SHA-256: `31504e8d03b68de549bb999f2ce6a62824eb3286e3802712534d3092fa3f7aac`

---

## 13. State

| | |
|---|---|
| Formal blockers | 8 before, 8 after, exact set unchanged |
| Parameters promoted | none |
| FCS mapping promoted | no; Elo 1250, mapping `None` |
| Calibration values | six, all `null` |
| Governed allowlist | not widened |
| Canonical config written | no |
| Canonical writer created | no |
| Experiments run | 0 |
| Season Monte Carlo | not run |
| Board custody | `BOARD_IK_APPROVED_ARTIFACT_VERIFIED`, unchanged |
| V2.1 static control SHA | unchanged |

---

## 14. To unblock the next lane

1. **Rule on `venue`.** Either admit a neutral-site source, or rule that a
   home-designated margin is admissible with the bias documented. Until then
   home-field advantage cannot be separated from the residual it contaminates.
2. **Ratify the rating-to-margin transform** (`P_TO_STRENGTH_TRANSFORM`) and
   `REFERENCE_HFA`. Without them `expected_margin` cannot exist in V3 units, and
   no corpus fixes that.
3. **Produce pregame V3 ratings for the admitted games**, walk-forward from this
   corpus and nothing else. That is the layer between an observation set and a
   calibration dataset, and it is a modelling lane, not an evidence lane.
4. **Rule on the four fields**, with the availability evidence in §7 in front of
   the decision — `overtime_periods` in particular is now demonstrably obtainable.
5. **Open a dedicated FCS-scale lane** against the 43-game inventory, knowing
   that 43 observations is a small sample and may itself prove insufficient.
