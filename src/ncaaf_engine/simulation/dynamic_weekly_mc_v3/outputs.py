from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, Mapping

from .textio import write_text_lf, write_json_lf


def write_csv(rows: Iterable[Mapping[str, object]], path: Path) -> None:
    """Write a CSV whose bytes do not depend on the host platform.

    Audited under CAL-R3 and deliberately left as it is. ``newline=""`` already
    disables Python's translation layer, and :mod:`csv` then terminates rows
    with its own fixed CRLF terminator — so this already emits identical bytes
    on Windows and on Linux. Switching it to LF would be a newline policy change dressed up
    as a portability fix, and it would alter the bytes of every CSV already
    produced, which this lane is not permitted to do.
    """
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        write_text_lf(path, "")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_json(payload: object, path: Path) -> None:
    write_json_lf(path, payload)


def write_parquet(rows: list[Mapping[str, object]], path: Path) -> None:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("Parquet output requested but pyarrow is not installed; install the 'mc' extra") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist([dict(r) for r in rows])
    pq.write_table(table, path, compression="zstd")
