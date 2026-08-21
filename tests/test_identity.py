from ncaaf_engine.enums import IdentityStatus
from ncaaf_engine.identity import resolve_source_team_label


def test_ambiguous_tigers_blocked():
    r = resolve_source_team_label("Tigers")
    assert r.status == IdentityStatus.BLOCKED
    assert r.stable_id is None
    assert r.reason == "AMBIGUOUS_NICKNAME_NO_STABLE_ID"


def test_stable_id_verifies_even_ambiguous_label():
    r = resolve_source_team_label("Tigers", "covers:abc123")
    assert r.status == IdentityStatus.VERIFIED
    assert r.stable_id == "covers:abc123"


def test_nonambiguous_nickname_without_stable_id_is_not_verified():
    r = resolve_source_team_label("Horned Frogs")
    assert r.status == IdentityStatus.PROVISIONAL
