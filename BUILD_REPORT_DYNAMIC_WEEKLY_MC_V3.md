# OPERATION SYTHALAX — Dynamic Weekly MC V3 Build Report

Build: `SYTHALAX_DYNAMIC_WEEKLY_MC_V3_EXPERIMENTAL`  
Model version: `3.0.0-experimental-harness`  
Configuration version: `V3-PLACEHOLDER-2026-08-20-001`  
Disposition: **STRUCTURALLY VALID HARNESS — EXECUTION BLOCKED**

## FACT

- V2.1 static control is preserved unchanged. SHA-256 of both the original ZIP member and V3 reference copy: `39055662b819a3ff3e6e87ad53e28a15d0451a6b1e692e7770459e7a984c614a`.
- Canonical identity input resolves exactly 134 entities: 121 `FBS_MEMBER` + 13 `SCHEDULE_ONLY_FCS`.
- Schedule v5 structurally resolves exactly 743 games: 736 `REG` + 7 `CCG` templates.
- Pre-selection Weeks 1–14 contain 735 regular games; Week 15 contains 7 CCG templates; Week 16 contains exactly one regular game, Army–Navy `G0736`.
- V2.1 control metadata records 10,000 paths, seed `20260803`, HFA `4.0`, and game SD `20.2`.
- Model Parameters v2.5 records schedule/team-master HFA baseline `3.5` and marks margin-SD calibration `OPEN`.
- Model Parameters v2.5 leaves five 13-game schedules OPEN: `ARK`, `GAST`, `UK`, `VAN`, `WVU`.
- FCS reconciliation records R-FCS-RATING-01 but also records `Model use authorized = FALSE`.
- The locked bracket and playoff calendar do not provide an explicit mapping from each Round-1 winner to bye seeds 1–4.
- The ratified American/Athletic division source is referenced but its 8/8 membership rows are not mounted.
- Schedule structural content is usable for preflight, but its current binary/content hashes do not match the governed/certified hashes recorded in the evidence set.
- Repository-wide test suite passes: **74 tests**.
- The Python CLI `validate` exits 0 and writes preflight + input manifest; `show-blockers` exits 0 and enumerates blockers; `run` exits 2 and writes only a blocked receipt.

## DERIVED

- W1 audit-only rerating plus first W2 promotion is enforced without contaminating Week 2 opening strength.
- The initial post-selection phase must freeze football strength for Army–Navy and CFP games because Selection Day occurs before W16 and the user explicitly requires frozen playoff strength after CCG/selection.
- A8/ECL's final-board tiebreak needs an explicit computation order because using conference-champion status inside the final committee board can otherwise create a circular dependency when the champion itself is being selected by that board.
- The current V3 package is suitable for coefficient experiments and deterministic fixture tests, but not for canonical 10,000-path probability production.

## ASSUMPTION

- None of the unresolved numeric calibration values have been assumed.
- Seed `20260803` is retained only as the inherited deterministic-control seed, not as a promoted V3 calibration parameter.
- No quarterfinal pairing rule, AAC membership row, FCS translation, HFA value, or committee-strength tiebreak source has been inferred.

## BLOCKED

Production `run` remains blocked on the following explicit gates:

1. `calibration.weekly_performance_residual_coefficient`
2. `calibration.weekly_movement_cap_points`
3. `calibration.recent_form_weights`
4. `calibration.blowout_treatment`
5. `calibration.game_sd_points`
6. `calibration.sample_size_regularization`
7. `hfa_baseline_points`
8. `fcs_translation_policy`
9. `committee_tiebreak_strength_source`
10. `inputs.aac_divisions_csv`
11. `provenance.SCHEDULE_GAMES_HASH_REPRODUCTION_MISMATCH`
12. `provenance.SCHEDULE_BINARY_HASH_MISMATCH_VS_MODEL_PARAMETERS_V2_5`
13. `governance.V3_HFA_BASELINE_CONFLICT_4P0_VS_3P5`
14. `governance.GAME_SD_CALIBRATION_OPEN`
15. `governance.FIVE_13_GAME_SCHEDULE_EXCEPTIONS_UNRATIFIED`
16. `governance.FCS_SOURCE_MODEL_USE_AUTHORIZED_FALSE`
17. `governance.POSTSEASON_QUARTERFINAL_MAPPING_NOT_EXPLICIT`
18. `governance.A8_ECL_FINAL_BOARD_TIEBREAK_ORDERING_NOT_EXPLICIT`

No final-looking team probabilities, conference probabilities, or postseason probabilities were generated.
