"""Monte Carlo convergence diagnostics derived from the runs themselves.

R1 compared two tiers against predeclared absolute tolerances and stopped for a
human wherever a tolerance was missing. That was a defensible way to avoid
choosing a tolerance after seeing the divergence, and it was also a second human
stop in a run whose whole design has exactly one. The fix is not a looser
tolerance -- it is not needing one. Two Monte Carlo estimates of the same
quantity disagree by a knowable amount, and the amount is computable from the
estimates and the path counts, so "is this disagreement larger than sampling
explains" is a question with an answer rather than a number somebody has to pick.

The uncertainty model
---------------------

For a quantity that is a probability estimated as the fraction of paths in which
an event occurred, the sampling standard error at ``N`` independent paths is::

    SE(p, N) = sqrt(p * (1 - p) / N)

and two independent runs differ with standard error::

    SE_delta = sqrt(SE_1^2 + SE_2^2)

so ``z = |p_2 - p_1| / SE_delta`` is a standardised divergence: how many
sampling standard errors apart the two runs landed. This is used because the V3
tier design makes it true -- the tiers draw the same distribution and differ only
in how many independent paths they draw, so the two estimates are independent
estimates of one quantity.

**Not every reported number is a Bernoulli probability.** An expected win total
is a mean, and its variance is a property of the outcome distribution rather
than of ``p(1-p)``. Where the run reports an empirical standard error for such a
quantity, it is used directly. Where it does not, the quantity is classified
:data:`NOT_DIAGNOSED_NO_VARIANCE_MODEL` and reported as such. It is not passed,
it is not failed, and no variance is invented for it -- a fabricated ``SE`` would
produce a confident diagnosis of a quantity nobody measured the spread of.

Thresholds, declared here rather than chosen later
---------------------------------------------------

:data:`FAMILY_WISE_ALPHA` is the false-alarm budget for the predeclared headline
family, ``0.01``, spent across that family by the Sidak correction in
:func:`family_wise_z`. At the usual family size this lands near ``z = 3.1``.

:data:`OUTLIER_Z` is ``3.0``: the per-output flag for the wide family. Under the
null it fires on about ``0.27%`` of outputs by construction, which is why a
single flag is not a failure.

:data:`CATASTROPHIC_Z` is ``6.0``: a single output this far out is not sampling.
At a family size in the hundreds the expected number of ``6-sigma`` events is
below ``10^-6``, so one is evidence about the model rather than about the dice.

Many outputs, one gate
-----------------------

A season report carries hundreds of team-level probabilities. Testing each at
``z = 3`` and failing on any breach would fail a healthy run most of the time --
with 300 outputs, the chance of at least one 3-sigma flag under the null is
about ``56%``. The policy implemented here is therefore three rules at once:

1. **Predeclared headline subset**, tested at a family-wise-corrected threshold.
   Any breach fails. This is the small set whose movement means something.
2. **Proportion-of-outliers over the whole diagnosed family.** Count outputs
   past :data:`OUTLIER_Z`, and fail only when that count is larger than the
   binomial upper tail at :data:`OUTLIER_PROPORTION_ALPHA` allows. One flag in
   three hundred is expected; forty is systematic.
3. **Catastrophic single-output threshold.** Any output past
   :data:`CATASTROPHIC_Z` fails regardless of how few there are.

Outliers are never hidden. Every flagged output appears in the diagnostic
detail with its ``z``, whether or not it changed the verdict, so "passed with
advisory" is a readable claim rather than a shrug.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import NormalDist
from typing import Any, Iterable, Mapping

from ..errors import InputValidationError

__all__ = [
    "BERNOULLI_PROBABILITY",
    "CATASTROPHIC_DIVERGENCE",
    "CATASTROPHIC_Z",
    "ConvergencePolicy",
    "DEGENERATE_ZERO_VARIANCE",
    "FAMILY_WISE_ALPHA",
    "FAMILY_WISE_BREACH",
    "NOT_COMPARABLE_SINGLE_TIER",
    "NOT_DIAGNOSED_NO_VARIANCE_MODEL",
    "OUTLIER_PROPORTION_ALPHA",
    "OUTLIER_WITHIN_EXPECTED_RATE",
    "OUTLIER_Z",
    "Quantity",
    "RUN_LEVEL_MEAN",
    "TierSample",
    "UNSPECIFIED_QUANTITY",
    "WITHIN_MONTE_CARLO_NOISE",
    "binomial_se",
    "diagnose",
    "family_wise_z",
    "sample_from_report",
    "se_delta",
]

# --- quantity kinds ----------------------------------------------------------

#: A probability estimated as the fraction of paths in which an event occurred.
#: The only kind for which a binomial standard error is mathematically correct.
BERNOULLI_PROBABILITY = "BERNOULLI_PROBABILITY"

#: A mean over paths. Diagnosable only where the run reports its empirical
#: standard error, because its variance is not a function of its value.
RUN_LEVEL_MEAN = "RUN_LEVEL_MEAN"

#: The run reported a number and did not say what kind of number it is.
UNSPECIFIED_QUANTITY = "UNSPECIFIED_QUANTITY"

_KINDS: tuple[str, ...] = (BERNOULLI_PROBABILITY, RUN_LEVEL_MEAN, UNSPECIFIED_QUANTITY)


# --- classifications ---------------------------------------------------------

#: The two runs agree to within what sampling explains.
WITHIN_MONTE_CARLO_NOISE = "WITHIN_MONTE_CARLO_NOISE"

#: Past the per-output flag, and inside the rate that flag fires at by chance.
OUTLIER_WITHIN_EXPECTED_RATE = "OUTLIER_WITHIN_EXPECTED_RATE"

#: A predeclared headline quantity past its family-wise threshold.
FAMILY_WISE_BREACH = "FAMILY_WISE_BREACH"

#: A single output too far out to be sampling at any plausible family size.
CATASTROPHIC_DIVERGENCE = "CATASTROPHIC_DIVERGENCE"

#: No variance model applies and the run supplied no empirical standard error.
NOT_DIAGNOSED_NO_VARIANCE_MODEL = "NOT_DIAGNOSED_NO_VARIANCE_MODEL"

#: Reported by one tier only.
NOT_COMPARABLE_SINGLE_TIER = "NOT_COMPARABLE_SINGLE_TIER"

#: Both estimates sit on a boundary with zero estimated variance and still
#: differ. Sampling cannot produce that, so it is treated as catastrophic.
DEGENERATE_ZERO_VARIANCE = "DEGENERATE_ZERO_VARIANCE"


# --- declared thresholds -----------------------------------------------------

#: False-alarm budget for the predeclared headline family, spent across it.
FAMILY_WISE_ALPHA = 0.01

#: Per-output flag for the wide family. Two-sided; fires on ~0.27% by chance.
OUTLIER_Z = 3.0

#: A single output past this is evidence about the model, not about the dice.
CATASTROPHIC_Z = 6.0

#: How improbable the observed outlier count must be before the proportion rule
#: calls the divergence systematic.
OUTLIER_PROPORTION_ALPHA = 0.001

_NORMAL = NormalDist()

#: The rate at which :data:`OUTLIER_Z` fires under the null, two-sided.
EXPECTED_OUTLIER_RATE = 2.0 * (1.0 - _NORMAL.cdf(OUTLIER_Z))


def binomial_se(p: float, n: int) -> float:
    """``sqrt(p * (1 - p) / n)`` -- the sampling SE of a path-fraction estimate."""
    if n <= 0:
        raise InputValidationError(
            f"A standard error needs a path count; got {n!r}. A tier that reports no "
            "paths reports no precision either."
        )
    if not 0.0 <= p <= 1.0:
        raise InputValidationError(
            f"{p!r} is outside [0, 1] and cannot be a Bernoulli path fraction."
        )
    return math.sqrt(p * (1.0 - p) / n)


def se_delta(se_a: float, se_b: float) -> float:
    """SE of the difference between two independent estimates."""
    return math.sqrt(se_a * se_a + se_b * se_b)


def family_wise_z(family_size: int, alpha: float = FAMILY_WISE_ALPHA) -> float:
    """Two-sided ``z`` controlling ``alpha`` across a family of ``family_size``.

    Sidak rather than Bonferroni: for independent tests it is exact rather than
    conservative, and the headline quantities are close enough to independent
    that the difference is real. Both are the same to two decimal places at
    these family sizes; the choice is recorded so the number is reproducible.
    """
    if family_size <= 0:
        raise InputValidationError("A family-wise threshold needs a non-empty family.")
    per_comparison = 1.0 - (1.0 - alpha) ** (1.0 / family_size)
    return _NORMAL.inv_cdf(1.0 - per_comparison / 2.0)


def _binomial_upper_tail(k: int, n: int, p: float) -> float:
    """``P(X >= k)`` for ``X ~ Binomial(n, p)``, summed from the lower end.

    Summed over ``j < k`` rather than ``j >= k`` because ``k`` is small whenever
    the answer matters -- a healthy run has a handful of outliers out of
    hundreds -- and the lower sum is then a few terms rather than hundreds.
    """
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0
    term = (1.0 - p) ** n
    cdf = term
    ratio = p / (1.0 - p)
    for j in range(1, k):
        term *= (n - j + 1) / j * ratio
        cdf += term
    return max(0.0, min(1.0, 1.0 - cdf))


@dataclass(frozen=True)
class Quantity:
    """One reported output, with what is known about its precision."""

    name: str
    value: float
    kind: str = UNSPECIFIED_QUANTITY
    paths: int = 0
    standard_error: float | None = None

    def __post_init__(self) -> None:
        if self.kind not in _KINDS:
            raise InputValidationError(
                f"Quantity {self.name} declares unknown kind {self.kind!r}; expected "
                f"one of {list(_KINDS)}."
            )

    def sampling_se(self) -> float | None:
        """The standard error to diagnose with, or ``None`` if there is none.

        An explicitly reported empirical SE wins over the binomial model even
        for a Bernoulli quantity: the run measured the spread and the model only
        predicts it.
        """
        if self.standard_error is not None:
            return float(self.standard_error)
        if self.kind == BERNOULLI_PROBABILITY:
            return binomial_se(float(self.value), self.paths)
        return None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "kind": self.kind,
            "paths": self.paths,
            "standard_error": self.standard_error,
        }


@dataclass(frozen=True)
class TierSample:
    """What one tier reported, and how many paths produced it."""

    tier: str
    paths: int
    quantities: dict[str, Quantity] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier,
            "paths": self.paths,
            "quantities": {
                name: q.as_dict() for name, q in sorted(self.quantities.items())
            },
        }


def sample_from_report(report: Mapping[str, Any], *, tier: str, paths: int) -> TierSample:
    """Read a tier report into a comparable sample.

    Two shapes are accepted. ``quantities`` is the R2 contract and says what each
    number is; ``aggregates`` is the R1 shape and does not, so its entries are
    :data:`UNSPECIFIED_QUANTITY` and are diagnosed only if they arrive with an
    explicit standard error. That asymmetry is the point: a run that wants its
    aggregates diagnosed says what they are.
    """
    quantities: dict[str, Quantity] = {}
    observed = int(report.get("observed_paths") or paths)
    for name, value in sorted(dict(report.get("aggregates") or {}).items()):
        quantities[str(name)] = Quantity(
            name=str(name),
            value=float(value),
            kind=UNSPECIFIED_QUANTITY,
            paths=observed,
        )
    for name, entry in sorted(dict(report.get("quantities") or {}).items()):
        if isinstance(entry, Mapping):
            se = entry.get("standard_error")
            quantities[str(name)] = Quantity(
                name=str(name),
                value=float(entry["value"]),
                kind=str(entry.get("kind", UNSPECIFIED_QUANTITY)),
                paths=int(entry.get("paths", observed)),
                standard_error=None if se is None else float(se),
            )
        else:
            quantities[str(name)] = Quantity(
                name=str(name),
                value=float(entry),
                kind=UNSPECIFIED_QUANTITY,
                paths=observed,
            )
    return TierSample(tier=tier, paths=observed, quantities=quantities)


@dataclass(frozen=True)
class ConvergencePolicy:
    """The declared diagnostic policy, as one object a report can quote.

    Predeclaring the headline subset is the only judgement in the whole
    diagnostic, and it is a judgement about *which quantities matter*, not about
    how much divergence is acceptable. That distinction is what keeps this from
    being a tolerance chosen after the fact: the thresholds are derived from the
    samples, and the only thing configuration supplies is the list of names.
    """

    headline: tuple[str, ...] = ()
    family_wise_alpha: float = FAMILY_WISE_ALPHA
    outlier_z: float = OUTLIER_Z
    catastrophic_z: float = CATASTROPHIC_Z
    outlier_proportion_alpha: float = OUTLIER_PROPORTION_ALPHA

    def as_dict(self) -> dict[str, Any]:
        return {
            "method": "MONTE_CARLO_SAMPLING_STANDARD_ERROR",
            "headline_subset": list(self.headline),
            "family_wise_alpha": self.family_wise_alpha,
            "family_wise_correction": "SIDAK",
            "outlier_z": self.outlier_z,
            "catastrophic_z": self.catastrophic_z,
            "outlier_proportion_alpha": self.outlier_proportion_alpha,
            "expected_outlier_rate": EXPECTED_OUTLIER_RATE,
            "multiple_comparison_policy": (
                "PREDECLARED_HEADLINE_FAMILY_WISE + PROPORTION_OF_OUTLIERS + "
                "CATASTROPHIC_SINGLE_OUTPUT"
            ),
        }


def _compare_one(
    name: str,
    baseline: Quantity | None,
    candidate: Quantity | None,
) -> dict[str, Any]:
    if baseline is None or candidate is None:
        return {
            "name": name,
            "baseline": None if baseline is None else baseline.value,
            "candidate": None if candidate is None else candidate.value,
            "classification": NOT_COMPARABLE_SINGLE_TIER,
            "detail": "Reported by only one tier, so there is nothing to compare it to.",
        }
    se_base = baseline.sampling_se()
    se_cand = candidate.sampling_se()
    delta = float(candidate.value) - float(baseline.value)
    row: dict[str, Any] = {
        "name": name,
        "kind": candidate.kind,
        "baseline": baseline.value,
        "candidate": candidate.value,
        "baseline_paths": baseline.paths,
        "candidate_paths": candidate.paths,
        "delta": delta,
        "baseline_se": se_base,
        "candidate_se": se_cand,
    }
    if se_base is None or se_cand is None:
        row["classification"] = NOT_DIAGNOSED_NO_VARIANCE_MODEL
        row["detail"] = (
            f"{name} is {candidate.kind} and the run reported no empirical standard "
            "error for it. A binomial standard error is not mathematically appropriate "
            "here, and no variance is invented, so the quantity is recorded "
            "undiagnosed rather than passed."
        )
        return row
    combined = se_delta(se_base, se_cand)
    row["se_delta"] = combined
    if combined == 0.0:
        if delta == 0.0:
            row["z"] = 0.0
            row["classification"] = WITHIN_MONTE_CARLO_NOISE
            row["detail"] = "Both tiers report the same degenerate value."
        else:
            row["z"] = math.inf
            row["classification"] = DEGENERATE_ZERO_VARIANCE
            row["detail"] = (
                "Both estimates sit on a probability boundary with zero estimated "
                f"variance and still differ by {delta}. Sampling cannot produce that."
            )
        return row
    row["z"] = abs(delta) / combined
    return row


def diagnose(
    baseline: TierSample,
    candidate: TierSample,
    *,
    policy: ConvergencePolicy | None = None,
) -> dict[str, Any]:
    """Compare two tiers and classify the result PASS / advisory / FAIL.

    Returns the full comparison table alongside the verdict. Every outlier is in
    the table with its ``z`` whether or not it changed the verdict, because a
    diagnostic that suppressed the outliers it forgave would be reporting a
    cleaner run than the one that happened.
    """
    policy = policy or ConvergencePolicy()
    names = sorted(set(baseline.quantities) | set(candidate.quantities))
    rows = [
        _compare_one(name, baseline.quantities.get(name), candidate.quantities.get(name))
        for name in names
    ]

    diagnosed = [r for r in rows if "z" in r]
    undiagnosed = [
        r["name"]
        for r in rows
        if r.get("classification") == NOT_DIAGNOSED_NO_VARIANCE_MODEL
    ]
    incomparable = [
        r["name"] for r in rows if r.get("classification") == NOT_COMPARABLE_SINGLE_TIER
    ]

    # 1. Predeclared headline subset at a family-wise threshold.
    headline_rows = [r for r in diagnosed if r["name"] in set(policy.headline)]
    headline_z = (
        family_wise_z(len(headline_rows), policy.family_wise_alpha) if headline_rows else None
    )
    headline_breaches = [
        r["name"] for r in headline_rows if headline_z is not None and r["z"] > headline_z
    ]
    headline_missing = sorted(set(policy.headline) - {r["name"] for r in diagnosed})

    # 3. Catastrophic single output, evaluated before the proportion rule so a
    #    lone pathological output cannot be averaged into acceptability.
    catastrophic = [r["name"] for r in diagnosed if r["z"] >= policy.catastrophic_z]

    # 2. Proportion of outliers across the whole diagnosed family.
    outliers = [r for r in diagnosed if r["z"] > policy.outlier_z]
    family_size = len(diagnosed)
    observed_rate = (len(outliers) / family_size) if family_size else 0.0
    tail = _binomial_upper_tail(len(outliers), family_size, EXPECTED_OUTLIER_RATE)
    proportion_exceeded = bool(family_size) and tail < policy.outlier_proportion_alpha

    for row in diagnosed:
        if row["name"] in catastrophic:
            row["classification"] = CATASTROPHIC_DIVERGENCE
        elif row["name"] in headline_breaches:
            row["classification"] = FAMILY_WISE_BREACH
        elif row["z"] > policy.outlier_z:
            row["classification"] = OUTLIER_WITHIN_EXPECTED_RATE
        else:
            row.setdefault("classification", WITHIN_MONTE_CARLO_NOISE)

    reasons: list[str] = []
    advisories: list[str] = []
    if catastrophic:
        reasons.append(
            f"Outputs past the declared catastrophic threshold z>={policy.catastrophic_z}: "
            f"{catastrophic}. A single output that far out is not sampling."
        )
    if headline_breaches:
        reasons.append(
            f"Predeclared headline outputs past the family-wise threshold "
            f"z>{headline_z:.3f} (Sidak, alpha={policy.family_wise_alpha}, family of "
            f"{len(headline_rows)}): {headline_breaches}."
        )
    if proportion_exceeded:
        reasons.append(
            f"{len(outliers)} of {family_size} diagnosed outputs exceed z>{policy.outlier_z}. "
            f"Under sampling alone the expected rate is {EXPECTED_OUTLIER_RATE:.4f} and "
            f"P(X >= {len(outliers)}) = {tail:.3e}, below the declared "
            f"{policy.outlier_proportion_alpha}. The divergence is systematic rather "
            "than a run of unlucky outputs."
        )
    if headline_missing:
        reasons.append(
            f"Predeclared headline outputs were not diagnosable: {headline_missing}. A "
            "headline quantity that cannot be compared is not a quantity that passed."
        )
    if outliers and not proportion_exceeded and not catastrophic:
        advisories.append(
            f"{len(outliers)} of {family_size} outputs exceed z>{policy.outlier_z}, within "
            f"the {EXPECTED_OUTLIER_RATE:.4f} rate that threshold fires at by chance "
            f"(P(X >= {len(outliers)}) = {tail:.3f}). Flagged, not hidden: "
            f"{[r['name'] for r in outliers]}."
        )
    if undiagnosed:
        advisories.append(
            f"Not diagnosed for want of a variance model or a reported standard error: "
            f"{undiagnosed}. No variance was invented for them."
        )
    if incomparable:
        advisories.append(f"Reported by one tier only, so not compared: {incomparable}.")
    if not family_size:
        advisories.append(
            "No quantity was diagnosable, so this comparison proves nothing about "
            "convergence."
        )

    classification = "FAIL" if reasons else ("PASS_WITH_ADVISORY" if advisories else "PASS")
    return {
        "classification": classification,
        "policy": policy.as_dict(),
        "baseline_tier": baseline.tier,
        "candidate_tier": candidate.tier,
        "baseline_paths": baseline.paths,
        "candidate_paths": candidate.paths,
        "comparisons": rows,
        "diagnosed_count": family_size,
        "headline": {
            "declared": list(policy.headline),
            "diagnosed": [r["name"] for r in headline_rows],
            "not_diagnosable": headline_missing,
            "threshold_z": headline_z,
            "breaches": headline_breaches,
        },
        "wide_family": {
            "size": family_size,
            "outlier_z": policy.outlier_z,
            "outliers": [{"name": r["name"], "z": r["z"]} for r in outliers],
            "expected_rate": EXPECTED_OUTLIER_RATE,
            "observed_rate": observed_rate,
            "upper_tail_probability": tail,
            "exceeds_expected_rate": proportion_exceeded,
        },
        "catastrophic": {"threshold_z": policy.catastrophic_z, "breaches": catastrophic},
        "not_diagnosed": undiagnosed,
        "not_comparable": incomparable,
        "reasons": reasons,
        "advisories": advisories,
    }


def policy_from_names(names: Iterable[str]) -> ConvergencePolicy:
    """Build a policy from a predeclared headline list."""
    return ConvergencePolicy(headline=tuple(str(n) for n in names))
