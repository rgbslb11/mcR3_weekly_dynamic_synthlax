# OPERATION SYTHALAX — Autonomous Model-Run Supervisor (R1 + R2)

Branch: `claude/v3-autonomous-model-run-supervisor-r1`
Frozen base: `5479f2ae7687c36c0ed4117334171289693dd5c9`
Disposition: **ORCHESTRATION MECHANISM BUILT — NO CALIBRATION RUN, NO PARAMETER PROMOTED**
R2: **EXECUTION HARDENING — MANIFEST DOMAIN GATE, MIXED DISPOSITIONS, ONE HUMAN GATE**

Entry point: `python -m ncaaf_engine.simulation.dynamic_weekly_mc_v3.supervisor`
Wrapper: `scripts/Invoke-SythalaxV3Supervisor.ps1`
Config template: `config/dynamic_weekly_mc_v3/supervisor/v3_autonomous_run.json`

No parameter was promoted, no blocker was retired, no calibration was run, no
season Monte Carlo was executed, and no canonical configuration was written.
The eight formal blockers are exactly where the base commit left them.

---

## 1. What this lane built

A deterministic supervisor that can drive the remaining V3 model run — frozen
synthetic evidence through calibration, validation, holdout, the single human
approval gate, 500 DEV, 2,000 ANALYSIS, 10,000 PUBLISH and final freeze — from
one command, stopping only for a genuine evidence or model failure, the human
parameter gate, or an unrecoverable execution error.

It is a mechanism, not a run. It contains no model mathematics and no parameter
values. What may be fitted is read out of frozen evidence that does not yet
exist; what is computed is delegated to a `ModelRunExecutor` whose default
implementation refuses every call. Pointed at this repository today, `plan`
reports that the evidence authority does not resolve and every run fails closed,
which is the correct answer.

R2 hardened three things for execution: the primary-domain gate now reads a
frozen manifest keyed on source byte digests rather than on names; the
recommendation carries an epistemic disposition per parameter so a vector that
is only partly fitted can still reach its human; and the tier gates derive
convergence from the run samples, which removes the second human stop that a
missing tolerance used to create.

---

## 2. The state machine

Thirty-five states on a linear spine, plus two halt states. The spine is
declared once, in `supervisor/states.py`, and the legal edge set is *derived*
from it: each live state reaches exactly its successor plus the halts it is
entitled to. Before the approval that is both halts; from `PARAMETERS_APPROVED`
onward it is `HALTED_FAILED` alone, which is how "one human gate" is a property
of the machine rather than a convention its gates observe.

```
INITIALIZED
SYNTHETIC_EVIDENCE_REQUIRED        -> SYNTHETIC_EVIDENCE_ACCEPTED
CALIBRATION_DATASET_REQUIRED       -> CALIBRATION_DATASET_READY
PREFLIGHT_REQUIRED                 -> PREFLIGHT_PASS
POINT_SCALE_DECISION_REQUIRED      -> POINT_SCALE_READY_OR_FIXED
COARSE_SEARCH_REQUIRED             -> COARSE_SEARCH_COMPLETE
REFINEMENT_REQUIRED                -> REFINEMENT_COMPLETE
VALIDATION_REQUIRED                -> VALIDATION_COMPLETE
HOLDOUT_LOCKED -> HOLDOUT_RELEASED -> HOLDOUT_COMPLETE
GAME_SD_REQUIRED                   -> GAME_SD_COMPLETE
FCS_ADAPTER_REQUIRED               -> FCS_ADAPTER_COMPLETE_OR_EXPLICITLY_UNIDENTIFIED
REAL_WORLD_WITNESS_REQUIRED        -> REAL_WORLD_WITNESS_COMPLETE
PARAMETER_RECOMMENDATION_READY
AWAITING_HUMAN_APPROVAL            -> PARAMETERS_APPROVED
DEV_500_REQUIRED                   -> DEV_500_PASS
ANALYSIS_2000_REQUIRED             -> ANALYSIS_2000_PASS
PUBLISH_10000_REQUIRED             -> PUBLISH_10000_PASS
FINAL_FREEZE_REQUIRED              -> COMPLETE

HALTED_FAILED             (genuine failure, or unrecoverable execution error)
HALTED_FOR_HUMAN_REVIEW   (a decision the supervisor may not make)
```

Because the only edge into a later state departs from the completion of the one
before it, "DEV failure blocks ANALYSIS" is structural rather than a check
somebody remembered to write. Neither halt state has an outgoing edge: a halted
run is re-entered by a human under new evidence, never by the supervisor
deciding the failure has aged out.

---

## 3. Governing calibration doctrine, as enforced code

**Synthetic-only primary estimation, decided by bytes (R2).** The authoritative
primary-domain gate is the frozen Agent-12 R2 evidence manifest in
`supervisor/domain_manifest.py`, resolved from
`origin/claude/v3-synthetic-2024-2025-calibration-corpus-r1` to an exact commit
and read out of the git object store — never from the sibling worktree, whose
contents depend on when somebody looked. It classifies every admissible source
by the SHA-256 of its bytes and verifies eight things per source: source SHA,
source lineage, season, domain classification, per-field admission, the
manifest-level forbidden-field list, parameter eligibility, and the dataset and
split the source belongs to. A real 2021–2024 corpus saved as
`synthetic_2025_estimation_table.json` hashes to what it always hashed to and
classifies as what it always was; `require_primary_estimation_source` refuses it
citing lineage, and no code path consults the filename. An unregistered digest
is refused for every purpose rather than defaulted, and a manifest that declares
a real-observed lineage as `PRIMARY_ESTIMATION_DOMAIN` does not load at all.
With no authority configured, or with the manifest absent from the pinned
commit, every run fails closed with nothing classified.

The `REAL_*` / bare-year / `OBSERVED_*` / `HISTORICAL_*` label patterns in
`supervisor/evidence.py` remain, demoted to what they always were:
`FILENAME_CHECKS_ROLE = DEFENSE_IN_DEPTH_SECONDARY_NEVER_AUTHORITATIVE`. They
run alongside the manifest gate and can only add a refusal. They catch a
mislabelled season inside an otherwise well-formed manifest; they are not asked
to catch a renamed file, and they cannot.

**Supersession (R2).** `supervisor/authority.py` ranks evidence generations —
`AGENT12_R1`, `AGENT12_R5_DISCOVERY`, `AGENT12_R2` — and the highest rank wins
each question. Stale eligibility claims from the earlier records, including the
`P_TO_STRENGTH_TRANSFORM` and reference-HFA blocker findings, no longer decide
anything: `require_current_authority` refuses a superseded generation acting as
the authority, and `resolve_claim` returns the winner together with everything
it superseded. Nothing older is edited or deleted — the earlier records explain
why the current authority exists, and the run reports the override rather than
smoothing it over.

**Real football is witness only.** The accepted corpus
`31504e8d03b68de549bb999f2ce6a62824eb3286e3802712534d3092fa3f7aac` is admitted
only under `EXTERNAL_WITNESS_ONLY`, and `require_vector_unchanged` is called on
the way out of the witness stage with the vector as it went in. A witness that
writes back through the mapping it was handed halts the run.

**Circularity is classified, not assumed.** Every parameter declares the
circularity class of its evidence. `GENERATED_BY_MECHANISM_UNDER_ESTIMATION`
forces `CIRCULAR_NOT_IDENTIFIABLE`; `UNCLASSIFIED` cannot support a fit at all.

**Point scale is conditional.** Nothing presumes the 14-points-per-standardized-unit
scale must be fitted. All four resolutions are supported — `FIT_ALLOWED`,
`FIXED_EXISTING_VALUE`, `CIRCULAR_NOT_IDENTIFIABLE`, `BLOCKED` — and the
manifest's resolution and its `point_scale` eligibility must agree or the
manifest does not load.

---

## 4. Identification, and refusing to invent a number

`supervisor/search.py` is a Python grid search, not a judgement call. Two
outcomes are deliberately *not* numbers:

* **Boundary optimum.** A best point on the edge of the declared range is not a
  result — the objective may still be falling off the end. The range is widened
  on the side that bound and searched again, up to a finite declared budget.
  Still boundary-bound afterwards is `BOUNDARY_BOUND_AT_MAX_EXPANSION` and
  `PARAMETER_UNIDENTIFIED`, which stops for human review. A boundary that is a
  declared physical limit reports separately, because no further searching would
  help.
* **Non-binding constraint.** If `weekly_movement_cap_points` never binds among
  the evidentially equivalent finalists, every value above the largest observed
  movement scores identically and the winner is an artifact of the tie-break.
  That is `UNIDENTIFIED_NONBINDING` with `recommended_value: null`.

`ParameterRecommendation` refuses to carry a number alongside either status, so
the artifact cannot be skimmed into a value that was never measured.

### 4a. Mixed epistemic dispositions (R2)

R1 could represent one thing: a parameter was fitted, or the run refused. The R2
evidence settles that the final V3 vector will not look like that, so
`supervisor/dispositions.py` makes the epistemic class a first-class value.
Nine are recognised and the set is closed:

| Disposition | Carries a value | Meaning |
| --- | --- | --- |
| `FIT_RESULT` | yes | A search ran and identified it. The only measurement this run makes. |
| `FIXED_PRIOR` | yes | A governed value carried forward. Nothing measured it here. |
| `PRIOR_ONLY` | yes | The evidence supports a prior, explicitly not a fit. |
| `RESIDUAL_DERIVED` | yes | Determined by other accepted quantities, recorded as derived. |
| `UNIDENTIFIED` | no | The objective could not distinguish a value. |
| `CIRCULAR_NOT_IDENTIFIABLE` | no | The evidence is the mechanism's own output. |
| `WITNESS_ONLY` | no | Diagnoses plausibility; may never select a value. |
| `MISSING_FAIL_CLOSED` | no | No evidence at all. A state of knowledge, never a basis for execution. |
| `HUMAN_SELECTION_REQUIRED` | optional | Valueless as a question, valued once the approver answers. |

`ESTIMATOR_ADMISSIBLE` is `(FIT_RESULT,)`, so only a parameter with permission
*and* a search space reaches a search; every other disposition is refused by
`require_estimator_admissible` rather than by a check somebody remembered.

The likely current matrix reaches `PARAMETER_RECOMMENDATION_READY` intact:
`point_scale`, `weekly_performance_residual_coefficient` and
`weekly_movement_cap_points` circular; `recent_form_weights`
`UNIDENTIFIED` under the reason code
`RECENT_FORM_UNIDENTIFIED_FROM_SYNTHETIC_EVIDENCE`; `blowout_treatment` and
`sample_size_regularization` `FIT_RESULT` where Wave 1 identifies them;
`game_sd_points` a fixed or human disposition under current evidence; and
`fcs_point_adapter` `MISSING_FAIL_CLOSED`.

**Production semantics decide what absence costs.** `PRODUCTION_VALUE_SEMANTICS`
marks every governed parameter `VALUE_REQUIRED_FOR_EXECUTION` except
`fcs_point_adapter`, which is `VALUE_REQUIRED_AT_USE_SITE`. So a missing FCS
adapter does not stop the run — every FCS game that needs a point adapter fails
closed, and no value is invented for it — while a missing weekly coefficient
does stop it, because production reads that on every path.

Nothing is invented for the parameters that carry no measurement. Where
production needs a value this run could not produce, the recommendation asks the
approver for one, at the single gate and nowhere else.

---

## 5. Holdout custody

Five bindings are taken before release — dataset SHA, split SHA, experiment
config SHA, candidate universe digest, scoring oracle digest — and re-derived
and compared at release. Release is legal only from `HOLDOUT_LOCKED`, happens
once, and scoring happens once; a second attempt at either is refused and names
the earlier outcome.

During candidate generation the scoring oracle is wrapped in the run's holdout
guard, and a holdout read *raises*. The executor is handed the guarded oracle,
not the raw one, so anything it scores for itself — finalists, sensitivity — is
refused on the same terms.

---

## 6. The one human gate

`AWAITING_HUMAN_APPROVAL`, action `APPROVE_V3_CALIBRATION_R1`, bound to the
recommendation's SHA-256. That digest covers the recommended values, every piece
of evidence behind them, and the evidence-manifest, dataset, split, experiment,
candidate-universe, oracle, input-manifest, code-tree and holdout-seal digests.

Refused: a wrong SHA, a malformed SHA, a stale recommendation superseded by a
newer one, changed inputs, changed code, a changed dataset, a changed scoring
oracle, an unnamed approver, an unknown action, and approval from any state but
the gate. Nothing in the supervisor can construct an approval on its own behalf.

**The approval binds values and epistemic statuses (R2).** Every question the
recommendation raises under `human_disposition_requests` must be answered, as
`{parameter: {"value": ..., "status": ...}}`, and both the approved value vector
and the approved disposition vector go inside the approval digest. Answering
with an absence is legitimate and is recorded as an answer —
`{"fcs_point_adapter": {"value": null, "status": "MISSING_FAIL_CLOSED"}}` keeps
the FCS use sites failing closed. Refused alongside the R1 list: an approval
that ignores a question, an unrecognised status, a value under a status that
cannot carry one, and an answer for a parameter the recommendation did *not*
ask about, which would overwrite a measured value at the one moment nobody is
watching for a substitution.

Approving an absence is not authorising execution.
`require_approval_for_execution` re-derives the execution obstacles from the
*approved* vector, so a parameter production reads on every path and still has
no value stops the tiers even though its status was approved.

**One human gate, structurally (R2).** After a valid approval the run proceeds
through 500 → 2,000 → 10,000 → freeze with no further prompts. That is not a
policy the gates cooperate with — `POST_APPROVAL_STATES` have no edge to
`HALTED_FOR_HUMAN_REVIEW` at all, so a tier gate cannot introduce a second stop
by returning `HUMAN_REVIEW_REQUIRED` and a future one cannot introduce it by
forgetting not to. A required-advisory policy stop applies only before the
approval; after it, `PASS_WITH_ADVISORY` always continues.

---

## 7. Tier gates

Every tier is checked for exact path count, deterministic seed replay, absence
of NaN/Inf, probability range and mass validity, team identity, conference
standings structure, CCG structure, CFP topology, impossible duplicate
participants, failed assertions, required artifacts and artifact hashes.

### Convergence, derived from the samples (R2)

R1 compared tiers against predeclared absolute tolerances and stopped for a
human wherever one was missing. That avoided choosing a tolerance after seeing
the divergence, and it was also a second human stop. R2 does not need a
tolerance: the disagreement two Monte Carlo runs *should* show is computable
from the estimates and their path counts. `supervisor/convergence.py`:

```
SE(p, N)  = sqrt(p * (1 - p) / N)          # a path-fraction probability
SE_delta  = sqrt(SE_1^2 + SE_2^2)          # two independent estimates
z         = |p_2 - p_1| / SE_delta
```

Declared thresholds, not magic percentages: `FAMILY_WISE_ALPHA = 0.01` spent
across the predeclared headline family by the Šidák correction; `OUTLIER_Z = 3.0`
as the per-output flag for the wide family, which fires on ≈0.27% of outputs by
construction; `CATASTROPHIC_Z = 6.0` for a single output too far out to be
sampling; `OUTLIER_PROPORTION_ALPHA = 0.001` for the proportion rule.

**Not every number is a Bernoulli probability.** A mean's variance is not
`p(1-p)`. Where the run reports an empirical standard error it is used directly;
where it does not, the quantity is `NOT_DIAGNOSED_NO_VARIANCE_MODEL` — not
passed, not failed, and no variance invented for it. Legacy `aggregates` with no
declared kind fall in the same class; the R2 report contract is `quantities`,
where each entry says what it is.

**Multiple comparisons.** A season report carries hundreds of team probabilities,
and at `z = 3` the chance of at least one flag among 300 healthy outputs is about
56%. Three rules apply at once, and the policy is
`PREDECLARED_HEADLINE_FAMILY_WISE + PROPORTION_OF_OUTLIERS + CATASTROPHIC_SINGLE_OUTPUT`:

1. **Predeclared headline subset** at the family-wise threshold. Any breach
   fails. A headline quantity that cannot be diagnosed also fails, because a
   quantity nobody could compare is not one that passed.
2. **Proportion of outliers** over the whole diagnosed family: fail only when the
   observed count is less likely than `OUTLIER_PROPORTION_ALPHA` under the
   binomial upper tail at the expected rate. One flag in three hundred is
   expected; forty is systematic.
3. **Catastrophic single output** past `CATASTROPHIC_Z`, which fails regardless
   of how few there are.

Outliers are never hidden: every flagged output appears in the diagnostic detail
with its `z` whether or not it changed the verdict.

500 → 2,000 and 2,000 → 10,000 both use this, classify `PASS`,
`PASS_WITH_ADVISORY` or `FAIL`, and never ask a question.
`PASS_WITH_ADVISORY` continues automatically; `FAIL` stops before the next tier.

The 10,000-path gate adds output-schema completeness, champion/conference/CFP
totals, standings tiebreak integrity, postseason topology, binding match, and
the stability diagnostic against the 2,000-path run — a publish tier with
nothing to compare against fails, because a freeze cannot be earned by silence.
Final freeze delegates the tier question to
`run_tier.require_publish_freeze_tier` rather than re-deciding it, and no freeze
artifact is written unless the gate passes.

---

## 7a. Wave-1 result ingestion (R2)

`supervisor/wave1.py` is the interface for the SHA-bound Wave-1 calibration
result from `origin/claude/v3-calibration-orchestrator-r1`, covering
`blowout_treatment` and `sample_size_regularization`. It is built now and does
not require the result to exist now: absence is a state (`WAVE1_NOT_PRESENT`),
reported by `plan` with the commit that was looked in, and it authorises nothing
— the two parameters keep whatever disposition the evidence manifest gives them.

When present, ten bindings are verified against what the supervisor
*independently* holds, never against another field of the same package:
execution commit, execution tree, evidence manifest, dataset, split, candidate
universe, scoring oracle, experiment config, field-admission artifact, and the
per-parameter result status. The candidate universe is computed over every axis
the manifest authorises rather than over the axes this run will search, so the
expectation does not change depending on whether the package exists. A package
bound to a different world is refused with both sides of every mismatch named. A
verified `FIT_RESULT` settles its parameter and the supervisor does not re-fit
it; re-fitting would produce a second answer bound to the same evidence with no
principled way to choose. The package is read from the object store at a pinned
commit — no live worktree read anywhere in the module.

---

## 8. Retries, resume, concurrency

**Retries are narrow.** One execution retry exists: on a matching Windows
filesystem or temp-lock failure — the stale `pytest-of-<user>` root and MAX_PATH
conditions `conftest.py` documents — a fresh short isolated basetemp is created
and the stage is retried **once**. Anything unmatched propagates untouched,
including every model failure. The other automatic behaviours (unavailable
optional witness, boundary expansion, unidentifiable FCS adapter) are
classifications, not retries, and none downgrades required evidence.

**Resume verifies before continuing.** State is written atomically
(temp-then-`os.replace`, same directory). Each stage result is immutable —
identical content replays, different content is a conflict. On restart the
supervisor re-derives its own code-tree digest and the run's input digest and
refuses on drift, then rehydrates from the same stage-result files an auditor
would read.

**One owner per run.** `RunLock` is an exclusive-create lock file. A lock left
by a crash is reported, never stolen: deciding another process is dead is not a
judgement that can be made from inside the supervisor.

---

## 9. What was deliberately not done

* No calibration values invented, and none promoted.
* No real calibration run; no 500, 2,000 or 10,000-path execution.
* The eight formal blockers are unchanged.
* V2.1 untouched; synthetic 2024/2025 source data untouched.
* No real 2021–2024 observation pooled into any fitting table.
* No sibling worktree read. Cross-lane inputs are frozen artifacts bound by
  digest and read from the git object store at a pinned commit, never live
  directory reads.
* R2 changed no canonical formal blocker. `blockers_before = 8`,
  `blockers_after = 8`. Learning to represent a non-fit disposition is not the
  same as closing the thing the disposition describes.
* The Agent-12 R2 evidence manifest does not exist on its branch yet, so the
  authority does not resolve, `plan` reports the absence, and every run fails
  closed. That is the correct state, and it is the state R2 was built to hold
  correctly.
