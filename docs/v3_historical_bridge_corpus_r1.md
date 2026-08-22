# OPERATION SYTHALAX — Historical Results Bridge, 2020 and 2025 (R1)

Branch: `claude/v3-historical-bridge-corpus-r1`
Frozen base: `5479f2ae7687c36c0ed4117334171289693dd5c9`
Disposition: **BOTH SEASONS ACQUIRED — 2020 CORROBORATED, 2025 SINGLE-SOURCE, NO ADMISSIBLE 2025 OPENING STATE**

Machine-readable artifacts: `reference/dynamic_weekly_mc_v3/historical_bridge_r1/`.

No rating was generated. No parameter was promoted, no blocker retired, no
allowlist widened, no canonical writer built, no FCS adapter installed, no point
scale fitted, no weekly calibration performed, no game SD computed and no Monte
Carlo run. The 2021–2024 R6 corpus is untouched; this lane did not read from it,
write to it, or depend on it.

---

## 1. The short version

| Question | Answer |
|---|---|
| Real 2020 results? | **568 scored games**, every one of them cross-checked against the NCAA's own feed where the NCAA publishes it |
| Real 2025 results? | **934 scored games**, complete for all 136 FBS members, from a tier-2 source only |
| Is the repository's existing 2025 feed usable? | **No**, and the reason is now established from bytes rather than asserted |
| Can 2025 give Stage 0 a scale-identification season? | **No.** 0 of 179 real Week 1/2 games have a valid opening state on both sides |
| Can a 2020 terminal state be computed? | **Yes, arithmetically** — and only as a witness. The governed V3 path cannot run at all |
| How many FBS members did 2024 have? | **134.** Settled on evidence; no ruling required |

Two of those deserve their own sentence.

**The 2025 opening-state question has a cleaner answer than "not yet".** The only
2025 preseason measurement that exists anywhere in this programme is the
TrueSkill Week 1 prior, and it carries **one distinct value** — 25.0 — for all
108 teams in it. It is also computed over a game universe that shares **zero**
games with the real 2025 season, out of 757. So the answer is not that the
opening state is thin. It is that there is no opening state, twice over.

**The 2024 population disagreement is not a disagreement about football.** The
conference-distribution workbook that reports 133 is *exactly right* for 2021,
2022 and 2023 — 130, 131, 133, matching the season structure team for team — and
then diverges from 2024 by precisely one program, Kennesaw State, which really
did join FBS that year. By 2025 the same workbook reports 143 FBS members
including Harvard, Yale and Princeton. It is a synthetic universe that tracked
reality closely and then stopped.

---

## 2. Sources, and why there are two

| Authority | Tier | Serves | Used for |
|---|---|---|---|
| `NCAA_OFFICIAL_SCOREBOARD_FEED` (`data.ncaa.com/casablanca`) | 1 | 2020 | the 2020 corroboration, and the 2025 refusal |
| `ESPN_PUBLIC_SCOREBOARD_API` (`site.web.api.espn.com`) | 2 | 2020 and 2025 | the corpus rows for both seasons |
| `ESPN_SEASON_STRUCTURE_API` (`sports.core.api.espn.com`) | 2 | 2020–2025 | subdivision membership, per season |

688 responses were retrieved and stored, 27,481,968 raw bytes, each gzip-wrapped
with `mtime=0` and bound by two digests: `stored_sha256` over the container git
holds and `raw_sha256` over the response body inside it. `raw_sha256` is what
custody is asserted over. The build re-reads and re-hashes every one before
parsing anything, and raises on a mismatch rather than reporting it.

### The tier-1 feed does not serve 2025

This is the finding the whole 2025 half of the lane rests on, so it is
established rather than claimed. Retrieved live, the NCAA's 2025 FBS scoreboard
returns **878 games: 852 `pre`, 22 `final`, 4 `live`** — reproducing the figures
the mission carries, from the bytes now committed here. Every one of those files
reports its own `updated_at` inside **2025-08-29**, the Saturday the season
opened.

The status field is not what refuses it. HTTP 200, well-formed objects, real
team names and real dates: nothing about the response says *stale*. What says
stale is that the file publishing a November game was last written in August.
`ncaa_season_staleness_report` measures exactly that — rows whose feed update
predates their own kickoff — and finds **1,669 of 1,731** for 2025 against
**0 of 677** for 2020.

Two other NCAA paths were tried and are recorded as unavailable in this
environment rather than absent in general: the date-addressed scoreboard
(`/{yyyy}/{mm}/{dd}/scoreboard.json`) and the per-game endpoints
(`/game/{id}/gameInfo.json`) both answer 404.

`api.collegefootballdata.com` returns 401 without a registered key, and
`www.sports-reference.com` returns 403. Neither was used.

### So 2020 is retrieved twice

An aggregator used where no check is possible is an assumption. An aggregator
**measured** against the NCAA's own feed on 553 games and then used on the season
the NCAA does not serve is an argument. Making that argument is the only reason
2020 was retrieved from both authorities, and it is what licenses the 2025
corpus.

The measurement:

| | |
|---|---:|
| Tier-1 final rows published | 578 |
| Matched into the tier-2 corpus | 553 |
| **Score disagreements** | **0** |
| Score agreement rate | **1.000** |
| Tier-1 rows missing from tier 2 | **0** |
| Tier-1 rows out of tier-2 scope (FCS vs FCS) | 14 |
| Tier-1 rows whose participant could not be name-bridged | 11 |

The 11 unbridged rows involve six programs — Angelo St., Missouri Western,
Pittsburg St., West Tex. A&M, Western Caro., Western Colo. — all Division II or
FCS, none of which played an FBS opponent, so none of which appears in an
FBS-group retrieval at all. They are listed in the artifact rather than absorbed.

Division was checked the same way. The NCAA feed states division implicitly,
through the intersection of its `fbs` and `fcs` scoreboards; the subdivision
declaration states it explicitly. On 2020 the two agree on **141 of 141** teams,
with **zero** disagreements. That is what makes the declaration an acceptable
substitute for 2025, where the intersection method is unavailable.

---

## 3. What is in the corpus

Two CSVs, 32 columns, one row per real scored game.

| | 2020 | 2025 |
|---|---:|---:|
| Retrieved event rows | 630 | 958 |
| **Admitted** | **568** | **934** |
| Excluded | 62 | 24 |
| Regular season | 542 | 888 |
| Postseason | 26 | 46 |
| FBS vs FBS | 534 | 808 |
| Cross-division (FBS vs non-FBS) | 34 | 126 |
| Neutral site | 38 | 55 |
| Overtime | 21 | 45 |
| Corroborated by tier 1 | 521 | 0 |

Every retrieved row is admitted or refused with exactly one reason code, and the
counts reconcile: 630 = 568 + 62, and 958 = 934 + 24. 2020's exclusions are 56
games that were never played (postponed or cancelled — it was 2020) and 6 with
no FBS participant, one of which is the Senior Bowl. 2025's 24 exclusions are all
`NO_FBS_PARTICIPANT`.

The mission's field list, and where each stands:

| Asked for | Status |
|---|---|
| real scored games | **FACT** — `home_points`, `away_points`, `home_margin` |
| team identities | **FACT** — source id, display name and school name for both sides |
| dates / order | **FACT** — `kickoff_utc` and `kickoff_epoch`, a published instant |
| historical FBS/FCS division | **FACT** — from the season's own subdivision declaration, both sides |
| home/away designation | **FACT** — the source's designation, which is not the same as venue |
| neutral venue | **FACT** — `neutral_site`, plus venue name, city and state |
| competition type | **FACT** — season type, and for a postseason game the bowl or round name |
| source provenance | **FACT** — authority, tier, exact URL |
| raw SHA-256 | **FACT** — per row, the digest of the capture it came from |
| row reconciliation | **FACT** — `V3_BRIDGE_ROW_RECONCILIATION.json` |
| ratings | **not generated**, by instruction and by test |

`neutral_site` is worth one note, because R6 recorded it as blocked and this lane
records it as a fact from a different source. The 2025 national championship —
Indiana 27, Miami 21, at Hard Rock Stadium — is published `neutralSite: false`,
because Hard Rock Stadium is Miami's home venue. That is a defensible call and it
is the source's call, not this lane's; it is flagged here so a consumer meets it
in the documentation rather than in the data.

### Three deliberate departures from R6

**Identity is source-native first.** R6 resolved every participant through the
2026 canonical master and excluded the row when that failed, at a cost of 934
rows over four seasons — mostly real programs a *synthetic* 2026 universe does
not carry. That is the right trade for a corpus headed into a governed fit. It is
the wrong trade for an evidence record about what really happened: a real game is
not less real because a synthetic master omits a participant. Here the key is the
source's own identifier, canonical binding is reported as an additional column,
and failing to bind costs the row nothing.

The binding rates are reported so a canonical-only consumer knows its own reach:
115 of 141 participants and 465 of 568 games for 2020; 125 of 230 and 644 of 934
for 2025.

**Division is a declaration, not an inference** — see §2.

**Cross-division games are admitted and flagged, not dropped.** The FCS point
scale is an open blocker and no fit may run over those rows. That is a consumer's
obligation, and `cross_division` is the column that discharges it. Deleting real
observations to enforce a downstream rule would make the record disagree with the
season it describes. A consumer wanting R6's shape takes
`cross_division == False`: 534 games for 2020 and 808 for 2025.

### One defect found late, and the guard that now exists

The first acquisition pass ran at `limit=900`. ESPN honours `limit` up to
somewhere below 1000 and then **silently** returns its default 25-event page,
HTTP 200, no pagination cursor. On 2025-08-30 the same URL answers 62 events at
`limit=400` and 25 at `limit=1000`. The first 2025 corpus was 544 games and
looked entirely ordinary.

What caught it was the per-team coverage report, not the total — nobody knows
what a season total *should* be, but everybody knows a team plays twelve games.
All captures were discarded and re-retrieved at a measured page size.
`espn_url` now refuses a limit above the tested ceiling, with the measurement in
the comment, and `test_the_2025_season_is_complete_for_every_declared_fbs_member`
pins the property: 136 of 136 FBS members present, minimum 12 games, median 13.

The 2020 coverage report reads differently and correctly so: 127 of 130 members
played, 42 of them fewer than eight games, and three played none at all —
Connecticut, New Mexico State and Old Dominion, each of which cancelled its 2020
season. Members with no game are carried in the report rather than dropped,
because "this member played nothing" and "this retrieval lost a page" must not
look the same.

---

## 4. The 2025 opening-state join test

**Result: 0 of 179 real Week 1/2 games have a valid opening state on both sides.**

Three things have to be true, and they are tested separately because collapsing
them yields a number that looks like an answer:

1. the source must be **preseason** — a measurement taken before the team played;
2. the opening state must have **dispersion** — a population where every team
   carries the same value has no deviation to divide by, so a Z score over it is
   undefined, not zero;
3. the component universe must **join** the real game universe.

| Family | Located 2025 source | Verdict |
|---|---|---|
| TrueSkill | Week 1 prior in the 2025/2026 consolidation workbook | **Preseason — and degenerate.** 108 teams, **1** distinct value (25.0), SD 0.0 |
| Litkenhous | 2025 season-**final** ratings | Not preseason. Final is same-season information |
| Pure Baxter | `Baxter_Ratings_2025.csv` | Not preseason. Carries a `games` column — a count obtainable only afterwards |
| Board family | none | 147 board artifacts found across the staged locations; **0** carry a 2025 label |

And the universe test, which is decisive on its own:

> The TrueSkill 2025 chain runs over `2025_Synthetic_Season_Games.csv`, whose
> declared SHA-256 in the workbook's own README matches the file on disk. Of its
> **757** games, **0** appear in the real 2025 season — 0 matching on team pair
> and date, and 0 matching on team pair alone.

Its first game is Air Force 42, Wyoming 20 on 2025-08-30; its second is Alabama
48, Auburn 8 in Week 1. The Iron Bowl is played in late November.

63 of the 179 real Week 1/2 games have both participants *named* somewhere in the
component table. That number is reported next to the zero on purpose: name
coverage and a usable opening state are different facts, and a reader who sees
only the zero cannot tell which one failed.

`safe_for_2025_stage0: false`. Not because the join was not attempted, but
because it was, and the components are not there.

---

## 5. 2020 backcast support

**Result: a 2020 terminal state is computable, as a witness only.**

`srs.compute_srs` needs `game_id`, two participants and a margin. The corpus
carries all four as facts. **No historical metadata is required and absent** —
the field the mission asked about is empty, and that is the answer to the
question it asked.

Run over the 534 same-division 2020 games, the system solves. Its values were
computed inside the feasibility probe and **discarded there**; nothing is emitted,
returned or written, and a test asserts `srs_values_emitted == False`.

Three findings came out of running it:

**The 2020 schedule graph connects only through the postseason.** Over the
regular season alone it splits into four components — 87 teams, then the Big Ten
(14), the SEC (14) and the MAC (12), each of which played a conference-only
schedule. The 87-team component holds together through a single edge: San Diego
State at Colorado, 2020-11-28, the only Pac-12 game against a non-Pac-12 opponent
all regular season. Add the 26 postseason games and the graph is one component of
127. Since the tier-1 NCAA feed publishes **no** 2020 postseason game — weeks 16
through 19 are empty — tier 1 alone could not have produced a connected 2020
system. The dual-source acquisition is what made this answerable.

**SRS computes and does not authorise.** `CANONICAL_SRS_SPEC_MOUNTED` is `False`
and `require_canonical_validated_srs()` fails closed: no canonical specification,
reference implementation or historical anchor is mounted. Under ruling
R2-SRS-WITNESS this is a calibration/validation witness, not the V3 rating.

**The governed V3 path cannot run on any amount of 2020 results.** Three
independent obstacles, none of which is a data problem:
`rerating.BlockedGovernedRerater` raises `GovernanceBlock` unconditionally; the
`TeamPathState` it consumes needs `preseason_strength_points`, which is exactly
the 2020 opening state no located source supplies; and its residual term needs
`expected_margin` in V3 point units, which needs the still-unratified
`P_TO_STRENGTH_TRANSFORM` and `REFERENCE_HFA`.

No same-season preseason state was derived from 2020 final, and a test asserts
`same_season_preseason_derivation_attempted == False`. The purpose of this
section is a possible 2021 prior and nothing else.

### A defect this probe caught in itself

The first version supplied each game to SRS once, from the home side.
`srs._build_system` credits margins and opponent counts to `team` only, so a
one-sided feed leaves every away appearance uncounted. It presented as
`SRS schedule-adjustment system is singular` on a graph the same module reported
as connected — a contradiction that was the only reason it was investigated
rather than written up. A one-sided feed does not always fail; on a small cycle it
returns a plausible ordering computed over half the appearances. The module's own
tests supply both sides; this probe now does too, and
`test_the_srs_feed_is_two_sided` pins it.

---

## 6. Historical membership, 2020–2025

Derived per season as the union of the member teams of every conference declared
a child of the subdivision group for **that season**. The flat `groups/80/teams`
listing is never used: it is not a season membership and returns a superset — 144
entries for 2024 where the roll-up returns 134.

| Season | FBS | FCS |
|---|---:|---:|
| 2020 | **130** | 127 |
| 2021 | **130** | 128 |
| 2022 | **131** | 130 |
| 2023 | **133** | 128 |
| 2024 | **134** | 129 |
| 2025 | **136** | 129 |

Membership is retrieved as a *declaration*, separately from results, because a
result feed can only show which teams played. In 2020 those are demonstrably
different sets, and deriving membership from participation would have deleted
Connecticut, New Mexico State and Old Dominion and reported the deletion as a
population of 127.

### The 2024 population question, resolved

**134. No Chairman ruling is required, because the evidence settles it.**

Three claims were located, each read once with its digest recorded:

| Claim | Says | Class |
|---|---:|---|
| Season structure roll-up (this lane) | **134** | real 2024 conference rosters |
| `Synthetic_NCAA_Conference_Distribution_2021_2026` | 133 | synthetic |
| `Phase5J team_registry_2024` | 118 | research registry, `REGISTRY_ONLY` |
| `2026_TEAM_CANONICAL_MASTER_v2` | 121 | synthetic **2026**, not a 2024 statement at all |

Compared name by name — after a small, documented alias table used *only* for
comparing claims and provably unable to touch a corpus row — the conference
distribution workbook is not vaguely close to reality. It is exact:

| Season | Workbook | Derived | Difference |
|---|---:|---:|---|
| 2021 | 130 | 130 | none |
| 2022 | 131 | 131 | none |
| 2023 | 133 | 133 | none |
| 2024 | 133 | 134 | **missing Kennesaw State** |
| 2025 | 143 | 136 | missing Kennesaw State; adds Colgate, Cornell, Harvard, Holy Cross, Lehigh, Penn, Princeton, Yale |

That is a much more useful finding than "two sources disagree". The workbook is a
faithful record of real FBS membership through 2023, drifts by exactly one
program in 2024, and by 2025 has been overwritten by the synthetic universe. Any
lane that has used it for 2021–2023 was using correct numbers; any lane using it
for 2024 or later was not.

The Phase5J registry's 118 is a different kind of number again: it carries
Colgate, Cornell, Harvard, Holy Cross, Lehigh, Penn, Princeton and Yale as FBS
and omits 24 real 2024 FBS members including Akron, Ball State, Bowling Green and
Charlotte. It is a registry of the teams that research package chose to rate.

**On the figure 128.** The mission describes the discrepancy as 133-vs-128. No
artifact carrying a 2024 FBS population of 128 was located anywhere in this
repository or in the staged locations searched. The located candidates are 133,
121 and 118. Two nearby 128s do exist and neither is a 2024 FBS count: the FCS
membership of 2021 and of 2023 is 128 in the table above, and
`V3_GOVERNANCE_STATUS_R2.json` records `r1_audited_full_suite: 128`, a test
count. This is reported as unlocated rather than reconciled to a guess.

---

## 7. Artifacts

Under `reference/dynamic_weekly_mc_v3/historical_bridge_r1/`:

| File | Contents |
|---|---|
| `raw/ncaa_scoreboard/**` | 62 immutable NCAA captures, 2020 and 2025, both division feeds |
| `raw/espn_scoreboard/**` | 312 immutable per-date captures across both season windows |
| `raw/espn_membership/**` | 314 immutable subdivision, conference and team captures, 2020–2025 |
| `V3_BRIDGE_SOURCE_ACQUISITION_MANIFEST.json` | every results URL retrieved, with digests, status and retrieval time |
| `V3_BRIDGE_MEMBERSHIP_ACQUISITION_MANIFEST.json` | the same for membership, including which phases are derived rather than static |
| `V3_BRIDGE_SOURCE_CUSTODY_MANIFEST.json` | 688 captures re-read and re-hashed at build time |
| `V3_BRIDGE_2020_RESULTS.csv` | 568 rows, 32 columns |
| `V3_BRIDGE_2025_RESULTS.csv` | 934 rows, 32 columns |
| `V3_BRIDGE_ROW_RECONCILIATION.json` | raw → admitted + excluded, per season, every exclusion with a reason |
| `V3_BRIDGE_CROSS_SOURCE_AGREEMENT_2020.json` | the score and division checks against tier 1 |
| `V3_BRIDGE_TIER_1_FEED_ASSESSMENT.json` | the 2025 staleness finding, and 2020's clean result |
| `V3_BRIDGE_SEASON_COVERAGE.json` | games per declared FBS member, per season |
| `V3_BRIDGE_HISTORICAL_MEMBERSHIP.json` | 2020–2025 membership, candidate comparisons, the 2024 resolution |
| `V3_BRIDGE_TEAM_IDENTITY.json` | canonical binding rates and every unbound name |
| `V3_BRIDGE_2025_OPENING_STATE_JOIN_TEST.json` | the join test, per family, with its refusal reasons |
| `V3_BRIDGE_2020_BACKCAST_FEASIBILITY.json` | solvability, connectivity, and what the governed path still lacks |
| `V3_BRIDGE_STATUS_R1.json` | the lane status record |
| `mounted/V3_BRIDGE_2025_OPENING_COMPONENT_EXTRACT.json` | provenance-bound evidence about the component sources — **not** a rating source |
| `mounted/V3_BRIDGE_POPULATION_CANDIDATE_EXTRACT.json` | the located population claims, each with its digest |

The two `mounted/` extracts exist so the build depends only on committed bytes.
The staged workbooks they describe are read once, by
`scripts/extract_opening_components_2025.py` and
`scripts/extract_population_candidates.py`, with the upstream digest recorded.
Committing the workbooks themselves would mount a synthetic rating universe into
a governed repository; reading them at build time would make the build depend on
a filesystem a reviewer may not have.

Regeneration is byte-deterministic: `python scripts/build_historical_bridge_r1.py`
reproduces all eleven derived artifacts identically from the committed captures,
and a test asserts it. No artifact carries a generation timestamp — that would
defeat the byte-identity requirement on the second run — and a test asserts that
too.

Corpus digests:

- `V3_BRIDGE_2020_RESULTS.csv` — `f71e0bdb53d1cbd34dfd1a4027b4193f909b20890992bd73df84df76505bc717`
- `V3_BRIDGE_2025_RESULTS.csv` — `08e0c9d9df163a3d1402961b814a96266cb00d273eec17c0e2f2affad9b9434b`

---

## 8. What this corpus is not

It is not a calibration dataset, and it cannot be made into one here for the same
reason R6's could not: `expected_margin` and the pregame rating fields are model
outputs, and manufacturing them would be synthesising a model output and calling
it an observation.

It is not tier-1 evidence for 2025. Every 2025 row says so in its own
`tier_1_corroboration` column, so no consumer can read one as corroborated by
forgetting to check. The 2020 corroboration measured the aggregator at 553 games
with zero disagreements; that is a strong prior about the source, and it is not a
substitute for a check that cannot be run.

It does not resolve the FCS scale. 34 cross-division games in 2020 and 126 in
2025 are identified and flagged so they can be excluded rather than silently
fitted. `model_scale.FCS_ELO_1250_TO_V3_POINT_SCALE_ADAPTER` is untouched and FCS
Elo remains 1250.

It does not supply a 2020 or 2025 opening state, and §4 is the evidence that none
exists to supply.

---

## 9. State

| | |
|---|---|
| Tests | **640 full**, **581 V3** — up from 602 / 543 at the frozen base, +38 new, no existing test modified |
| Ratings emitted | none |
| Parameters promoted | none |
| Blockers | 8 before, 8 after |
| Calibration values | six, all `null` |
| Governed allowlist | not widened |
| Canonical config written | no |
| `config.py` | untouched |
| `V3_CALIBRATION_DATA_CONTRACT.json` | untouched |
| R6 corpus | untouched, and not read |
| Season Monte Carlo | not run |

Files added outside `reference/`: one engine module
(`historical_bridge.py`), four scripts, one test file, one documentation file,
and eleven lines of `.gitattributes` pinning `*.gz` as binary so a checkout
filter cannot rewrite a raw capture out from under its digest.

---

## 10. To unblock the next lane

1. **2021 opening state is now one modelling decision away, not one data
   acquisition away.** 2020 results exist, are corroborated, and yield a
   connected schedule graph. What does not exist is a ratified way to turn a
   terminal state into an opening state — and SRS is a witness, so it cannot be
   that way without a canonical specification and anchors being mounted.
2. **Stage 0 needs a preseason source, not a season.** 2025 is now the best real
   game universe this programme holds: 934 games, complete, with kickoff
   instants, neutral flags and bowl identities. It is Stage-0 ready on every axis
   except the one that matters, and §4 says exactly which measurements would fix
   it — a 2025 preseason value, with dispersion, for each of the four families,
   computed over the real season.
3. **Rule on nothing about 2024 membership.** It is 134. If a lane needs the
   synthetic universe's 2024 population instead, that is a different question and
   should be asked in those words.
4. **Decide whether the 2021–2024 R6 corpus should be re-derived on this lane's
   terms.** R6's 2,241 rows exclude cross-division games, carry no neutral-site
   flag, no venue, no bowl and no overtime tag, and lose participants the
   synthetic master omits. The same acquisition run over 2021–2024 would supply
   all of those. That is a re-derivation and needs a decision, not a merge.
