from __future__ import annotations

from dataclasses import dataclass

from .enums import IdentityStatus


AMBIGUOUS_NICKNAMES = {
    "Tigers",
    "Bulldogs",
    "Aggies",
    "Cougars",
    "Wildcats",
    "Owls",
    "Panthers",
    "Huskies",
    "Broncos",
    "Eagles",
    "Rebels",
    "Trojans",
    "Bulls",
    "Bobcats",
    "Cardinals",
    "Spartans",
    "Bears",
    "Mountaineers",
    "Falcons",
    "Cowboys",
}


@dataclass(frozen=True)
class IdentityResolution:
    status: IdentityStatus
    stable_id: str | None
    reason: str


def resolve_source_team_label(label: str, stable_id: str | None = None) -> IdentityResolution:
    if stable_id:
        return IdentityResolution(IdentityStatus.VERIFIED, stable_id, "stable external identifier supplied")
    if label in AMBIGUOUS_NICKNAMES:
        return IdentityResolution(IdentityStatus.BLOCKED, None, "AMBIGUOUS_NICKNAME_NO_STABLE_ID")
    return IdentityResolution(IdentityStatus.PROVISIONAL, None, "nickname-only identity requires verification")
