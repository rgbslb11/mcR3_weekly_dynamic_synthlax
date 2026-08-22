"""Runtime portability: checkout bytes, emitted bytes, and path tiers.

Three findings are covered, and each is written as the failure it prevents
rather than as the feature it added.

WINDOWS-1. Governed artifacts are verified by SHA-256 over their bytes, and Git
for Windows ships ``core.autocrlf=true`` at system scope. An independent clone
that has never had a local override therefore checks the governed CSV out as
CRLF, its registered digest fails, and a retired blocker reopens on a machine
where nothing was edited. The tests below check out this repository's own index
twice under opposite ``core.autocrlf`` settings and require the bytes to match.

CAL-R3. ``Path.write_text`` translates newlines to ``os.linesep``, so the same
generator emitted CRLF on Windows and LF elsewhere. The contract is compared by
digest across machines, which made that difference read as a changed contract.

RUNTIME-1. Architecture validation required exactly 10,000 paths, so the
development and analysis tiers could not instantiate the governed engine at
all. The replacement is three exact counts, not a relaxed bound - the tests
that matter here are the ones proving 9,999 is still refused.

No simulation is executed anywhere in this module.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import aac_divisions, run_tier
from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import calibration_contract as contract
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.config import V3Config
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.errors import GovernanceBlock
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.manifest import build_input_manifest
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.rng import deterministic_normal
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.textio import write_json_lf, write_text_lf

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config/dynamic_weekly_mc_v3/v3_experimental.json"
GOVERNED_CSV_REL = "config/dynamic_weekly_mc_v3/governed/aac_divisions_2026_R2_SUCCESSOR.csv"
BOARD_XLSX_REL = (
    "reference/dynamic_weekly_mc_v3/inputs/"
    "2026_Board_I-K_CANONICAL_APPROVED_R1_REISSUE.xlsx"
)
GOVERNED_CSV = ROOT / GOVERNED_CSV_REL
BOARD_XLSX = ROOT / BOARD_XLSX_REL

#: Text artifacts whose bytes are load-bearing: the CSV carries a digest
#: registered in source, and the Markdown and JSON are digested into the run
#: manifest and the reproducibility artifacts.
GOVERNED_TEXT_ARTIFACTS = (
    GOVERNED_CSV_REL,
    "config/dynamic_weekly_mc_v3/governed/aac_divisions_2026_R2_SUCCESSOR.provenance.json",
    "reference/dynamic_weekly_mc_v3/inputs/2026_TEAM_CANONICAL_MASTER_v2_LLM_GROUNDING.md",
    "reference/dynamic_weekly_mc_v3/V3_CALIBRATION_DATA_CONTRACT.json",
    "reference/dynamic_weekly_mc_v3/V3_BOARD_IK_CUSTODY.json",
    "reference/dynamic_weekly_mc_v3/V3_BUILD_MANIFEST.json",
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True
    )


def _have_git() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


requires_git = pytest.mark.skipif(not _have_git(), reason="git is not available")


def _checkout_index_with(autocrlf: str, destination: Path) -> dict[str, str]:
    """Materialize this repository's index under a given ``core.autocrlf``.

    ``checkout-index`` runs the same smudge path a clone's initial checkout
    does, so this reproduces what a fresh clone would put on disk without
    needing the network or a second copy of the history.
    """
    destination.mkdir(parents=True, exist_ok=True)
    _git(
        "-c",
        f"core.autocrlf={autocrlf}",
        f"--work-tree={destination}",
        "checkout-index",
        "-a",
        "-f",
    )
    return {
        str(p.relative_to(destination)).replace("\\", "/"): _sha256(p.read_bytes())
        for p in sorted(destination.rglob("*"))
        if p.is_file()
    }


# --- WINDOWS-1: checkout byte determinism ------------------------------------


@requires_git
def test_the_repository_carries_its_own_eol_policy():
    """The attributes file exists and is tracked.

    A local ``core.autocrlf=false`` fixes one machine. Only a tracked
    attributes file fixes a clone nobody has configured yet, which is the case
    the finding is about.
    """
    assert (ROOT / ".gitattributes").is_file()
    assert _git("ls-files", "--error-unmatch", ".gitattributes").returncode == 0


@requires_git
def test_every_tracked_file_survives_an_autocrlf_true_checkout(tmp_path):
    """Whole-tree, not a named list.

    A per-artifact list only protects the artifacts someone remembered. This
    compares every tracked file, so a governed artifact added later is covered
    on the day it is added rather than the day someone updates a constant.
    """
    crlf = _checkout_index_with("true", tmp_path / "crlf")
    lf = _checkout_index_with("false", tmp_path / "lf")
    assert set(crlf) == set(lf)
    assert sorted(k for k in crlf if crlf[k] != lf[k]) == []


@requires_git
def test_governed_text_is_lf_in_a_windows_default_checkout(tmp_path):
    """The case that would have failed on a fresh Windows clone.

    Checked out under the Git-for-Windows system default and required to be
    byte-identical to the LF checkout - not merely parseable, identical.
    """
    crlf = _checkout_index_with("true", tmp_path / "crlf")
    lf = _checkout_index_with("false", tmp_path / "lf")
    for artifact in GOVERNED_TEXT_ARTIFACTS:
        assert artifact in crlf, f"{artifact} is not tracked"
        assert crlf[artifact] == lf[artifact], artifact
        assert b"\r\n" not in (tmp_path / "crlf" / artifact).read_bytes(), artifact


@requires_git
def test_the_governed_csv_still_matches_its_registered_digest_under_autocrlf(tmp_path):
    """The digest, not merely the bytes.

    Ties the checkout to the constant in ``aac_divisions`` so this fails if
    either side moves.
    """
    checkout = _checkout_index_with("true", tmp_path / "crlf")
    assert checkout[GOVERNED_CSV_REL] == aac_divisions.SUCCESSOR_AAC_CSV_SHA256


@requires_git
def test_the_board_workbook_is_bit_identical_after_an_autocrlf_true_checkout(tmp_path):
    """Binary preservation.

    A workbook is a zip container: one substituted byte stops it being a
    readable ``.xlsx`` at all. Marking it binary is what keeps a text filter
    away from it, and this is the assertion that says so.
    """
    checkout = _checkout_index_with("true", tmp_path / "crlf")
    assert checkout[BOARD_XLSX_REL] == _sha256(BOARD_XLSX.read_bytes())


@requires_git
def test_gitattributes_marks_workbooks_binary_and_governed_text_lf():
    """The attributes resolve, rather than merely being written down.

    ``check-attr`` is asked what Git will really do, because a pattern that
    silently fails to match is indistinguishable from a missing rule until a
    digest breaks.
    """
    text = _git("check-attr", "text", "eol", "--", GOVERNED_CSV_REL).stdout
    assert "text: set" in text
    assert "eol: lf" in text

    workbook = _git("check-attr", "text", "binary", "--", BOARD_XLSX_REL).stdout
    assert "binary: set" in workbook
    assert "text: unset" in workbook


def test_a_crlf_substitution_in_the_governed_csv_is_detected(tmp_path):
    """The counterfactual, stated as a digest.

    Substituting CRLF for LF changes nothing about the content and everything
    about the digest. This is the exact state a fresh Windows clone would have
    been in.
    """
    original = GOVERNED_CSV.read_bytes()
    assert _sha256(original) == aac_divisions.SUCCESSOR_AAC_CSV_SHA256

    crlf = original.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    assert crlf != original
    assert _sha256(crlf) != aac_divisions.SUCCESSOR_AAC_CSV_SHA256

    substituted = tmp_path / "substituted.csv"
    substituted.write_bytes(crlf)
    assert aac_divisions.aac_artifact_status(substituted)["blocker"] == (
        aac_divisions.AAC_ARTIFACT_BLOCKER
    )


@requires_git
def test_without_gitattributes_autocrlf_true_would_break_the_digest(tmp_path):
    """Why the attributes file has to exist.

    Builds a throwaway repository holding the same governed bytes and no
    attributes file, then checks it out the way an unconfigured Windows clone
    would. If this ever stops breaking the digest the platform has changed
    underneath the finding; until then it is the evidence the protection
    cannot be dropped.
    """
    source = tmp_path / "src"
    source.mkdir()
    (source / "gov.csv").write_bytes(GOVERNED_CSV.read_bytes())
    _git("init", "-q", ".", cwd=source)
    _git("-c", "core.autocrlf=false", "add", "gov.csv", cwd=source)
    _git(
        "-c", "user.email=t@example.invalid",
        "-c", "user.name=t",
        "-c", "core.autocrlf=false",
        "commit", "-qm", "governed",
        cwd=source,
    )

    naive = tmp_path / "naive"
    naive.mkdir()
    _git(
        "-c", "core.autocrlf=true", f"--work-tree={naive}",
        "checkout-index", "-a", "-f",
        cwd=source,
    )

    checked_out = (naive / "gov.csv").read_bytes()
    assert b"\r\n" in checked_out
    assert _sha256(checked_out) != aac_divisions.SUCCESSOR_AAC_CSV_SHA256


# --- CAL-R3: deterministic emitted bytes -------------------------------------


def test_the_calibration_contract_is_emitted_with_lf_on_every_platform(tmp_path):
    """The finding, directly.

    Before the fix this file went through ``Path.write_text`` with default
    newline translation, so on Windows every line break was CRLF and the
    artifact's digest differed from the one the identical code produced on
    Linux.
    """
    emitted = contract.write_contract(tmp_path / "contract.json").read_bytes()
    assert b"\r" not in emitted
    assert emitted.endswith(b"}\n")


def test_the_emitted_contract_matches_the_committed_reference_byte_for_byte():
    """Cross-platform identity, anchored to a file in the repository.

    The committed artifact was generated elsewhere. Reproducing it exactly here
    is what makes "deterministic" a measurement rather than a claim, and it
    also proves the fix rewrote no history.
    """
    with tempfile.TemporaryDirectory() as scratch:
        emitted = contract.write_contract(Path(scratch) / "c.json").read_bytes()
    committed = ROOT / "reference/dynamic_weekly_mc_v3/V3_CALIBRATION_DATA_CONTRACT.json"
    assert emitted == committed.read_bytes()


def test_repeated_contract_emission_is_byte_stable(tmp_path):
    first = contract.write_contract(tmp_path / "a.json").read_bytes()
    second = contract.write_contract(tmp_path / "b.json").read_bytes()
    assert first == second


def test_text_emission_helpers_never_emit_cr(tmp_path):
    """Including when the caller supplies CRLF.

    A governed artifact must not be able to acquire CRLF through its content
    either, so the helper normalizes rather than trusting its input.
    """
    written = write_text_lf(tmp_path / "t.txt", "a\r\nb\rc\n")
    assert written.read_bytes() == b"a\nb\nc\n"

    payload = write_json_lf(tmp_path / "t.json", {"b": 1, "a": [1, 2]})
    body = payload.read_bytes()
    assert b"\r" not in body
    assert body.startswith(b'{\n  "a"')
    assert not body.endswith(b"\n")

    trailing = write_json_lf(tmp_path / "n.json", {"a": 1}, trailing_newline=True)
    assert trailing.read_bytes().endswith(b"}\n")


def test_emission_helpers_do_not_depend_on_os_linesep(tmp_path, monkeypatch):
    """Guards the mechanism, not just today's result.

    ``os.linesep`` is what default text mode consults. Forcing it to CRLF would
    have changed the old output and must not change this one.
    """
    monkeypatch.setattr(os, "linesep", "\r\n")
    assert write_text_lf(tmp_path / "x.txt", "one\ntwo\n").read_bytes() == b"one\ntwo\n"


# --- RUNTIME-1: governed path tiers ------------------------------------------


@pytest.mark.parametrize(
    ("paths", "name", "publishable"),
    [(500, "DEV", False), (2_000, "ANALYSIS", False), (10_000, "PUBLISH", True)],
)
def test_the_three_governed_tiers_are_exactly_these(paths, name, publishable):
    tier = run_tier.tier_for_paths(paths)
    assert (tier.name, tier.paths, tier.publish_freeze) == (name, paths, publishable)


def test_the_approved_path_counts_are_the_whole_register():
    assert run_tier.APPROVED_PATH_COUNTS == (500, 2_000, 10_000)
    assert [t.name for t in run_tier.GOVERNED_TIERS] == ["DEV", "ANALYSIS", "PUBLISH"]
    assert [t for t in run_tier.GOVERNED_TIERS if t.publish_freeze] == [run_tier.PUBLISH]


@pytest.mark.parametrize("paths", [499, 501, 1_999, 2_001, 9_999, 10_001])
def test_a_near_miss_path_count_is_refused(paths):
    """The requirement that stops this becoming ``paths > 0``.

    9,999 is not a slightly smaller publish run. It is an ungoverned one, and
    it is refused as firmly as zero.
    """
    with pytest.raises(ValueError, match="not a governed V3 path count"):
        run_tier.tier_for_paths(paths)


@pytest.mark.parametrize("paths", [0, -1, -500, 1, 250, 5_000, 20_000, 1_000_000])
def test_other_ungoverned_path_counts_are_refused(paths):
    with pytest.raises(ValueError):
        run_tier.tier_for_paths(paths)


@pytest.mark.parametrize("paths", [499, 501, 1_999, 2_001, 9_999, 10_001, 0, -500])
def test_the_engine_architecture_gate_refuses_ungoverned_counts(paths):
    """The gate the engine actually calls, not only the helper beneath it."""
    cfg = replace(V3Config.from_json(CONFIG), paths=paths)
    with pytest.raises(ValueError, match="not a governed V3 path count"):
        cfg.validate_architecture()


@pytest.mark.parametrize("paths", [500, 2_000, 10_000])
def test_every_governed_tier_passes_the_same_architecture_gate(paths):
    """All three instantiate the one governed engine.

    This is the finding: before it, only the publish configuration could reach
    preflight, so a development run had no governed engine to run on.
    """
    cfg = replace(V3Config.from_json(CONFIG), paths=paths)
    cfg.validate_architecture()
    assert cfg.run_tier.paths == paths


@pytest.mark.parametrize(("paths", "name"), [(500, "DEV"), (2_000, "ANALYSIS")])
def test_a_smaller_tier_cannot_claim_publish_or_freeze(paths, name):
    cfg = replace(V3Config.from_json(CONFIG), paths=paths)
    assert cfg.publish_freeze_eligible is False
    with pytest.raises(GovernanceBlock, match="may not be published or frozen"):
        cfg.require_publish_freeze_tier()
    with pytest.raises(GovernanceBlock, match=name):
        run_tier.require_publish_freeze_tier(paths)


def test_publish_remains_the_only_publishable_tier():
    cfg = replace(V3Config.from_json(CONFIG), paths=10_000)
    assert cfg.publish_freeze_eligible is True
    assert cfg.require_publish_freeze_tier() is run_tier.PUBLISH
    assert run_tier.is_publish_freeze_tier(10_000) is True
    assert run_tier.is_publish_freeze_tier(500) is False
    assert run_tier.is_publish_freeze_tier(2_000) is False


def test_the_shipped_configuration_is_still_the_publish_tier():
    """The default is unchanged. This lane widened what is possible, not what is."""
    cfg = V3Config.from_json(CONFIG)
    assert cfg.paths == 10_000
    assert cfg.run_tier is run_tier.PUBLISH
    assert cfg.publish_freeze_eligible is True


def test_a_smaller_run_cannot_masquerade_in_its_manifest():
    """Anti-masquerade, recorded in the artifact.

    A directory of outputs is otherwise silent about how many paths produced
    it, which is exactly how a development run gets read later as a result of
    record.
    """
    base = V3Config.from_json(CONFIG)
    dev = build_input_manifest(replace(base, paths=500), execution_blockers=[])
    publish = build_input_manifest(base, execution_blockers=[])
    assert (dev["paths"], dev["run_tier"], dev["publish_freeze_eligible"]) == (
        500,
        "DEV",
        False,
    )
    assert (publish["paths"], publish["run_tier"], publish["publish_freeze_eligible"]) == (
        10_000,
        "PUBLISH",
        True,
    )


def test_tier_state_does_not_leak_between_configurations():
    """No tier is stored anywhere it could be inherited.

    The tier is derived from ``paths`` on every access. Interleaving the tiers
    and re-reading the earlier ones proves nothing was cached on the module,
    the class, or an instance.
    """
    base = V3Config.from_json(CONFIG)
    dev = replace(base, paths=500)
    analysis = replace(base, paths=2_000)
    publish = replace(base, paths=10_000)

    for _ in range(3):
        for cfg, name, publishable in (
            (dev, "DEV", False),
            (publish, "PUBLISH", True),
            (analysis, "ANALYSIS", False),
            (dev, "DEV", False),
        ):
            assert cfg.run_tier.name == name
            assert cfg.publish_freeze_eligible is publishable

    assert base.run_tier is run_tier.PUBLISH
    assert run_tier.APPROVED_PATH_COUNTS == (500, 2_000, 10_000)


def test_a_tier_is_immutable():
    """Frozen, so a publish claim cannot be granted by assignment."""
    with pytest.raises(Exception):
        run_tier.DEV.publish_freeze = True  # type: ignore[misc]
    assert run_tier.DEV.publish_freeze is False


def test_tier_selection_changes_nothing_but_the_number_of_paths():
    """Non-negotiable architecture, asserted rather than assumed.

    Two configurations differing only in tier must agree on every governed
    field the engine reads, and the draw for a given coordinate must be
    identical across tiers - the RNG is keyed by semantic coordinates, so path
    17 of a DEV run is path 17 of a PUBLISH run.
    """
    base = V3Config.from_json(CONFIG)
    dev = replace(base, paths=500)

    for field in (
        "model_name",
        "model_version",
        "base_seed",
        "weeks",
        "prior_decay",
        "hfa_baseline_points",
        "fcs_translation_policy",
        "committee_tiebreak_policy",
        "freeze_strength_after_selection",
        "first_promoted_rerating_after_week",
        "calibration",
        "inputs",
    ):
        assert getattr(dev, field) == getattr(base, field), field

    assert dev.execution_blockers() == base.execution_blockers()

    for path_id in (0, 17, 499):
        assert deterministic_normal(dev.base_seed, 0.0, 1.0, "G1", path_id) == (
            deterministic_normal(base.base_seed, 0.0, 1.0, "G1", path_id)
        )


# --- WINDOWS-PYTEST-1 / WINDOWS-PATH-1: test temp roots ----------------------

windows_only = pytest.mark.skipif(
    sys.platform != "win32", reason="Windows-specific temp-root constraint"
)


@windows_only
def test_the_session_temp_root_is_short_enough_for_max_path(tmp_path):
    """MAX_PATH headroom, measured against the root actually in use.

    A Board custody test failed at exactly 260 characters and passed unchanged
    under a shorter root. The budget is asserted here so the next long test
    name does not silently spend the last of it.
    """
    assert len(str(tmp_path)) < 150, (
        f"tmp_path is already {len(str(tmp_path))} characters; a test that nests "
        "a few directories under it will cross MAX_PATH"
    )


@windows_only
def test_the_session_temp_root_is_not_the_stale_default():
    """WINDOWS-PYTEST-1.

    The default ``pytest-of-<user>`` root outlives its session and has already
    caused WinError 5 before collection. The run is required to be somewhere
    this repository chose instead.
    """
    assert "pytest-of-" not in os.environ.get("TMP", "")
    assert "pytest-of-" not in os.environ.get("TEMP", "")


@windows_only
def test_the_session_root_leaves_more_max_path_headroom_than_the_default(tmp_path):
    """The budget, stated as a comparison rather than a fabricated overflow.

    What crossed 260 was not the base temp alone but the base temp plus what a
    custody test builds beneath it. So the honest measurement is headroom: how
    many characters are left for a test to spend. The default form spends its
    budget on ``pytest-of-<user>`` and a numbered session directory before the
    test gets any; the chosen root spends almost none.
    """
    user = os.environ.get("USERNAME", "some-user-name")
    default_style = (
        Path(f"C:/Users/{user}/AppData/Local/Temp")
        / f"pytest-of-{user}"
        / "pytest-1024"
        / "test_the_board_inverse_of_the_g0"
    )
    assert len(str(tmp_path)) < len(str(default_style))
    assert 260 - len(str(tmp_path)) > 200


def test_the_resolver_prefers_an_override_and_falls_back_when_unusable(
    short_temp_root_resolver, tmp_path
):
    """The resolution order, including the case the finding is about.

    An explicit override wins; otherwise the first candidate that can actually
    be written to is taken. Usability is probed by writing, because on Windows
    a directory can be listable and still refuse writes - which is exactly the
    stale-root condition.
    """
    override = tmp_path / "chosen"
    chosen = short_temp_root_resolver(tmp_path, {"SYTHALAX_TEST_TMP": str(override)})
    assert chosen == override
    assert chosen.is_dir()


def test_the_resolver_steps_around_an_unusable_root_rather_than_repairing_it(
    short_temp_root_resolver, tmp_path
):
    """An inaccessible root is avoided, never fixed.

    Repairing one would need elevation, which this must run without, so the
    only correct behaviour is to choose somewhere else and carry on. The
    unusable candidate is a path the filesystem cannot create, which is the
    portable stand-in for a root the current user cannot write into.
    """
    unusable = tmp_path / "nope\0bad"
    fallback = short_temp_root_resolver(tmp_path, {"SYTHALAX_TEST_TMP": str(unusable)})
    assert fallback is not None
    assert fallback != unusable
    assert "pytest-of-" not in str(fallback)


def test_the_launcher_script_is_present_and_suppresses_no_failure():
    """The mechanism operators and agents are told to use.

    Asserted rather than assumed because a launcher that swallowed pytest's
    exit code would turn a red suite green, which is the one thing it must
    never do.
    """
    script = ROOT / "scripts/Invoke-SythalaxTests.ps1"
    assert script.is_file()
    body = script.read_text(encoding="utf-8")
    assert "--basetemp" in body
    assert "exit $code" in body
    # No error suppression anywhere in the part that runs the suite.
    assert "SilentlyContinue" not in body.split("# --- run ---")[-1]
