# OPERATION SYTHALAX — Autonomous Model-Run Supervisor (R1)

Branch: `claude/v3-autonomous-model-run-supervisor-r1`
Frozen base: `5479f2ae7687c36c0ed4117334171289693dd5c9`
Disposition: **ORCHESTRATION MECHANISM BUILT — NO CALIBRATION RUN, NO PARAMETER PROMOTED**

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
values. What may be fitted is read out of a frozen evidence manifest that does
not yet exist; what is computed is delegated to a `ModelRunExecutor` whose
default implementation refuses every call. Pointed at this repository today,
`plan` refuses because the manifest is absent, and that is the correct answer.

---

## 2. The state machine

Thirty-five states on a linear spine, plus two halt states. The spine is
declared once, in `supervisor/states.py`, and the legal edge set is *derived*
from it: each live state reaches exactly its successor plus the two halts.

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

**Synthetic-only primary estimation.** The frozen manifest declares its primary
estimation domain, and `require_synthetic_only_primary_estimation_domain`
refuses a manifest naming a real season at all — matched on `REAL_*`, a bare
four-digit year, `OBSERVED_*` and `HISTORICAL_*`, so the doctrine cannot be
sidestepped by renaming a key. The refusal is at *load*, because by the time a
real observation has entered the fitting table the contamination has happened.

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

After a valid approval the run proceeds through 500 → 2,000 → 10,000 → freeze
with no further prompts, provided every deterministic gate passes.

---

## 7. Tier gates

Every tier is checked for exact path count, deterministic seed replay, absence
of NaN/Inf, probability range and mass validity, team identity, conference
standings structure, CCG structure, CFP topology, impossible duplicate
participants, failed assertions, required artifacts and artifact hashes.

The 2,000-path gate adds convergence against the 500-path run. It does not
demand Monte Carlo equality: every compared aggregate needs a *predeclared*
tolerance, and an aggregate with none is `HUMAN_REVIEW_REQUIRED` rather than
either a pass or a fail, because a tolerance chosen once the divergence is
visible is a choice of outcome.

The 10,000-path gate adds output-schema completeness, champion/conference/CFP
totals, standings tiebreak integrity, postseason topology and binding match.
Final freeze delegates the tier question to
`run_tier.require_publish_freeze_tier` rather than re-deciding it, and no freeze
artifact is written unless the gate passes.

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
  digest, never live directory reads.
