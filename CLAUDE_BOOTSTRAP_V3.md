# OPERATION SYTHALAX — V3 TESTED BASELINE BOOTSTRAP

Repository: `rgbslb11/mcR3_weekly_dynamic_synthlax`

You are the implementation agent. Deterministic software and tests are authoritative. Do not invent missing data, coefficients, ratings, mappings, tiebreak rules, postseason rules, or governance decisions. Do not modify `main` directly. Do not merge.

The bootstrap branch contains:
`SYTHALAX_DYNAMIC_WEEKLY_MC_V3_EXPERIMENTAL_BUILD.zip`

Required SHA-256:
`e62f4497fa02196b9755932d616d7fb69bfc0b3ebdba6d90c87e83be4dbc6ca0`

Previously validated Windows baseline:
- Python 3.12.3
- full repository suite: 74 passed
- V3-specific suite: 15 passed
- pip dependency check: clean

## Objective

Publish the exact tested V3 baseline as a governed feature-branch pull request against `main`.

## Procedure

1. Inspect repository state, base branch, remotes, and archive.
2. Verify the ZIP SHA-256 exactly. If it differs, STOP and return BLOCKED.
3. Extract the archive to a temporary directory.
4. Copy `ncaaf_synthetic_market_engine_v0/` contents into the repository root.
5. Exclude `.venv/`, `output/`, `__pycache__/`, `.pytest_cache/`, `.vscode/`.
6. Ensure `.gitignore` protects those paths.
7. Do not retain the bootstrap ZIP in the final proposed tree.
8. Install with `python -m pip install -e ".[test,mc]"`.
9. Run `python -m pip check`.
10. Run `python -m pytest`.
11. Run `python -m pytest tests/dynamic_weekly_mc_v3 -v`.
12. Require zero failures.
13. Run `git diff --check`.
14. Inspect every changed path before committing.
15. Do not use broad staging that silently captures unrelated files.
16. Preferred branch: `experiment/dynamic-weekly-mc-v3`. If the cloud agent requires another branch, report it exactly.
17. Commit: `Publish tested Dynamic Weekly MC V3 experimental baseline`.
18. Push the feature branch.
19. Open a DRAFT pull request against `main`.
20. Do not merge.

## Governance

- Preserve V2.1 unchanged.
- V3 remains EXPERIMENTAL.
- Do not populate unresolved calibration values.
- Do not promote coefficients.
- Do not invent FCS translation policy.
- Do not resolve HFA 4.0 vs 3.5 by inference.
- Do not invent AAC division rows.
- Do not invent committee final-strength tiebreak source.
- Do not invent quarterfinal R1-winner mapping.
- Do not resolve A8/ECL ordering circularity by inference.
- Do not emit final-looking V3 probabilities while validation/governance is blocked.
- A BLOCKED production run is acceptable and expected while governed inputs remain unresolved.

## Final report

Return FACT / DERIVED / ASSUMPTION / BLOCKED, including:
- branch
- commit SHA
- changed-file count
- full test result
- V3 test result
- pip check result
- git diff --check
- working-tree state
- draft PR URL
- archive SHA verification

If any prerequisite, hash, test, or integrity check fails, STOP and return BLOCKED with evidence.
