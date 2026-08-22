"""Emit the V3 FCS point-scale research result.

The artifact is a pure function of the module: no arguments, no environment, no
clock. Running this twice produces identical bytes, and a test asserts the
committed copy equals a fresh emission, so the artifact is checkable rather than
merely present.

Deliberately not parameterised by a corpus path. The moment an audited
FBS-versus-FCS corpus exists it is bound through
``fcs_scale_research.bind_research_corpus`` and passed to
``fcs_scale_research_result``; until then there is nothing to point at, and a
``--corpus`` flag would invite pointing at something unaudited.

Usage::

    python scripts/build_fcs_scale_research_r1.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import (  # noqa: E402
    fcs_scale_research as research,
)

OUTPUT = REPO_ROOT / "reference" / "dynamic_weekly_mc_v3" / research.RESULT_ARTIFACT_NAME


def main() -> int:
    payload = research.fcs_scale_research_result()
    research.write_research_result(OUTPUT, payload)
    print(f"wrote {OUTPUT.relative_to(REPO_ROOT).as_posix()}")
    print(f"  terminal              {payload['terminal']}")
    print(f"  identification_status {payload['identification_status']}")
    print(f"  promotion_authorised  {payload['promotion_authorised']}")
    for entry in payload["blocked_inputs"]:
        print(f"  blocked: {entry['input']} [{entry['status']}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
