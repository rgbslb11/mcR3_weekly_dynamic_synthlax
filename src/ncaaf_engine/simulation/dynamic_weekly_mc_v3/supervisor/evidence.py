"""The frozen synthetic-evidence manifest, and what it permits.

The supervisor never decides what may be fitted. It reads that decision out of
a frozen manifest and then refuses everything the manifest does not permit. This
module is that manifest's schema, loader and gate.

Governing doctrine, encoded rather than described
-------------------------------------------------

The production domain is synthetic 2024 and synthetic 2025 estimating synthetic
2026. Real 2021-2024 football is external witness only: it may diagnose
plausibility and it may never move the selected parameter vector. Both halves
are enforced here at load time --
:func:`require_synthetic_only_primary_estimation_domain` refuses a manifest
whose estimation domain names a real season at all, and the real corpus is
admitted only under :data:`EXTERNAL_WITNESS_ONLY`. A manifest that tried to pool
them does not load, so no later stage has to remember not to.

The naming checks here are the *second* line, not the first
------------------------------------------------------------

:data:`_REAL_SEASON_PATTERNS` matches season labels, and a label is a string
somebody chose. That makes these checks defence in depth and nothing more:
:data:`FILENAME_CHECKS_ROLE` says so, and the authoritative primary-domain gate
is :mod:`.domain_manifest`, which classifies a source by the SHA-256 of its
bytes and therefore cannot be defeated by renaming anything. The two run
together and the manifest runs first; these patterns can only add a refusal the
manifest did not already make. Keeping them is worth the duplication -- a
mislabelled season inside an otherwise well-formed manifest is a real mistake
and this catches it -- but nothing here is load-bearing on its own.

Circularity is the second half of the doctrine and the easier one to get wrong.
A synthetic 2024/2025 field that was produced by the same mechanism a parameter
governs is not independent evidence about that parameter: fitting to it recovers
the generator's own setting and reports it as a measurement. So every parameter
must declare the circularity class of the evidence behind it, and
:data:`GENERATED_BY_MECHANISM_UNDER_ESTIMATION` forces
:data:`CIRCULAR_NOT_IDENTIFIABLE`. :data:`UNCLASSIFIED` is refused rather than
assumed benign, for the same reason ``UNKNOWN`` source authority is refused in
:mod:`..calibration_evidence`: unclassified is the state of the thing nobody
checked.

Point scale is conditional, not assumed
---------------------------------------

Nothing here presumes the 14-points-per-standardized-unit scale must be fitted.
The manifest resolves it to one of four states and the supervisor supports all
four, including the two that mean "no fitting happens": carrying the governed
value forward with a recorded reason, and declaring it unidentifiable from its
own generated outputs.

This module reads a manifest. It does not create one, and it cannot promote
anything -- the strongest thing it produces is permission for a later stage to
run a search whose result still has to survive validation, holdout and a human.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .. import fcs
from ..errors import GovernanceBlock, InputValidationError
from .digests import digest_mapping, sha256_file

__all__ = [
    "CIRCULARITY_CLASSES",
    "CIRCULAR_NOT_IDENTIFIABLE",
    "ELIGIBILITY_CLASSES",
    "EXTERNAL_WITNESS_ONLY",
    "FILENAME_CHECKS_ROLE",
    "FITTABLE_ELIGIBILITY",
    "GENERATED_BY_MECHANISM_UNDER_ESTIMATION",
    "GOVERNED_PARAMETERS",
    "INDEPENDENT_OF_MECHANISM",
    "POINT_SCALE_RESOLUTIONS",
    "PRIMARY_ESTIMATION_DOMAIN",
    "PRIMARY_PROJECTION_SEASON",
    "REAL_WITNESS_CORPUS_SHA256",
    "ParameterEvidence",
    "PointScaleResolution",
    "SyntheticEvidenceManifest",
    "UNCLASSIFIED",
    "load_evidence_manifest",
    "require_fit_permitted",
    "require_synthetic_only_primary_estimation_domain",
]


# --- doctrine constants ------------------------------------------------------

#: The only seasons that may estimate the primary synthetic parameter vector.
PRIMARY_ESTIMATION_DOMAIN: tuple[str, ...] = ("SYNTHETIC_2024", "SYNTHETIC_2025")

#: What the estimated vector is for.
PRIMARY_PROJECTION_SEASON = "SYNTHETIC_2026"

#: What the label-matching in this module is for. The authoritative gate is
#: :mod:`.domain_manifest`, which keys on content digests; these patterns run
#: alongside it and may only add a refusal.
FILENAME_CHECKS_ROLE = "DEFENSE_IN_DEPTH_SECONDARY_NEVER_AUTHORITATIVE"

#: Any season label matching this is real football. Matched case-insensitively
#: as a prefix *and* as a bare four-digit year, because "2023" and "REAL_2023"
#: are the same corpus wearing different labels. This catches a mislabelled
#: season; it does not catch a renamed file, and it is not asked to -- the
#: manifest gate keyed on bytes does that.
_REAL_SEASON_PATTERNS = (
    re.compile(r"^real[_\- ]", re.IGNORECASE),
    re.compile(r"^(19|20)\d{2}$"),
    re.compile(r"^observed[_\- ]", re.IGNORECASE),
    re.compile(r"^historical[_\- ]", re.IGNORECASE),
)

#: The accepted real historical observation corpus, by content digest.
REAL_WITNESS_CORPUS_SHA256 = (
    "31504e8d03b68de549bb999f2ce6a62824eb3286e3802712534d3092fa3f7aac"
)

#: The only role real football may hold under this calibration doctrine.
EXTERNAL_WITNESS_ONLY = "EXTERNAL_WITNESS_ONLY"


# --- eligibility -------------------------------------------------------------

#: The parameter is identifiable from admissible synthetic evidence and a
#: deterministic search may run for it.
FIT_ALLOWED = "FIT_ALLOWED"

#: A governed value already exists and is carried forward unchanged.
FIXED = "FIXED"

#: Evidence supports a prior, not an estimate. Recorded, never fitted.
PRIOR_ONLY = "PRIOR_ONLY"

#: The field diagnoses plausibility only. It can never select a value.
WITNESS_ONLY = "WITNESS_ONLY"

#: The evidence was generated by the mechanism being estimated. Fitting it
#: recovers the generator's own setting; it is not a measurement.
CIRCULAR_NOT_IDENTIFIABLE = "CIRCULAR_NOT_IDENTIFIABLE"

#: The manifest names the parameter but holds no evidence for it.
MISSING = "MISSING"

#: Governance forbids touching it in this run.
BLOCKED = "BLOCKED"

ELIGIBILITY_CLASSES: tuple[str, ...] = (
    FIT_ALLOWED,
    FIXED,
    PRIOR_ONLY,
    WITNESS_ONLY,
    CIRCULAR_NOT_IDENTIFIABLE,
    MISSING,
    BLOCKED,
)

#: The single class under which a numerical search may run. Membership is the
#: whole test; there is no "close enough" eligibility.
FITTABLE_ELIGIBILITY: tuple[str, ...] = (FIT_ALLOWED,)

#: Classes that mean "a value exists and travels forward without being fitted".
CARRY_FORWARD_ELIGIBILITY: tuple[str, ...] = (FIXED, PRIOR_ONLY)

#: Classes that stop the run rather than yielding a value.
REFUSING_ELIGIBILITY: tuple[str, ...] = (MISSING, BLOCKED)


# --- circularity -------------------------------------------------------------

#: The evidence field was not produced by the mechanism under estimation.
INDEPENDENT_OF_MECHANISM = "INDEPENDENT_OF_MECHANISM"

#: It was. Forces :data:`CIRCULAR_NOT_IDENTIFIABLE`.
GENERATED_BY_MECHANISM_UNDER_ESTIMATION = "GENERATED_BY_MECHANISM_UNDER_ESTIMATION"

#: Nobody classified it. Refused, not assumed benign.
UNCLASSIFIED = "UNCLASSIFIED"

CIRCULARITY_CLASSES: tuple[str, ...] = (
    INDEPENDENT_OF_MECHANISM,
    GENERATED_BY_MECHANISM_UNDER_ESTIMATION,
    UNCLASSIFIED,
)


# --- point scale -------------------------------------------------------------

#: A deterministic scale-identification stage may run.
POINT_SCALE_FIT_ALLOWED = "FIT_ALLOWED"

#: Carry the governed value forward and record why.
POINT_SCALE_FIXED_EXISTING_VALUE = "FIXED_EXISTING_VALUE"

#: The scale cannot be recovered from outputs its own value produced.
POINT_SCALE_CIRCULAR_NOT_IDENTIFIABLE = "CIRCULAR_NOT_IDENTIFIABLE"

#: Governance forbids resolving it in this run.
POINT_SCALE_BLOCKED = "BLOCKED"

POINT_SCALE_RESOLUTIONS: tuple[str, ...] = (
    POINT_SCALE_FIT_ALLOWED,
    POINT_SCALE_FIXED_EXISTING_VALUE,
    POINT_SCALE_CIRCULAR_NOT_IDENTIFIABLE,
    POINT_SCALE_BLOCKED,
)

#: The governed scale already recorded on the unified axis. Read from
#: :mod:`..fcs` rather than restated, so there is one number, in one place, and
#: a change to it cannot leave this module quietly disagreeing.
GOVERNED_POINT_SCALE_POINTS_PER_SD = fcs.UNIFIED_NEUTRAL_POINTS_PER_SD


# --- the parameter set -------------------------------------------------------

#: Every parameter a manifest must classify. The six unresolved calibration
#: fields from :data:`..calibration.CALIBRATION_FIELDS`, plus the two the model
#: run also has to settle: the point scale itself and the FCS point adapter.
GOVERNED_PARAMETERS: tuple[str, ...] = (
    "weekly_performance_residual_coefficient",
    "weekly_movement_cap_points",
    "recent_form_weights",
    "blowout_treatment",
    "sample_size_regularization",
    "game_sd_points",
    "point_scale",
    "fcs_point_adapter",
)


@dataclass(frozen=True)
class ParameterEvidence:
    """What the frozen manifest says about one parameter.

    ``search_space`` is present only where ``eligibility`` is
    :data:`FIT_ALLOWED`; carrying a search space on a fixed or circular
    parameter is refused rather than ignored, because a range that is never
    searched still reads, to a later auditor, as though it might have been.
    """

    parameter: str
    eligibility: str
    circularity: str
    evidence_fields: tuple[str, ...]
    rationale: str
    current_value: Any = None
    prior_value: Any = None
    search_space: dict[str, Any] | None = None
    required: bool = True
    #: The epistemic disposition the evidence declares, where it is more specific
    #: than the eligibility class. ``MISSING`` and ``BLOCKED`` each map to one
    #: disposition by default; a manifest that knows the difference between "no
    #: evidence exists" and "the evidence exists and does not identify this" says
    #: so here. Empty means "derive it from the eligibility".
    declared_disposition: str = ""
    #: Why, as a reason code or sentence. Required whenever a disposition is
    #: declared, because a declared disposition with no stated reason is an
    #: assertion rather than a finding.
    disposition_reason: str = ""

    def __post_init__(self) -> None:
        if self.parameter not in GOVERNED_PARAMETERS:
            raise InputValidationError(
                f"Evidence manifest classifies unknown parameter {self.parameter!r}; "
                f"expected one of {list(GOVERNED_PARAMETERS)}."
            )
        if self.eligibility not in ELIGIBILITY_CLASSES:
            raise InputValidationError(
                f"Parameter {self.parameter} has unknown eligibility "
                f"{self.eligibility!r}; expected one of {list(ELIGIBILITY_CLASSES)}."
            )
        if self.circularity not in CIRCULARITY_CLASSES:
            raise InputValidationError(
                f"Parameter {self.parameter} has unknown circularity class "
                f"{self.circularity!r}; expected one of {list(CIRCULARITY_CLASSES)}."
            )
        if self.circularity == GENERATED_BY_MECHANISM_UNDER_ESTIMATION and (
            self.eligibility != CIRCULAR_NOT_IDENTIFIABLE
        ):
            raise GovernanceBlock(
                f"Parameter {self.parameter} declares its evidence "
                f"{GENERATED_BY_MECHANISM_UNDER_ESTIMATION} but claims eligibility "
                f"{self.eligibility}. A value generated by the mechanism being "
                "estimated is not independent evidence for that mechanism; the only "
                f"admissible eligibility is {CIRCULAR_NOT_IDENTIFIABLE}."
            )
        if self.circularity == UNCLASSIFIED and self.eligibility in FITTABLE_ELIGIBILITY:
            raise GovernanceBlock(
                f"Parameter {self.parameter} is {FIT_ALLOWED} with {UNCLASSIFIED} "
                "circularity. Synthetic 2024/2025 evidence must be classified for "
                "circularity before it can support a fit; unclassified is refused "
                "rather than assumed independent."
            )
        if self.eligibility in FITTABLE_ELIGIBILITY and not self.search_space:
            raise InputValidationError(
                f"Parameter {self.parameter} is {FIT_ALLOWED} but declares no search "
                "space. A fit with no declared range has no boundary to expand from."
            )
        if self.eligibility not in FITTABLE_ELIGIBILITY and self.search_space:
            raise GovernanceBlock(
                f"Parameter {self.parameter} is {self.eligibility} yet carries a search "
                "space. A range that will never be searched must not be recorded as "
                "though it might have been."
            )
        if self.eligibility in CARRY_FORWARD_ELIGIBILITY and self.current_value is None:
            raise InputValidationError(
                f"Parameter {self.parameter} is {self.eligibility} with no current "
                "value to carry forward."
            )
        if not self.rationale.strip():
            raise InputValidationError(
                f"Parameter {self.parameter} records no rationale for its eligibility."
            )
        if self.declared_disposition:
            # Imported here rather than at module scope: :mod:`.dispositions`
            # reads this module's eligibility constants, so a top-level import
            # would be a cycle. By the time an instance is constructed both
            # modules are loaded, and the check happens where the value arrives
            # rather than at the first stage that reads it.
            from .dispositions import ESTIMATOR_ADMISSIBLE, require_known_disposition

            require_known_disposition(self.parameter, self.declared_disposition)
            if not self.disposition_reason.strip():
                raise InputValidationError(
                    f"Parameter {self.parameter} declares disposition "
                    f"{self.declared_disposition} and states no reason for it."
                )
            if (
                self.declared_disposition in ESTIMATOR_ADMISSIBLE
                and self.eligibility not in FITTABLE_ELIGIBILITY
            ):
                raise GovernanceBlock(
                    f"Parameter {self.parameter} declares disposition "
                    f"{self.declared_disposition} while its eligibility is "
                    f"{self.eligibility}. A fit result cannot be declared by a manifest "
                    "that did not authorise a fit."
                )

    @property
    def fittable(self) -> bool:
        return self.eligibility in FITTABLE_ELIGIBILITY

    def as_dict(self) -> dict[str, Any]:
        return {
            "parameter": self.parameter,
            "eligibility": self.eligibility,
            "circularity": self.circularity,
            "evidence_fields": list(self.evidence_fields),
            "rationale": self.rationale,
            "current_value": self.current_value,
            "prior_value": self.prior_value,
            "search_space": None if self.search_space is None else dict(self.search_space),
            "required": self.required,
            "declared_disposition": self.declared_disposition,
            "disposition_reason": self.disposition_reason,
        }


@dataclass(frozen=True)
class PointScaleResolution:
    """How the manifest resolves points per standardized unit.

    Four states, all supported. The two that carry a value require one; the two
    that do not, refuse one -- a "circular, not identifiable" resolution that
    also reported a fitted number would be claiming the measurement it just
    said could not be made.
    """

    resolution: str
    rationale: str
    value: float | None = None
    search_space: dict[str, Any] | None = None
    evidence_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.resolution not in POINT_SCALE_RESOLUTIONS:
            raise InputValidationError(
                f"Unknown point-scale resolution {self.resolution!r}; expected one of "
                f"{list(POINT_SCALE_RESOLUTIONS)}."
            )
        if not self.rationale.strip():
            raise InputValidationError("Point-scale resolution records no rationale.")
        if self.resolution == POINT_SCALE_FIT_ALLOWED:
            if not self.search_space:
                raise InputValidationError(
                    f"Point scale is {POINT_SCALE_FIT_ALLOWED} but declares no search space."
                )
            if self.value is not None:
                raise GovernanceBlock(
                    "A point scale that is to be fitted must not also arrive with an "
                    "answer. Declare the search space, not the result."
                )
        if self.resolution == POINT_SCALE_FIXED_EXISTING_VALUE and self.value is None:
            raise InputValidationError(
                f"Point scale is {POINT_SCALE_FIXED_EXISTING_VALUE} but names no value "
                "to carry forward."
            )
        if self.resolution in (
            POINT_SCALE_CIRCULAR_NOT_IDENTIFIABLE,
            POINT_SCALE_BLOCKED,
        ):
            if self.search_space:
                raise GovernanceBlock(
                    f"Point scale is {self.resolution} yet carries a search space. "
                    "It will not be searched, and must not read as though it might be."
                )

    @property
    def fits(self) -> bool:
        return self.resolution == POINT_SCALE_FIT_ALLOWED

    def as_dict(self) -> dict[str, Any]:
        return {
            "resolution": self.resolution,
            "rationale": self.rationale,
            "value": self.value,
            "search_space": None if self.search_space is None else dict(self.search_space),
            "evidence_fields": list(self.evidence_fields),
        }


def _is_real_season(label: str) -> bool:
    return any(pattern.match(label.strip()) for pattern in _REAL_SEASON_PATTERNS)


@dataclass(frozen=True)
class SyntheticEvidenceManifest:
    """A frozen, digest-bound classification of what this run may fit.

    ``source_sha256`` is the digest of the bytes actually read, recomputed at
    load. ``manifest_digest`` is the digest of the parsed, canonicalised
    content, and is what the recommendation and approval bind to -- so a
    manifest reformatted without semantic change still binds, and a manifest
    edited in substance does not.
    """

    manifest_id: str
    primary_estimation_domain: tuple[str, ...]
    projection_season: str
    real_witness_sha256: str
    real_witness_role: str
    parameters: dict[str, ParameterEvidence]
    point_scale: PointScaleResolution
    source_path: Path
    source_sha256: str

    def __post_init__(self) -> None:
        require_synthetic_only_primary_estimation_domain(self.primary_estimation_domain)
        if self.projection_season != PRIMARY_PROJECTION_SEASON:
            raise GovernanceBlock(
                f"Primary projection season is {self.projection_season!r}; the governed "
                f"production domain projects {PRIMARY_PROJECTION_SEASON}."
            )
        if self.real_witness_role != EXTERNAL_WITNESS_ONLY:
            raise GovernanceBlock(
                f"Real historical football is admitted as {self.real_witness_role!r}. "
                f"Under this calibration doctrine its only role is "
                f"{EXTERNAL_WITNESS_ONLY}: it may diagnose plausibility and may never "
                "change the selected synthetic-domain parameter vector."
            )
        if self.real_witness_sha256.lower() != REAL_WITNESS_CORPUS_SHA256:
            raise GovernanceBlock(
                "Real witness corpus digest does not match the accepted corpus. "
                f"Expected {REAL_WITNESS_CORPUS_SHA256}, manifest declares "
                f"{self.real_witness_sha256}."
            )
        unknown = sorted(set(self.parameters) - set(GOVERNED_PARAMETERS))
        if unknown:
            raise InputValidationError(f"Manifest classifies unknown parameters: {unknown}")
        unclassified = sorted(set(GOVERNED_PARAMETERS) - set(self.parameters))
        if unclassified:
            raise GovernanceBlock(
                f"Manifest leaves parameters unclassified: {unclassified}. Every "
                "governed parameter must carry an eligibility class; an omitted "
                "parameter is not an implicitly fixed one."
            )
        declared = self.parameters["point_scale"].eligibility
        expected = _POINT_SCALE_ELIGIBILITY_FOR[self.point_scale.resolution]
        if declared != expected:
            raise GovernanceBlock(
                f"Point-scale resolution {self.point_scale.resolution} implies parameter "
                f"eligibility {expected}, but the manifest classifies point_scale as "
                f"{declared}. The two must agree or the manifest says two things."
            )

    # -- queries ------------------------------------------------------------

    def eligibility(self, parameter: str) -> str:
        try:
            return self.parameters[parameter].eligibility
        except KeyError:
            raise InputValidationError(
                f"{parameter!r} is not classified by manifest {self.manifest_id}."
            ) from None

    def fittable_parameters(self) -> tuple[str, ...]:
        return tuple(p for p in GOVERNED_PARAMETERS if self.parameters[p].fittable)

    def parameters_in_class(self, eligibility: str) -> tuple[str, ...]:
        return tuple(
            p for p in GOVERNED_PARAMETERS if self.parameters[p].eligibility == eligibility
        )

    def refusing_parameters(self) -> tuple[str, ...]:
        """Parameters whose class stops the run rather than yielding a value."""
        return tuple(
            p
            for p in GOVERNED_PARAMETERS
            if self.parameters[p].eligibility in REFUSING_ELIGIBILITY
            and self.parameters[p].required
        )

    @property
    def manifest_digest(self) -> str:
        return digest_mapping(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        return {
            "manifest_id": self.manifest_id,
            "primary_estimation_domain": list(self.primary_estimation_domain),
            "projection_season": self.projection_season,
            "real_witness": {
                "sha256": self.real_witness_sha256,
                "role": self.real_witness_role,
            },
            "point_scale": self.point_scale.as_dict(),
            "parameters": {
                name: self.parameters[name].as_dict() for name in GOVERNED_PARAMETERS
            },
            "source_sha256": self.source_sha256,
        }


#: Which parameter eligibility each point-scale resolution implies. Stated once
#: so the manifest cannot hold a resolution and an eligibility that disagree.
_POINT_SCALE_ELIGIBILITY_FOR: dict[str, str] = {
    POINT_SCALE_FIT_ALLOWED: FIT_ALLOWED,
    POINT_SCALE_FIXED_EXISTING_VALUE: FIXED,
    POINT_SCALE_CIRCULAR_NOT_IDENTIFIABLE: CIRCULAR_NOT_IDENTIFIABLE,
    POINT_SCALE_BLOCKED: BLOCKED,
}


def require_synthetic_only_primary_estimation_domain(domain: tuple[str, ...]) -> None:
    """Refuse any real season label in the primary estimation domain.

    The refusal is on the domain declaration itself rather than on the rows it
    resolves to, because by the time a real observation has been pooled into the
    fitting table the contamination has already happened and every downstream
    metric is describing a different model than the one being calibrated.

    This is :data:`FILENAME_CHECKS_ROLE` work: it reads labels. A real corpus
    that arrives under a synthetic label passes here and is refused by
    :meth:`.domain_manifest.EvidenceDomainManifest.require_primary_estimation_source`,
    which asks what the bytes are rather than what they are called.
    """
    if not domain:
        raise InputValidationError(
            "Primary estimation domain is empty. Name the synthetic seasons that "
            "estimate the parameter vector."
        )
    real = sorted(season for season in domain if _is_real_season(season))
    if real:
        raise GovernanceBlock(
            f"Real observation seasons {real} appear in the primary estimation domain. "
            "Real 2021-2024 football is EXTERNAL_WITNESS_ONLY under this calibration "
            "doctrine and must not be pooled into the synthetic parameter-estimation "
            f"table. The governed domain is {list(PRIMARY_ESTIMATION_DOMAIN)}."
        )
    unexpected = sorted(set(domain) - set(PRIMARY_ESTIMATION_DOMAIN))
    if unexpected:
        raise GovernanceBlock(
            f"Primary estimation domain names {unexpected}, which is not part of the "
            f"governed synthetic production domain {list(PRIMARY_ESTIMATION_DOMAIN)}."
        )


def require_fit_permitted(
    manifest: SyntheticEvidenceManifest, parameter: str
) -> ParameterEvidence:
    """Assert the frozen manifest permits fitting ``parameter``, or refuse.

    Every numerical stage calls this before it searches anything. The message
    names the class that was found, because "not permitted" and "permitted but
    circular" are different facts and the operator needs the second one.
    """
    record = manifest.parameters.get(parameter)
    if record is None:
        raise InputValidationError(
            f"{parameter!r} is not classified by manifest {manifest.manifest_id}."
        )
    if record.eligibility == CIRCULAR_NOT_IDENTIFIABLE:
        raise GovernanceBlock(
            f"{parameter} is {CIRCULAR_NOT_IDENTIFIABLE}: its evidence was generated by "
            "the mechanism being estimated, so a fit would recover the generator's own "
            f"setting rather than measure it. Manifest rationale: {record.rationale}"
        )
    if not record.fittable:
        raise GovernanceBlock(
            f"{parameter} is {record.eligibility} in manifest {manifest.manifest_id}; "
            f"only {FIT_ALLOWED} authorises a search. Manifest rationale: "
            f"{record.rationale}"
        )
    return record


def _parameter_from_raw(name: str, raw: Mapping[str, Any]) -> ParameterEvidence:
    search_space = raw.get("search_space")
    return ParameterEvidence(
        parameter=name,
        eligibility=str(raw["eligibility"]),
        circularity=str(raw.get("circularity", UNCLASSIFIED)),
        evidence_fields=tuple(str(x) for x in raw.get("evidence_fields", ())),
        rationale=str(raw.get("rationale", "")),
        current_value=raw.get("current_value"),
        prior_value=raw.get("prior_value"),
        search_space=None if search_space is None else dict(search_space),
        required=bool(raw.get("required", True)),
        declared_disposition=str(raw.get("declared_disposition", "")),
        disposition_reason=str(raw.get("disposition_reason", "")),
    )


def load_evidence_manifest(path: str | Path) -> SyntheticEvidenceManifest:
    """Load and validate a frozen synthetic-evidence manifest.

    The file is read as bytes and digested before it is parsed, so the recorded
    ``source_sha256`` describes what was actually on disk rather than what the
    manifest says about itself.
    """
    import json

    resolved = Path(path).resolve()
    if not resolved.exists():
        raise InputValidationError(f"Synthetic evidence manifest not found: {resolved}")
    digest = sha256_file(resolved)
    raw = json.loads(resolved.read_text(encoding="utf-8"))

    witness = raw.get("real_witness", {})
    scale_raw = raw.get("point_scale", {})
    scale_space = scale_raw.get("search_space")
    point_scale = PointScaleResolution(
        resolution=str(scale_raw["resolution"]),
        rationale=str(scale_raw.get("rationale", "")),
        value=(None if scale_raw.get("value") is None else float(scale_raw["value"])),
        search_space=None if scale_space is None else dict(scale_space),
        evidence_fields=tuple(str(x) for x in scale_raw.get("evidence_fields", ())),
    )
    parameters = {
        name: _parameter_from_raw(name, entry)
        for name, entry in sorted(raw.get("parameters", {}).items())
    }
    return SyntheticEvidenceManifest(
        manifest_id=str(raw["manifest_id"]),
        primary_estimation_domain=tuple(str(x) for x in raw.get("primary_estimation_domain", ())),
        projection_season=str(raw.get("projection_season", "")),
        real_witness_sha256=str(witness.get("sha256", "")),
        real_witness_role=str(witness.get("role", "")),
        parameters=parameters,
        point_scale=point_scale,
        source_path=resolved,
        source_sha256=digest,
    )
