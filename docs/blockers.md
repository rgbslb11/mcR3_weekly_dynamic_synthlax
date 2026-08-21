# Explicit v0 Blockers

## BLOCKED-001: Independent power model

**Missing:** independent 2026 team ratings and calibrated home-field/roster adjustment pipeline.

`feature_flags.independent_power_model = false`

## BLOCKED-002: Current sharp selections

The supplied four detailed capper profiles contained **no pending picks**. Historical performance does not create a current selection.

## BLOCKED-003: Sharp probability calibration

**Missing:** evidence-backed mapping from market-specific weighted capper consensus to a fair-probability delta.

`feature_flags.sharp_belief_adjustment = false`

## BLOCKED-004: Historical line movement

**Missing:** timestamped historical spread/total changes.

## BLOCKED-005: Multi-book pricing

**Missing:** sportsbook-specific strike/price dispersion.

## BLOCKED-006: Authoritative public-money source timestamp

Use ingest time as `observed_at`; do not invent `source_snapshot_at`.
