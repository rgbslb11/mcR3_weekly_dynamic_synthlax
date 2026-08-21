"""Primary criterion and supporting diagnostics for the Baxter RMSE harness.

Ruling R2-CAL-OBJECTIVE makes out-of-sample Baxter Rating RMSE the primary
criterion and keeps Colley Matrix and SRS as independent witnesses. Everything
in this module is either that criterion or a diagnostic reported beside it;
nothing here blends the two, and :func:`..calibration.reject_witness_composite`
stands guard over anyone who tries.

Diagnostics are reported *where supported*. A diagnostic whose inputs the
mounted dataset does not carry returns an ``UNSUPPORTED`` record naming what was
missing, rather than a number standing in for evidence that is not there.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

from ..calibration import PRIMARY_CALIBRATION_METRIC
from ..errors import InputValidationError
from .model import Movement, Prediction

#: Probability clamp for log loss. A model that says 0 and is wrong should be
#: heavily penalised, not infinitely so; the bound is stated rather than implied.
PROBABILITY_EPSILON = 1e-12

#: Fixed, deterministic bin edges for the calibration curve.
CALIBRATION_BINS = 10

SUPPORTED = "SUPPORTED"
UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class Diagnostic:
    """One diagnostic, or a statement of why it could not be computed."""

    name: str
    status: str
    values: dict[str, Any] | None = None
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "values": None if self.values is None else dict(self.values),
            "reason": self.reason,
        }


def baxter_rating_rmse(predictions: Sequence[Prediction]) -> float:
    """The primary criterion: RMSE of rating-implied margin against observed margin."""
    if not predictions:
        raise InputValidationError(
            f"{PRIMARY_CALIBRATION_METRIC} is undefined over an empty prediction set."
        )
    return math.sqrt(
        math.fsum((p.predicted_margin - p.actual_margin) ** 2 for p in predictions)
        / len(predictions)
    )


def _mean(values: Sequence[float]) -> float:
    return math.fsum(values) / len(values)


def _quantile(sorted_values: Sequence[float], q: float) -> float:
    """Deterministic linear-interpolation quantile over a pre-sorted sequence."""
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = q * (len(sorted_values) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


def residual_diagnostic(predictions: Sequence[Prediction]) -> Diagnostic:
    """Residual shape, with the two-sided-rows caveat stated rather than left implicit.

    When an observation set carries both directed rows of each game, the residuals
    come in exact +/- pairs and their mean is structurally zero. That zero is an
    artefact of the row orientation, not evidence that the model is unbiased, so
    the diagnostic says which case it is looking at.
    """
    if not predictions:
        return Diagnostic("residuals", UNSUPPORTED, reason="no scored predictions")
    residuals = [p.actual_margin - p.predicted_margin for p in predictions]
    two_sided = len(predictions) == 2 * len({p.game_id for p in predictions})
    mean = _mean(residuals)
    ordered = sorted(residuals)
    variance = (
        math.fsum((r - mean) ** 2 for r in residuals) / (len(residuals) - 1)
        if len(residuals) > 1
        else 0.0
    )
    return Diagnostic(
        "residuals",
        SUPPORTED,
        {
            "count": len(residuals),
            "two_sided_rows": two_sided,
            "mean_bias_points": mean,
            "mean_bias_interpretable": not two_sided,
            "mean_bias_note": (
                "Both directed rows of each game are present, so residuals are exact +/- "
                "pairs and this mean is structurally zero. It is not a bias measurement."
                if two_sided
                else "Rows are one-sided, so the mean is a directional bias measurement."
            ),
            "mean_absolute_error_points": _mean([abs(r) for r in residuals]),
            "sd_points": math.sqrt(variance),
            "p05_points": _quantile(ordered, 0.05),
            "median_points": _quantile(ordered, 0.50),
            "p95_points": _quantile(ordered, 0.95),
            "max_absolute_points": max(abs(r) for r in residuals),
        },
    )


def movement_diagnostic(movements: Sequence[Movement]) -> Diagnostic:
    if not movements:
        return Diagnostic(
            "week_to_week_movement_distribution",
            UNSUPPORTED,
            reason="no weekly rating updates were applied",
        )
    magnitudes = sorted(abs(m.delta) for m in movements)
    binding = sum(1 for m in movements if m.cap_binding)
    return Diagnostic(
        "week_to_week_movement_distribution",
        SUPPORTED,
        {
            "updates": len(movements),
            "mean_absolute_move_points": _mean(magnitudes),
            "median_absolute_move_points": _quantile(magnitudes, 0.50),
            "p90_absolute_move_points": _quantile(magnitudes, 0.90),
            "max_absolute_move_points": magnitudes[-1],
            "cap_binding_rate": binding / len(movements),
            "mean_shrink_applied": _mean([m.shrink for m in movements]),
        },
    )


def stability_diagnostic(movements: Sequence[Movement]) -> Diagnostic:
    """How settled the rating state is, and whether it is still drifting."""
    if not movements:
        return Diagnostic(
            "rating_stability", UNSUPPORTED, reason="no weekly rating updates were applied"
        )
    by_week: dict[tuple[int, int], list[float]] = {}
    for movement in movements:
        by_week.setdefault((movement.season, movement.week), []).append(abs(movement.delta))
    ordered_weeks = sorted(by_week)
    weekly_means = [_mean(by_week[week]) for week in ordered_weeks]
    net_drift: dict[str, float] = {}
    for movement in movements:
        net_drift[movement.team] = net_drift.get(movement.team, 0.0) + movement.delta
    drifts = sorted(net_drift.values())
    first, last = weekly_means[0], weekly_means[-1]
    return Diagnostic(
        "rating_stability",
        SUPPORTED,
        {
            "weeks_with_updates": len(ordered_weeks),
            "mean_absolute_weekly_move_points": _mean(weekly_means),
            "first_week_mean_absolute_move_points": first,
            "last_week_mean_absolute_move_points": last,
            "settling_ratio": (last / first) if first > 0.0 else None,
            "mean_net_drift_points": _mean(drifts),
            "max_absolute_net_drift_points": max(abs(d) for d in drifts),
        },
    )


def _probability_pairs(
    predictions: Sequence[Prediction],
) -> tuple[list[tuple[float, float]], int]:
    pairs: list[tuple[float, float]] = []
    undetermined = 0
    for prediction in predictions:
        if prediction.actual_win is None:
            undetermined += 1
            continue
        pairs.append((prediction.win_probability, 1.0 if prediction.actual_win else 0.0))
    return pairs, undetermined


def brier_diagnostic(predictions: Sequence[Prediction]) -> Diagnostic:
    pairs, undetermined = _probability_pairs(predictions)
    if not pairs:
        return Diagnostic(
            "brier_score",
            UNSUPPORTED,
            reason="no observation carried a determinable win/loss outcome",
        )
    return Diagnostic(
        "brier_score",
        SUPPORTED,
        {
            "brier_score": _mean([(p - y) ** 2 for p, y in pairs]),
            "scored": len(pairs),
            "undetermined_outcomes_excluded": undetermined,
        },
    )


def log_loss_diagnostic(predictions: Sequence[Prediction]) -> Diagnostic:
    pairs, undetermined = _probability_pairs(predictions)
    if not pairs:
        return Diagnostic(
            "log_loss",
            UNSUPPORTED,
            reason="no observation carried a determinable win/loss outcome",
        )
    total = math.fsum(
        -(
            y * math.log(min(max(p, PROBABILITY_EPSILON), 1.0 - PROBABILITY_EPSILON))
            + (1.0 - y)
            * math.log(1.0 - min(max(p, PROBABILITY_EPSILON), 1.0 - PROBABILITY_EPSILON))
        )
        for p, y in pairs
    )
    return Diagnostic(
        "log_loss",
        SUPPORTED,
        {
            "log_loss": total / len(pairs),
            "scored": len(pairs),
            "probability_epsilon": PROBABILITY_EPSILON,
            "undetermined_outcomes_excluded": undetermined,
        },
    )


def calibration_diagnostic(predictions: Sequence[Prediction]) -> Diagnostic:
    pairs, undetermined = _probability_pairs(predictions)
    if not pairs:
        return Diagnostic(
            "probability_calibration",
            UNSUPPORTED,
            reason="no observation carried a determinable win/loss outcome",
        )
    bins: list[list[tuple[float, float]]] = [[] for _ in range(CALIBRATION_BINS)]
    for probability, outcome in pairs:
        index = min(int(probability * CALIBRATION_BINS), CALIBRATION_BINS - 1)
        bins[index].append((probability, outcome))
    rows = []
    expected_error = 0.0
    max_error = 0.0
    for index, bucket in enumerate(bins):
        if not bucket:
            rows.append(
                {
                    "bin": index,
                    "lower": index / CALIBRATION_BINS,
                    "upper": (index + 1) / CALIBRATION_BINS,
                    "count": 0,
                    "mean_predicted": None,
                    "observed_rate": None,
                    "gap": None,
                }
            )
            continue
        mean_predicted = _mean([p for p, _ in bucket])
        observed = _mean([y for _, y in bucket])
        gap = abs(mean_predicted - observed)
        expected_error += (len(bucket) / len(pairs)) * gap
        max_error = max(max_error, gap)
        rows.append(
            {
                "bin": index,
                "lower": index / CALIBRATION_BINS,
                "upper": (index + 1) / CALIBRATION_BINS,
                "count": len(bucket),
                "mean_predicted": mean_predicted,
                "observed_rate": observed,
                "gap": gap,
            }
        )
    return Diagnostic(
        "probability_calibration",
        SUPPORTED,
        {
            "expected_calibration_error": expected_error,
            "maximum_calibration_error": max_error,
            "bins": CALIBRATION_BINS,
            "scored": len(pairs),
            "undetermined_outcomes_excluded": undetermined,
            "curve": rows,
        },
    )


def blowout_sensitivity_diagnostic(
    predictions: Sequence[Prediction], threshold_points: float | None
) -> Diagnostic:
    """How much of the primary criterion is carried by lopsided games."""
    if threshold_points is None:
        return Diagnostic(
            "blowout_sensitivity",
            UNSUPPORTED,
            reason="regime blowout treatment is 'none', so it names no binding threshold",
        )
    if not predictions:
        return Diagnostic("blowout_sensitivity", UNSUPPORTED, reason="no scored predictions")
    blowouts = [p for p in predictions if abs(p.actual_margin) >= threshold_points]
    ordinary = [p for p in predictions if abs(p.actual_margin) < threshold_points]
    overall = baxter_rating_rmse(predictions)
    return Diagnostic(
        "blowout_sensitivity",
        SUPPORTED,
        {
            "threshold_points": threshold_points,
            "blowout_share": len(blowouts) / len(predictions),
            "rmse_all": overall,
            "rmse_blowouts_only": baxter_rating_rmse(blowouts) if blowouts else None,
            "rmse_excluding_blowouts": baxter_rating_rmse(ordinary) if ordinary else None,
            "rmse_delta_excluding_blowouts": (
                baxter_rating_rmse(ordinary) - overall if ordinary else None
            ),
        },
    )


def baseline_comparison(predictions: Sequence[Prediction]) -> dict[str, Any]:
    """Compare against the mounted source model's own ``expected_margin``.

    This is a comparison against whatever prediction the observation set carries,
    which is not the V2.1 static control workbook. The record says so explicitly
    so the two are never read as the same comparison.
    """
    paired = [p for p in predictions if p.baseline_expected_margin is not None]
    if not paired:
        return {
            "status": UNSUPPORTED,
            "reason": "observation set carries no expected_margin column",
            "v2_1_control_workbook_mounted": False,
        }
    baseline_rmse = math.sqrt(
        math.fsum((p.baseline_expected_margin - p.actual_margin) ** 2 for p in paired)
        / len(paired)
    )
    harness_rmse = baxter_rating_rmse(paired)
    return {
        "status": SUPPORTED,
        "baseline_source": "observation_set.expected_margin",
        "baseline_rmse": baseline_rmse,
        "harness_rmse_on_same_rows": harness_rmse,
        "delta_vs_baseline": harness_rmse - baseline_rmse,
        "scored": len(paired),
        "v2_1_control_workbook_mounted": False,
    }


def diagnostics_for(
    predictions: Sequence[Prediction],
    movements: Sequence[Movement],
    *,
    blowout_threshold_points: float | None,
) -> list[Diagnostic]:
    """Every supporting diagnostic, in a fixed order, reported where supported."""
    return [
        residual_diagnostic(predictions),
        movement_diagnostic(movements),
        stability_diagnostic(movements),
        brier_diagnostic(predictions),
        log_loss_diagnostic(predictions),
        calibration_diagnostic(predictions),
        blowout_sensitivity_diagnostic(predictions, blowout_threshold_points),
    ]


def flat_metrics(
    predictions: Sequence[Prediction], diagnostics: Sequence[Diagnostic]
) -> dict[str, float]:
    """Flat scalar metrics, keyed for :class:`~..calibration.ExperimentRecord`.

    The primary criterion is always present under its governed name. Diagnostic
    scalars appear only when their diagnostic was supported.
    """
    out: dict[str, float] = {PRIMARY_CALIBRATION_METRIC: baxter_rating_rmse(predictions)}
    by_name = {d.name: d for d in diagnostics}

    def add(diagnostic_name: str, key: str, metric_name: str) -> None:
        diagnostic = by_name.get(diagnostic_name)
        if diagnostic is None or diagnostic.status != SUPPORTED or diagnostic.values is None:
            return
        value = diagnostic.values.get(key)
        if isinstance(value, (int, float)):
            out[metric_name] = float(value)

    add("residuals", "mean_absolute_error_points", "residual_mae_points")
    residual = by_name.get("residuals")
    if (
        residual is not None
        and residual.status == SUPPORTED
        and residual.values is not None
        and residual.values.get("mean_bias_interpretable")
    ):
        out["residual_bias_points"] = float(residual.values["mean_bias_points"])
    add("brier_score", "brier_score", "brier_score")
    add("log_loss", "log_loss", "log_loss")
    add("probability_calibration", "expected_calibration_error", "expected_calibration_error")
    add("week_to_week_movement_distribution", "p90_absolute_move_points", "movement_p90_points")
    add("week_to_week_movement_distribution", "cap_binding_rate", "movement_cap_binding_rate")
    add("rating_stability", "mean_absolute_weekly_move_points", "stability_mean_weekly_move")
    add("blowout_sensitivity", "rmse_delta_excluding_blowouts", "blowout_rmse_delta")
    return out
