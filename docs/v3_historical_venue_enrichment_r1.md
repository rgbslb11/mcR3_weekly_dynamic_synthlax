# V3 Historical Venue / Competition Enrichment R1

**Lane** `claude/v3-historical-venue-enrichment-r1`
**Status** EXPERIMENTAL / NOT CANONICAL / NO PARAMETER PROMOTED / NO BLOCKER RETIRED

## What this lane is for

Historical Observation Corpus R6 admits 2,241 real 2021–2024 observations and
records venue as `BLOCKED`. That is a property of the source, not a gap in the
corpus: the NCAA scoreboard feed designates a home and an away participant and
carries no venue field at all — not blank, absent, in every row of every week of
every season retrieved.

The consequence is specific. A designated home team is not evidence of home
field, so the governed V3 football-point HFA of **3.5** (`SCHED-HFA-BASE`, ruling
`R2-HFA-3P5`) cannot be attached to one. Conference championship games, kickoff
classics and any other neutral-site game would silently receive an advantage
nobody had.

This lane produces an **enrichment layer** that answers that question per game
where evidence permits, and says `VENUE_UNRESOLVED` where it does not. It does
not rewrite the corpus, does not re-decide which games belong in calibration,
computes no expected margin, fits no parameter, and runs no simulation.

## Result

| | Enrichment universe | Joined to corpus R6 |
|---|---|---|
| Games | 3,454 | 2,241 |
| Venue resolved | 3,416 | **2,241** |
| Venue unresolved | 38 | 0 |
| Neutral site | 82 | 67 |
| Home field | 3,334 | 2,174 |
| Game type resolved | 3,416 | 2,241 |
| Conference championships | 39 | 30 |
| `EXPECTED_MARGIN_VENUE_READY` | 3,416 | **2,241** |

**Every one of the 2,241 admitted corpus observations now has a defensible
venue classification.** 67 of them are neutral-site games that would otherwise
have been treated as home games for the designated home team, and 2,174 are
confirmed true-home games rather than assumed ones.

The 43 FBS-versus-FCS games R6 identified and excluded are also all resolved:
43 FBS-hosted, 0 FCS-hosted, 0 neutral, 0 ambiguous. No FCS point scale is
estimated here.

## Sources, and why the second one

| Authority | Tier | Role | Carries venue |
|---|---|---|---|
| `NCAA_OFFICIAL_SCOREBOARD_FEED` | `TIER_1_NCAA_OFFICIAL` | Game identity, designated orientation, scheduled kickoff | No |
| `ESPN_COLLEGE_FOOTBALL_SCOREBOARD` | `TIER_5_REPRODUCIBLE_SECONDARY` | `neutralSite`, venue, contest name, kickoff | Yes |

The hierarchy permits a reproducible secondary source only when the sources
above it do not provide the needed fact. For venue specifically they do not, and
that was established by probe before ESPN was used:

| NCAA-side option | Result |
|---|---|
| `data.ncaa.com/casablanca/.../scoreboard.json` | 200 — no venue field in any row |
| `data.ncaa.com/casablanca/game/<id>/gameInfo.json` | 404 for both identifier namespaces the scoreboard exposes |
| `www.ncaa.com/game/<id>` | 200 — venue element present but empty; filled client-side |
| `sdataprod.ncaa.com` (the gateway that fills it) | 403 Access Denied at the Akamai edge |
| `stats.ncaa.org` | 403 |

The tier is carried on every row that uses ESPN and is never promoted. Where the
two sources can be compared, they are: orientation and kickoff are cross-checked
on all 3,416 matched games.

## Matching

The two feeds share no identifier, so matching runs on facts in strength order
and refuses rather than guesses whenever more than one candidate survives.

| Pass | Basis | Bound |
|---|---|---|
| `IDENTITY_DATE` | Both teams resolved to ESPN ids, unique on date ±1 day. Does **not** consult score. | 3,406 |
| `PARTIAL_IDENTITY_SCORE` | One team resolved, plus date and score pair | 10 |
| `DATE_SCORE` | Date and score pair unique on both sides | 0 (bootstrap only) |

The team-identity map is **not hand-authored**. It is harvested from unambiguous
date-and-score matches by aligning the two feeds' scores within a game, then the
passes re-run to a fixpoint. 240 teams resolved; `missouri-st` and `ut-martin`
were observed against two ESPN ids each and were **dropped rather than decided by
majority**.

Every ESPN event binds to at most one NCAA game, which is what turns a duplicated
source row into a visible refusal instead of a silent double count.

### The 38 unresolved

| Status | Count | What they are |
|---|---|---|
| `UNMATCHED` | 24 | FCS-vs-FCS games the NCAA *FBS* scoreboard carries for teams in transition (Delaware and Missouri State in 2024, James Madison in 2021, Kennesaw State, Sam Houston). ESPN's FBS grouping does not carry them. None is a corpus row. |
| `AMBIGUOUS_SOURCE_IDENTITY` | 14 | 7 games the NCAA feed publishes twice under different `gameID`s — twice with disagreeing scores. Both rows refused. R6 excluded all of them too. |

Neither category costs the corpus anything: all 2,241 corpus rows resolved.

## Neutral-site findings

39 conference championship games were found across four seasons. **They are not
all neutral, and assuming they were would have been wrong 16 times.**

| Neutral (23) | Hosted on a participant's field (16) |
|---|---|
| SEC (Mercedes-Benz), Big Ten (Lucas Oil), ACC (Bank of America), Big 12 (AT&T), MAC (Ford Field), Pac-12 (Allegiant) | American Athletic (Nippert, Yulman, Michie), C-USA (Alamodome, Williams, AmFirst), Mountain West (Dignity Health, Albertsons, Allegiant), Sun Belt (Our Lady of Lourdes, Veterans Memorial) |

The Allegiant Stadium pair is the sharpest case. The 2021 Pac-12 championship
there is neutral; the 2023 Mountain West championship in the same building is
**not**, because UNLV plays its home games in it. A venue-name rule would have
got that backwards. The source states the flag per game and the flag is what is
recorded.

## Conflicts

288 games carry a source conflict. **On every one of them both evidence records
are preserved and neither source is selected.**

| Conflict | Count | Blocks venue? |
|---|---|---|
| `SOURCE_CONFLICT_KICKOFF` | 275 | No |
| `SOURCE_CONFLICT_SCORE` | 9 | No |
| Both | 4 | No |
| `SOURCE_CONFLICT_ORIENTATION` | **0** | Would |

Kickoff conflicts are concentrated in 2021 (214 of 288) and dominated by a
one-hour displacement (192 games), which makes them a property of that season's
NCAA feed rather than noise. Where the two disagree, `kickoff_utc` is left empty
and both `kickoff_utc_ncaa` and `kickoff_utc_espn` carry their source's value.

The zero is the notable number: a tier-1 and a tier-5 source **never disagree
about which team hosted**, across 3,416 matched games. That is independent
corroboration of the orientation the corpus already relies on, and it is also the
check that would expose a mis-binding matcher long before a wrong venue did.

## Timestamps not produced

`completion_utc` and `observability_utc` are **empty on every row**, and both
counts are zero. Neither source carries a completion or observability instant.
Deriving one from kickoff would fabricate exactly the fact this lane exists to
stop fabricating. 12 rows have a known date but no known kickoff time and record
the date alone.

## Artifacts

All under `reference/dynamic_weekly_mc_v3/venue_enrichment_r1/`.

| Artifact | Contents |
|---|---|
| `V3_VENUE_R1_ENRICHMENT.csv` | 3,454 rows × 35 columns, sorted by `game_id` |
| `V3_VENUE_R1_SOURCE_ACQUISITION_MANIFEST.json` | Every URL, HTTP status, retrieval UTC, and decompressed SHA-256 |
| `V3_VENUE_R1_SOURCE_CUSTODY_MANIFEST.json` | Digests re-derived from bytes at build time |
| `V3_VENUE_R1_MATCH_REPORT.json` | Matched / refused / unmatched with method breakdown |
| `V3_VENUE_R1_COVERAGE_REPORT.json` | Full coverage counts |
| `V3_VENUE_R1_CONFLICT_REPORT.json` | Both evidence records per conflicting game |
| `V3_VENUE_R1_TEAM_IDENTITY_MAP.json` | Harvested identity map and division membership |
| `V3_VENUE_R1_CORPUS_JOIN_REPORT.json` | Read-only join onto R6, with the corpus digest |
| `V3_VENUE_R1_REGISTRATION_RECEIPT.json` | Enrichment digest and the empty promotion record |
| `raw/` | 281 gzipped source captures, written once, never overwritten |

## Reproducing

```
python scripts/acquire_venue_sources_r1.py      # refuses to overwrite existing captures
python scripts/build_venue_enrichment_r1.py \
    --corpus-csv <R6 corpus, read only> \
    --corpus-exclusion-report <R6 exclusion report, read only>
python -m pytest tests/dynamic_weekly_mc_v3/test_r7_venue_enrichment.py
```

A build is a pure function of the bytes in custody — it retrieves nothing, takes
about a second, and is byte-identical across runs. The corpus is read from
another branch, never copied into this one and never modified; its SHA-256 is
recorded in the join report so a reader can tell which corpus a number was
computed against.

## What remains blocked

* **Completion and observability instants** — not carried by any source reachable
  by this lane.
* **NCAA-official venue** — venue is tier-5 evidence because tiers 1–4 answer
  404 or 403 for it. If NCAA game-detail access is ever obtained, the same
  matching layer can re-derive venue at tier 1 without changing the join.
* **Bowl and playoff games** — 0 in the universe, because the NCAA scoreboard
  feed carries no postseason games at all. Not a matching failure; the games are
  not in the identity source. Bowls therefore cannot enter calibration through
  this corpus regardless of venue.
* **Division for 35 rows** — Colorado State and Hawaii (2021) and Delaware (2024)
  appear in *both* feeds' exclusive game sets, so feed membership does not
  determine their division. Left `UNRESOLVED` rather than guessed. Venue is
  resolved for these rows regardless; only the division label is withheld.
