"""Platform-independent text emission for governed and reproducibility artifacts.

``Path.write_text`` opens in text mode with ``newline=None``, which asks Python
to rewrite every ``\n`` to ``os.linesep`` on the way out. On Windows that
silently turns a JSON artifact into a CRLF file, so the same code and the same
inputs produce a different digest on a different operating system — the one
failure mode a reproducibility layer cannot tolerate, and one that no test
running only on Linux would ever see.

Everything here writes the exact bytes it was handed. Callers that emit governed
or evidentiary artifacts use these helpers rather than ``write_text`` so newline
policy is decided in one place instead of at each call site.
"""

from __future__ import annotations

import json
from pathlib import Path

#: The newline every governed text artifact is written with, on every platform.
GOVERNED_NEWLINE = "\n"


def write_text_lf(path: Path, text: str) -> Path:
    """Write ``text`` as UTF-8 with LF endings, whatever the host platform.

    ``newline=""`` disables the translation layer outright, so the bytes on disk
    are the bytes in ``text``. Any CRLF the caller supplied is normalized first,
    so a governed artifact cannot carry CRLF in through its content either.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write(normalized)
    return path


def write_json_lf(path: Path, payload: object, *, trailing_newline: bool = False) -> Path:
    """Write ``payload`` as deterministic JSON: sorted keys, 2-space indent, LF.

    ``trailing_newline`` is explicit rather than defaulted because the existing
    artifacts disagree — the calibration contract ends with a newline and the
    manifest and preflight reports do not. Changing either would change bytes
    that are already registered, so the caller states which shape it emits.
    """
    body = json.dumps(payload, indent=2, sort_keys=True)
    if trailing_newline:
        body += GOVERNED_NEWLINE
    return write_text_lf(path, body)
