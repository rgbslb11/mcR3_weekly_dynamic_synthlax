# OPERATION SYTHALAX — Leak-Free Historical Opening Backcast (R1)

Branch: `claude/v3-opening-backcast-r1`
Frozen base: `5479f2ae7687c36c0ed4117334171289693dd5c9`
Disposition: **PROXY_VALID_FOR_LIMITED_CALIBRATION_ONLY**

Machine-readable record: `reference/dynamic_weekly_mc_v3/opening_backcast_r1/V3_OPENING_BACKCAST_R1.json`.

No parameter was promoted, no blocker retired, no allowlist widened, no canonical
writer built, no FCS adapter installed, no football point emitted, no per-team
opening value emitted, and no season Monte Carlo run.

---

## 1. The short version

A strictly leak-free historical opening state can be built, and it works. For
2022, 2023 and 2024 it can be constructed from real NCAA-published results and
nothing else, it predicts that season's margins with a positive and substantial
slope in every season, and compared against V3's own opening construction it
agrees at a Pearson correlation of 0.98.

Three things stop that from being a good-news finding.

It is **one family out of four**. Only Pure Baxter — 0.25 of the Unified Z
ensemble weight — can be rebuilt from results. And the multi-family ensemble
that would look structurally like Unified Z is not merely unavailable: it is
**already refused** by governance mounted in this repository, because a blend of
Baxter, Colley and SRS is the Body-of-Work Index that ACC-EXT-12 records
PROPOSAL ONLY / NOT ADOPTED.

The **2021 opening cannot be built**, and the reason is not the one everybody
expects. The 2020 data are acquirable — probed, HTTP 200, digests recorded. The
2020 *season* is what fails: under the observation corpus's own admission rule
it collapses to 38 teams.

And the proxy carries a **signed bias**, measured, into exactly the parameters
one would reach for first. It recovers between 0.48 and 0.68 of the point-scale
slope a same-season reference recovers, and leaves 4.4 to 5.7 more points of
residual dispersion behind. Those two facts have one cause and they do not
average out across seasons.

So the answer to "can a leak-free proxy support calibration" is: yes, for three
of the seven parameters, and no for the four that most people mean when they ask.

---

## 2. The finding that makes the rest of it tractable

The governed offseason transitions are affine, and standardization is
affine-invariant.

```text
TrueSkill    mu_Y          = 25 + 0.70 * (mu_(Y-1) - 25)
Pure Baxter  pure_baxter_Y = 0.70 * baxter_ridge_(Y-1)
```

Both are `a*x + b` with `a > 0`. A Z score does not move under one. So **for a
team that holds a prior state, the opening Z of a carryover family simply is the
standardized prior-season final rating** — exactly, to floating point, not
approximately.

This is worth stating carefully because it cuts both ways.

It means a proxy does not have to *approximate* the offseason regression step.
It reproduces it. Every error the proxy carries lives somewhere else: in the
prior-season rating engine, in the population it standardizes over, and in the
families it cannot build. The 0.70 is not one of them.

It also means the 0.70 is **not identifiable from a standardized opening state**,
in the real V3 construction any more than in a proxy of it. It is visible only
on the native point axis. A future lane that hopes to validate the offseason
regression coefficient against opening Z values is chasing a quantity that has
been divided out.

The slope is measured, not quoted. The Data Dictionary states the Pure Baxter
rule in prose; the Master Ratings sheet carries both sides of it, and the ratio
of column AQ to column AM is 0.70 for all 121 teams to within 1e-12.
`test_the_pure_baxter_carryover_slope_is_exactly_the_registered_one` asserts it
against the workbook so a replacement input that changes the rule fails the
suite rather than silently changing every conclusion built on the old one.

---

## 3. First test — can a prior-season final state be formed?

Yes, for three of the four requested transitions, from
`V3_R6_OBSERVATION_CORPUS.csv` (SHA-256 `31504e8d…fa3f7aac`), 2,241 real
FBS-versus-FBS observations published by the NCAA's own scoreboard feed, joined
to `V3_VENUE_R1_ENRICHMENT.csv` (SHA-256 `3e7c965e…62d78778`) for the
neutral-site indicator. The join is exact: 2,241 of 2,241 rows matched, every one
`VENUE_EVIDENCE_BOUND`, 67 neutral-site games, 30 conference championships.

| Season | Games | Teams | Components | Games/team min–median–max | Fitted season HFA | Baxter SD | SRS SD |
|---|---:|---:|---:|---|---:|---:|---:|
| 2021 | 556 | 105 | 1 | 8 – 11 – 12 | 1.63 | 12.33 | 9.84 |
| 2022 | 524 | 101 | 1 | 8 – 10 – 12 | 2.45 | 12.63 | 10.50 |
| 2023 | 598 | 114 | 1 | 8 – 11 – 13 | 2.98 | 11.94 | 9.93 |
| 2024 | 563 | 108 | 1 | 8 – 10 – 13 | 3.01 | 12.21 | 10.23 |

Each season's schedule graph is a single connected component. That is not
decoration: `compute_srs` centres per component precisely because a disconnected
graph has one degree of freedom per piece, and on such a graph no single
standardization would be defined at all. Connectivity is what makes one Z score
over the whole population meaningful.

Three systems were computed and none was invented:

- **Baxter margin ridge**, under frozen doctrine `BAXTER-MOV-v1.0-R`: predicted
  margin = season HFA × non-neutral indicator + rating(home) − rating(away);
  per-game margin cap 49; ridge λ = 0.3 on team terms only; HFA unpenalised;
  ratings sum to zero within the season. Every one of those five clauses is
  quoted from the Doctrine sheet, not chosen here.
- **SRS**, using this repository's own solver at its governed ±24 cap.
- **Colley matrix**, as a second witness, from the standard published
  construction.

Year over year, the margin-based families carry a real signal and the win–loss
family carries materially less:

| Family | 2021→2022 | 2022→2023 | 2023→2024 |
|---|---:|---:|---:|
| Baxter | 0.683 | 0.715 | 0.652 |
| SRS | 0.666 | 0.728 | 0.657 |
| Colley | 0.549 | 0.625 | 0.467 |

A margin-based prior season explains roughly 42–53 per cent of the next season's
rating variance. That is the whole raw material a carryover proxy has.

### What the fitted HFA is, and is not

The season HFA the Baxter doctrine fits lands at 1.63, 2.45, 2.98 and 3.01
points. The governed V3 value is 3.5, LOCKED under `R2-HFA-3P5`, and it is not
an estimand here. These are witnesses in their own namespace, and the low 2021
figure is more likely a symptom of the truncated schedule graph (§7) than a
statement about home field.

---

## 4. Multi-family: the ensemble is refused, not merely unavailable

The lane instruction asked whether the computable historical families could form
something structurally analogous to Unified Z. The answer is no, for two
independent reasons, either sufficient on its own.

**Three of the four families cannot be rebuilt.**

| Family | Weight | Native units | Standardization | Earliest state | Reproducible? |
|---|---:|---|---|---|---|
| TrueSkill | 0.25 | skill μ | Z over 121, ddof 1 | 2025 wk 1, flat at μ=25 | **No** |
| Litkenhous | 0.25 | power margin, rating = power + 100 | Z over 121, ddof 1 | 2025 finals | **No** |
| Pure Baxter | 0.25 | zero-centred margin points | Z over 121, ddof 1 | 2025 ridge fit | **Yes** |
| Board family | 0.25 | two board scales | each standardized, then averaged | 2026 only | **No** |

TrueSkill's transition rule is affine and would be reproducible — but no
TrueSkill update engine is mounted anywhere in this repository, and the chain is
initialised flat at μ = 25 for every team at 2025 Week 1, so there is no earlier
posterior to carry. Fitting a substitute latent-skill model would be inventing a
system, which the instruction forbids and which would in any case not be the
family V3 weights.

Litkenhous is a carryover plus an offseason composite: the carryover half needs a
prior Litkenhous rating that does not exist before 2025, and the composite half
is not a function of results at all. The Board family's components — baseline,
returning production, movement, talent, coaching, market, 247 points — are the
offseason itself, and no board of any letter exists for 2021–2024.

Team coverage for all four in 2026 is 121 of 121, so the gap is temporal, not
partial.

**And the families that can be computed may not be combined.** SRS and Colley
are exactly the two systems a results-only proxy could add. Ruling
`R2-CAL-OBJECTIVE` names out-of-sample Baxter Rating RMSE the primary criterion
and keeps Colley and SRS as *independent witnesses*, and
`srs.reject_witness_composite` raises `GovernanceBlock` on any weighted blend of
them, because that blend is the Body-of-Work Index recorded PROPOSAL ONLY / NOT
ADOPTED in `18_ACC_POLICY_REFERENCE` ACC-EXT-12. This was tested rather than
assumed; the refusal fires on all three pairings and passes on a single family.

The consequence is worth stating plainly. The admissible proxy shape —
**one family, with witnesses reported beside it and never blended** — is V3's own
calibration reporting shape. It is not the Unified Z ensemble shape. Those two
shapes were never the same thing, and a proxy that respected the calibration
ruling would have to violate the ensemble structure to look like Unified Z.

On weights: the 0.25s **are** authorised, and only for the four named 2026
families. The workbook's Ensemble Parameters sheet carries them explicitly and
its Validation sheet checks that they sum to 1 across an included family count of
4. Nothing extends that authority to any other family set, so no equal-weight
proxy ensemble was built.

---

## 5. Continuity, and a gap that is not what it looks like

The 2026 record carries two governed new-entrant precedents, and they disagree
with each other in the way that matters here:

| Family | Status recorded for teams with no prior state | Teams | Reproducible historically |
|---|---|---:|---|
| TrueSkill | `POPULATION_PRIOR_NO_2025_EVIDENCE` → `P0_POPULATION_PRIOR` | 2 | Yes |
| Pure Baxter | `Imputed new entrant from Baxter~Board J baseline regression` | 2 | **No** |

The family whose imputation rule *is* authorised for the axis being built is the
family whose imputation rule is *unavailable* — it regresses on a Board J
baseline, and no board exists for any historical season. The population-mean
precedent is reproducible but belongs to a different family, and borrowing a
new-entrant rule across families is not authorised by anything mounted. A
transition prior and an FCS mapping both reduce to the open FCS adapter blocker
in different costumes.

No authority selects among the four. So teams without a prior-season state are
**excluded and named**, never imputed:

| Opening | Teams needing a state | With one | Excluded |
|---|---:|---:|---|
| 2022 | 101 | 101 | none |
| 2023 | 114 | 101 | ARMY, ARST, CCU, GASO, GAST, MRSH, ODU, TROY, TXST, UConn, ULL, ULM, USM |
| 2024 | 108 | 108 | none |

**None of those 13 is a new FBS entrant.** They are teams whose 2022 games were
pruned by the corpus's iterative eight-game floor after their opponents failed
identity resolution. The continuity gap is a corpus artifact, not a membership
event.

Which raises the sharper point. The real FBS entrants of this period — James
Madison, Jacksonville State, Sam Houston, Kennesaw State — never enter the corpus
at all, because the synthetic 2026 canonical universe does not carry them. The
continuity problem is **masked by the identity filter, not solved by it**. A
corpus built over a historically faithful universe would face it in full, and
would need the ruling this lane could not make.

---

## 6. 2020: available, and still not usable

A 2021 opening needs a 2020 final state. What is needed, exactly:

1. the 2020 FBS scoreboard for weeks 1–15, which is where the games are;
2. the 2020 FCS scoreboard as the division oracle, under the corpus's own rule —
   a game appears in both scoreboards exactly when it crosses divisions;
3. a venue enrichment pass over 2020, because the NCAA feed publishes no
   neutral-site indicator and the Baxter doctrine's HFA term requires one; the
   existing enrichment covers 2021–2024 only;
4. identity resolution of the 2020 participants against whatever population a
   2021 opening would be standardized over.

**Can they be acquired from the same authoritative source family? Yes.** The
R6 corpus retrieved seasons 2021–2025 and never probed 2020. This lane did:
`https://data.ncaa.com/casablanca/scoreboard/football/{fbs,fcs}/2020/{week}/scoreboard.json`,
weeks 1–19 both divisions. Every FBS week returns HTTP 200; weeks 16–19 return a
valid document carrying zero games. FCS weeks 13 and 16–19 return 404. Per-week
response digests are recorded in the JSON artifact. Nothing was fabricated and
nothing was mounted — the bytes were retrieved to answer the availability
question, and adding a governed observation source is a corpus lane's action, not
this one's.

**And it still does not produce a 2021 opening.** The 2020 season's own content
is the obstacle:

| | 2020 | 2021 for comparison |
|---|---:|---:|
| FBS-feed rows | 616 | — |
| final / postponed / cancelled | 523 / 92 / 1 | — |
| FBS-versus-FBS final games | 489 | — |
| entities in an FBS-only game | 127 | — |
| games per team, min–median–max | 3 – 8 – 12 | 8 – 11 – 12 |
| teams below eight games | 57 of 127 | 0 of 105 |
| **after the corpus's iterative eight-game floor** | **171 games, 38 teams** | **556 games, 105 teams** |

Thirty-eight teams. Before identity resolution against the 121-team canonical
universe removes more. A 38-team remnant cannot standardize an opening state for
the ~105 teams the other three openings cover, and a population of 38 is not the
population any of them uses.

So the 2021 backcast is refused on **season quality**, not on acquisition.
Retrieving the bytes would not fix it. Only a ruling that relaxes the admission
floor for a pandemic-shortened season could, and that ruling is not this lane's
to make. The distinction matters because the two failures need opposite
remedies, and "get the 2020 data" is the wrong instruction.

---

## 7. Does it work? Two tests, and neither is the one that was asked for

### 7.1 Leak-free predictive validity

The proxy opening Z for season Y, built only from Y−1, against season Y's own
margins:

```text
margin_home = k * (Z_home - Z_away) + h * non_neutral_indicator
```

| Season | n | k (pts/SD) | h | residual SD | unconditional SD | R | weeks 1–2 k | weeks 1–2 n |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2022 | 524 | 7.62 | 3.34 | 17.60 | 20.19 | 0.490 | 12.47 | 58 |
| 2023 | 522 | 8.53 | 2.74 | 17.18 | 19.93 | 0.507 | 9.19 | 59 |
| 2024 | 563 | 6.19 | 3.35 | 18.31 | 19.78 | 0.378 | 7.10 | 58 |

Every slope is positive and substantial and residual dispersion falls below
unconditional dispersion in every season. This is a working opening state, not a
null one. The weeks 1–2 subsets are 58–59 observations each; they are reported
because that is the window the identification graph names, not because 58
observations settle anything.

### 7.2 Proxy against actual — the only season where both exist

The instruction asked for a comparison in a season where a proxy opening Z and an
actual V3-style opening Z both exist. There is exactly one: **2026**. And it is
not a historical test — the prior season it carries forward is synthetic, and the
field is the closed synthetic 121-team universe. What it measures is the
**construction** difference: one results-carryover family standing in for four.

`Pure Baxter Z` is, by construction, the standardized prior-season margin-ridge
fit carried forward. That is precisely the shape a historical single-family proxy
takes. Against the published `Unified Master Z`, n = 121:

| | value |
|---|---:|
| Pearson | 0.9826 |
| Spearman | 0.9600 |
| Kendall τ | 0.8416 |
| bias (mean difference) | 0.000 |
| SD of difference | 0.187 SD |
| max abs difference | 0.480 SD (6.7 pts at 14 pts/SD) |
| rank displacement mean / median / p90 / max | 6.8 / 4 / 18 / 36 |
| top-10 overlap | 9/10 |
| top-25 overlap | 24/25 |
| **top-4 overlap** | **2/4** |

Bias is zero by construction — both sides are standardized — so the whole of the
disagreement is dispersion and ordering.

Two readings of the 0.98, and the second one is the honest one.

The families **are not independent**. Litkenhous Adjusted Power correlates
0.9884 with Pure Baxter, because it too is largely a prior-season carryover with
an offseason overlay on top. Board family correlates 0.9764 with Litkenhous. The
ensemble diversifies considerably less than a four-family structure implies, and
that — not the proxy's quality — is a large part of why one family tracks four so
closely. It is a reason to be *less* impressed by the correlation, not more.

And the last row is the one that constrains use. V3 seeds playoff byes from the
top four, and the proxy disagrees about half of them. Aggregate agreement at 0.98
coexists with the model being wrong about the thing it is most sensitive to.

For completeness, a two-family proxy — the shape available if a TrueSkill engine
were ever mounted — reaches Pearson 0.9886, Spearman 0.9670, SD of difference
0.151. Adding a second carryover family buys about 0.035 SD of accuracy. Adding
Litkenhous reaches 0.9973, which is mostly a measurement of how much Litkenhous
already is the carryover.

### 7.3 Attenuation, quarantined

Refit the same regression with the season's own final rating in place of the
prior-season proxy. That predictor is built from season-Y games and is **leaky by
construction**; it is classified `LEAKY_REFERENCE_NOT_A_CALIBRATION_INPUT` and no
number derived from it is offered toward any parameter. It exists to measure one
thing: how much slope the proxy gives up.

| Season | k proxy | k same-season | ratio | residual SD proxy | residual SD reference |
|---|---:|---:|---:|---:|---:|
| 2022 | 7.62 | 13.38 | 0.569 | 17.60 | 12.72 |
| 2023 | 8.53 | 12.59 | 0.677 | 17.18 | 12.76 |
| 2024 | 6.19 | 12.88 | 0.480 | 18.31 | 12.66 |

The proxy recovers roughly half to two thirds of the available slope and leaves
4.4 to 5.7 more points of residual dispersion behind. **Same cause, same sign,
every season.** That is what makes it a bias and not noise, and it is the whole
basis of §8.

---

## 8. Calibration consequence — and yes, one parameter far more than the others

One mechanism drives every entry below. A proxy opening state is a noisier
measurement of the latent one, so any slope regressed on it is attenuated toward
zero and any residual measured around it is inflated. The biases are therefore
**signed**, and pooling seasons does not remove them.

| Parameter | Support | Contamination | Direction |
|---|---|---|---|
| **Point-scale identification** | REFUSED | **severe** | biased **low** |
| **Game SD** | bound only | **severe** | biased **high** |
| Weekly update response | REFUSED | high | biased high |
| Movement cap | REFUSED | high | inherits both |
| Blowout treatment | research-supported | low | mild |
| Recent form | research-supported | **lowest** | mild |
| Sample-size regularization | research-supported* | low from the proxy, **high from the corpus** | unquantified |

**Point-scale identification is the worst, and that is counter-intuitive.** The
expected-margin lane classified the axis scale `EMPIRICALLY_CALIBRATABLE`
precisely because weeks 1–2 precede the first promoted rerating, so no weekly
coefficient exists to absorb a rescale and the governed additive HFA stays a
fixed-length ruler. All of that is correct — *with the actual opening state*.
With a proxy it fails, because the estimator is a regression slope on a noisy
regressor, and the measured attenuation is 0.48–0.68. Any k estimated on the
proxy is a lower bound. It may not be promoted.

**Game SD is the mirror image.** `game_sd_points` is the residual dispersion
around the deterministic mean, and a weaker mean model leaves more variance
behind. The proxy's 17.2–18.3 bounds the parameter from above and locates
nothing — the same shape as the 19.764 figure the evidence lane already refused
to treat as corroboration, one step further in.

**Weekly update response is doubly blocked.** The residual is actual minus
expected, expected is built on the opening state in weeks 1–2, and a shrunken
opening state manufactures residuals that a fitted coefficient then absorbs —
biased high. Independently, `rerating.BlockedGovernedRerater` raises
unconditionally, so no governed formula exists for weeks 3+ to parameterise at
all.

**Movement cap** inherits the axis scale (it is expressed in points) and the
update response (it caps weekly movement). It cannot be estimated ahead of the
two parameters it is defined against.

**Blowout treatment and recent form** are the two the proxy genuinely supports.
Margins are observed directly; the proxy enters blowout treatment only through
which games were *expected* to be lopsided, and enters recent form only as the
baseline for the first weeks. Worth noting for the blowout question: the two
governed caps already in the record disagree — Baxter 49 points, SRS 24 — and
both are measurable against real margins without an opening axis at all.

**Sample-size regularization carries a different defect, and it is the sharper
one.** The proxy barely touches it. The *corpus* does: the observation set prunes
team-seasons below eight admitted games, which removes exactly the small-sample
cases the parameter governs. That is a selection defect in the sample, not a bias
from the proxy, and no amount of improving the opening state addresses it.

`opening_backcast.require_proxy_admissible_parameter` fails closed on the four
refused parameters and returns the register entry for the three supported ones,
so the distinction is executable rather than advisory.

---

## 9. A research observation about the point scale

Not a promotion, and not this lane's to settle. It is recorded because it bears
on two items that are already open.

`sd(Z_home − Z_away)` measured over the **locked 2026 schedule** with the
published Unified Master Z is **1.219**. Over the historical proxy fields it is
1.188 to 1.295. Those are nearly the same number, and the reason is scheduling,
not rating: teams play opponents near their own strength, so the difference
dispersion sits well below the 1.414 of random pairing. The proxy field and the
production field are geometrically comparable on this axis.

Which makes the following arithmetic legible. With `Var(margin) = Var(k·ΔZ) +
Var(residual)`:

| k (pts/SD) | predicted-margin SD | implied total margin SD with game SD 20.2 |
|---:|---:|---:|
| 14 | 17.07 | **26.44** |
| 10 | 12.19 | 23.59 |
| 8 | 9.75 | 22.43 |
| 7 | 8.53 | 21.93 |

Real FBS margin dispersion in 2021–2024 is 19.78 to 20.87. At the provisional 14
points per standard deviation *together with* the recorded 20.2-point game SD,
the implied total is 26.4 — far above anything observed.

At most one of those two values can survive against real football dispersion, and
both are already flagged: the workbook says of the 14 "recalibrate against game
margins", and `ENG-CAL-MARGIN` is OPEN against the 20.2. This observation
corroborates existing open items and settles neither. The 2026 field is
synthetic, so the arithmetic is indicative rather than decisive, and it is
recorded here so a later lane does not have to rediscover it.

---

## 10. Bias risks, in the order they would bite

| Risk | Severity | Signed |
|---|---|---|
| Errors-in-variables attenuation | high | **yes** |
| Population non-correspondence | high | no |
| Seed sensitivity | high | no |
| Omitted family structure | medium | no |
| Schedule-graph truncation | medium | **yes** |
| Small-sample selection | medium | **yes** |
| Unvalidated reimplementation | medium | no |
| Cross-lane dependency | medium | no |
| Season-specific native scale | low | no |

Two deserve a sentence beyond the JSON.

**Population non-correspondence** is the one most likely to be waved through. A Z
score is defined only against a population. This proxy standardizes over 101–114
teams resolved to the synthetic 2026 universe; the real FBS population of those
seasons was 130–133, and the historical opening-state lane records two mutually
inconsistent membership authorities for 2024 alone — 133 by one, 118 by the
other. A proxy standardized over a different population is not on the same axis
as a state standardized over the real one, however well the two correlate.

**Schedule-graph truncation** is signed and visible. Between 214 and 265 games
per season are excluded on unresolved identity, overwhelmingly against programmes
absent from the 2026 universe. Opponent adjustment is a property of the whole
graph, so every rating is adjusted against a truncated schedule and teams lose
different numbers of games. The fitted season HFA of 1.6–3.0, below the governed
3.5, is one visible symptom of it.

---

## 11. What this lane is not

It is not `claude/v3-opening-source-recovery-r1`. That lane is independently
trying to recover the exact historical V3 preseason component inputs. This one
assumes that recovery fails and asks whether a leak-free substitute can be built
from results alone. If the exact inputs are recovered, this proxy is superseded
and nothing here needs withdrawing, because nothing here was promoted.

It is not a rebuild of `claude/v3-historical-opening-state-r1`. That lane
established that no V3 preseason family has a state before 2025, and reimplemented
the 2026 construction exactly. Both are taken as given.

Both observation inputs live on **unmerged sibling branches** and were read as
evidence with their digests verified here, not copied into this branch. Every
measurement in this record is therefore conditional on those lanes integrating as
audited. The digests are recorded so the conditionality is checkable rather than
assumed.

`HISTORICAL_CALIBRATION_PROXY` and `EXACT_V3_PRESEASON_ENSEMBLE` are kept as two
named things by `opening_backcast.classify`, which refuses an unlabelled state
outright — the distinction is the point of the lane, and an unlabelled state
collapses it.

---

## 12. Decision

**`PROXY_VALID_FOR_LIMITED_CALIBRATION_ONLY`**

Valid: a strictly leak-free opening proxy exists, is constructible for 2022, 2023
and 2024 from real published results, carries genuine predictive signal, and
tracks the actual V3 construction at 0.98 in the one season both exist.

Limited: it is one family of four; the ensemble form is refused by mounted
governance; 2021 is unavailable; team coverage is 101–114 against a real FBS
population of 130–133; and it carries a measured, signed bias that refuses four
of the seven calibration parameters outright.

Not `PROXY_TOO_DIFFERENT_FROM_V3`, because it demonstrably reproduces the
carryover step exactly and the full construction closely. Not
`NO_LEAK_FREE_PROXY_AVAILABLE`, because one was built and measured. Not
`PROXY_VALID_FOR_CALIBRATION_RESEARCH` without qualification, because the two
parameters a researcher would most want from an opening state are the two it
biases hardest.

---

## 13. To unblock

1. **Rule on the population.** Nothing standardizes without one, and two mounted
   candidates disagree for 2024. This gates everything else here.
2. **Rule on new entrants for the Baxter family**, or accept exclusion-and-report
   as the standing policy. The governed precedent for this family requires a
   board that no historical season has.
3. **Rule on whether the eight-game admission floor applies to a
   pandemic-shortened season.** That, and only that, decides whether 2021 is ever
   reachable. Acquiring the 2020 bytes is not the blocker and would not help.
4. **Widen the identity universe, or accept the truncated graph as a known
   signed bias.** Between 25 and 30 per cent of each historical season's rows are
   excluded on unresolved identity, because the programme does not exist in the
   synthetic 2026 master.
5. If the point scale is to be estimated at all, estimate it against an
   opening state that is not a proxy — or estimate the proxy's reliability first
   and correct for attenuation explicitly. Neither is done here.

Items 1 and 2 are prerequisites for using the proxy for anything. Items 3 and 4
change its coverage. Item 5 is the one that must not be skipped quietly.

---

## 14. State

- Tests: **623 full**, **564 V3** — up from 602 / 543 at the frozen base, +21
  new, no existing test modified.
- `config.py` untouched. `v3_experimental.json` untouched; all six calibration
  values remain `null`.
- `V3_CALIBRATION_DATA_CONTRACT.json` untouched; `governed_allowlist` unchanged.
- Blockers: **8 before, 8 after.** None retired, none opened.
- No per-team opening value, in any unit, in any artifact of this lane.
- No season simulation of any path count was run.

The full-suite run needs an explicit short `--basetemp`; pytest's default form
spends enough of the 260-character budget on `pytest-of-<user>` and a numbered
session directory to trip the repository's own path-headroom test. That is the
test doing its job, not a repository defect.
