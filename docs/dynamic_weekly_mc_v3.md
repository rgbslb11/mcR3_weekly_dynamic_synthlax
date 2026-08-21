# SYTHALAX Dynamic Weekly Monte Carlo V3 — Experimental Harness

## Authority boundary

`SYTHALAX_DYNAMIC_WEEKLY_MC_V3_EXPERIMENTAL` is an experimental simulation package. Deterministic Python software owns simulation math and state transitions. ChatGPT is not a runtime pricing/rating authority. The approved V2.1 10,000-season workbook is preserved byte-for-byte under `reference/dynamic_weekly_mc_v3/inputs/` as the static-rating control and is never rewritten by V3.

V3 currently supports **structural preflight and test-fixture execution only**. The production-facing rerater fails closed until unresolved calibration, provenance, and governance choices are explicitly resolved. Nulls in `v3_experimental.json` are deliberate control placeholders, not defaults.

## Weekly football-strength contract

For each independent path:

1. Freeze the current football-strength state.
2. Simulate every scheduled game in the current phase with a stateless SHA-256-keyed Gaussian draw.
3. Preserve expected margin, simulated margin, winner/loser, venue, performance residual, and rating-state version.
4. Build an experimental rerating candidate.
5. Week 1 candidate is **audit-only** and is not promoted; Week 2 still opens from preseason strength.
6. The first promoted rerating is after Week 2.
7. Preseason-prior weights are exactly: preseason 1.00, after W1 0.80 audit-only, after W2 0.60, after W3 0.40, after W4 0.20, after W5 0.00. After Week 5 the preseason-specific prior remains zero, while sample-size regularization remains a separate unresolved mechanism.
8. Weekly football strength is distinct from committee/resume rank. CFP selection, committee ranking, postseason advancement, and championship outcomes never feed back into football point strength.
9. The initial playoff implementation freezes football strength after CCG/selection.

## Season phase contract

The mounted Schedule v5 resolves into these deterministic phases:

- Weeks 1–14: 735 regular-season games; rerating occurs after each completed week subject to the W1 audit-only rule.
- Week 15: 7 conference-championship templates; CCG participants/venues must be resolved from governed rules; rerating occurs after the CCG phase before selection.
- Selection Day: committee ranking and the 14-team field are frozen; football strength is frozen for the initial playoff implementation.
- Week 16: exactly one regular-season game, Army–Navy (`G0736`), after Selection Day. It counts to season record but does not promote a new football-strength state in initial V3.
- CFP postseason: all games use the frozen post-CCG football-strength state.

The compatibility method `simulate_regular_season_path()` is intentionally only a W1–W14 test harness alias. It is not a production full-season runner.

## Determinism and path isolation

Random draws are keyed by `(base_seed, path_id, week, game_id, draw_slot)` rather than a shared mutable RNG stream. Reordering paths or worker execution cannot move another path's game draws. The placeholder config retains V2.1 seed `20260803` only as a controlled inherited seed; it does not approve any unresolved V3 calibration value.

## Mounted governed evidence

The harness mounts immutable copies of:

- canonical 134-entity grounding master: 121 governed FBS members + 13 schedule-only FCS opponents;
- unified 121-team preseason ratings;
- Schedule v5: 743 games = 736 regular + 7 CCG templates;
- Model Parameters v2.5 approved workbook;
- locked 14-team bracket regime;
- official playoff calendar;
- 134-team reconciliation/FCS operator artifact;
- V2.1 static 10,000-season Monte Carlo control workbook.

Every preflight emits SHA-256 input hashes. The V2.1 control reference copy is byte-identical to the workbook inside the supplied preseason/MC export (`39055662b819a3ff3e6e87ad53e28a15d0451a6b1e692e7770459e7a984c614a`).

## Current execution blockers

### Calibration placeholders — intentionally unresolved

- weekly performance-residual update coefficient;
- weekly movement cap;
- recent-form weighting;
- blowout treatment;
- game-SD value (`20.2` remains V2.1 evidence and Model Parameters marks current margin calibration OPEN);
- post-Week-5 sample-size regularization policy.

### Governance / data blockers

- V3 HFA baseline: V2.1 legacy engine records `4.0`, while current schedule/team-master governance records `3.5`; V3 does not silently choose either.
- Exact FCS Board-equivalent -> unified-points translation policy is not configured.
- The FCS reconciliation workbook explicitly records `Model use authorized = FALSE`, despite V2.1 referring to its R-FCS-RATING-01 construct; V3 requires an explicit authority resolution.
- Final committee strength tiebreak source is not governed for V3: preserve V2.1 preseason strength or use final weekly football strength.
- Ratified American/Athletic 8/8 division membership is referenced by Model Parameters, but the membership-row artifact is not mounted.
- Model Parameters leaves the five 13-game schedule exceptions (`ARK`, `GAST`, `UK`, `VAN`, `WVU`) OPEN pending resolution or explicit ratification.
- A8/ECL terminal tiebreak is defined as FINAL committee rank, while the final committee method can itself depend on conference-champion status; the deterministic ordering needed to avoid a circular dependency is not explicit.
- The locked bracket specifies generic quarterfinal pairings (`Seed 1 v W(R1)`, etc.) but does not map the four named Round-1 winners to bye seeds 1–4.

### Provenance blockers

The mounted Schedule v5 passes structural validation (743/736/7 and exact canonical IDs) but does not reproduce two governed hashes:

- certified Games-sheet SHA-256: `bd8089f70f6d483a75564e33438272c22daade8e53619fb21a915778975ff221`;
- reproduced Games-sheet SHA-256: `d52bf7c46822fc4acd631062d7c8292f5b2f627ea52ede71003b1a44f9861369`;
- governed binary SHA-256 in Model Parameters v2.5: `db26c3fff15a61ce8e7efa3b93100fa017e02248c96076d291495b55e855da12`;
- mounted raw workbook SHA-256: `b0f2c2cdbb3b47fa35bfcffdf4bd04850731355f3a8599a9494673ca9fcc24b8`.

These are retained as provenance anomalies. The harness does not rewrite Schedule v5 to force a match.

## Tiebreak / CFP scaffolding already implemented

- Current CCG chain scaffold: head-to-head -> mini round-robin -> terminal committee board.
- American carveout scaffold is division-winner vs division-winner but remains blocked until exact 8/8 membership rows are mounted.
- Atlantic-8/ECL are no-CCG standings champions; circular terminal-board ordering remains blocked.
- CG-8 supersession is enforced in tests: highest-ranked eligible G5 **conference champion**, not merely the highest-ranked G5 team.
- Notre Dame top-14 auto-bid and straight 1–14 seeding are scaffolded.
- Top four overall teams receive byes; play-ins are 11v14 and 12v13; Round 1 is 5v12, 6v11, 7v10, 8v9 after play-in replacement.
- Quarterfinal winner-to-bye mapping remains fail-closed.

The open ACC tied-set/restart proposal is not adopted; current governed rules remain the implemented scaffold.

## Required output schema after activation

Team summaries preserve each requested field separately:

- preseason strength;
- weekly strength trajectory (separate trajectory table/Parquet);
- average final strength;
- average regular-season wins;
- CCG appearance %;
- conference-title %;
- CFP %;
- CFP bye %;
- quarterfinal %;
- semifinal %;
- national-championship appearance %;
- national-championship win %;
- average final committee rank.

Conference output rows preserve team-level conference-title, CFP, title-game appearance, and national-title win probabilities, with explicit flags for each conference's favorite to reach the title game and favorite to win it.

## PowerShell launcher

From the repository root on Windows PowerShell:

```powershell
.\scripts\Invoke-SythalaxDynamicWeeklyMCV3.ps1 -Command validate
.\scripts\Invoke-SythalaxDynamicWeeklyMCV3.ps1 -Command show-blockers
.\scripts\Invoke-SythalaxDynamicWeeklyMCV3.ps1 -Command run
```

Optional overrides:

```powershell
.\scripts\Invoke-SythalaxDynamicWeeklyMCV3.ps1 `
  -Command validate `
  -ConfigPath .\config\dynamic_weekly_mc_v3\v3_experimental.json `
  -OutputRoot .\output\dynamic_weekly_mc_v3
```

`run` is expected to fail closed while blockers remain. A blocked run writes only `BLOCKED_<UTC>/BLOCKED.json`; no team/conference probabilities or final-looking V3 outputs are created.

## Run-specific output design after activation

- input/config manifest and hashes;
- preflight/validation receipt;
- team summary CSV/JSON;
- weekly strength trajectory CSV/Parquet;
- game-observation Parquet;
- path-level team/postseason state Parquet where enabled;
- conference summary CSV/JSON;
- V2.1-vs-V3 comparison CSV/JSON.

Large path-level data is designed for Parquet through the optional `mc` dependency (`pyarrow`); summaries remain CSV/JSON.
