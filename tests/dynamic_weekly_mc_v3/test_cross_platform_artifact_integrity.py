from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

AAC_SUCCESSOR = (
    REPO_ROOT
    / "config"
    / "dynamic_weekly_mc_v3"
    / "governed"
    / "aac_divisions_2026_R2_SUCCESSOR.csv"
)

GITATTRIBUTES = REPO_ROOT / ".gitattributes"

EXPECTED_AAC_SHA256 = (
    "92fd7f78fe3fa4cde75624a58efe2136e40e342439474435bf97c1f6b70e22ce"
)


def test_governed_aac_successor_bytes_are_exact():
    """The physical checkout must retain the governed artifact's exact bytes."""
    assert AAC_SUCCESSOR.is_file()

    actual = hashlib.sha256(AAC_SUCCESSOR.read_bytes()).hexdigest()

    assert actual == EXPECTED_AAC_SHA256


def test_gitattributes_protects_governed_artifact_trees():
    """SHA-bound governed trees must be excluded from Git text conversion."""
    assert GITATTRIBUTES.is_file()

    lines = {
        line.strip()
        for line in GITATTRIBUTES.read_text(encoding="ascii").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert "config/dynamic_weekly_mc_v3/governed/** -text" in lines
    assert "reference/dynamic_weekly_mc_v3/** -text" in lines


def test_git_marks_aac_successor_as_non_text():
    """Git itself must resolve the AAC governed artifact to text=unset."""
    relative_path = AAC_SUCCESSOR.relative_to(REPO_ROOT).as_posix()

    result = subprocess.run(
        ["git", "check-attr", "text", "--", relative_path],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip().endswith(": text: unset"), result.stdout
