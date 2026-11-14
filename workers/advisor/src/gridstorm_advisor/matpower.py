"""Minimal MATPOWER case-file (``.m``) reader for numeric ``mpc.*`` matrices.

Reads ``mpc.baseMVA`` and the numeric matrices ``mpc.bus``, ``mpc.gen``, ``mpc.branch`` and
``mpc.gencost`` from a MATPOWER v2 case file (the format PGLib-OPF publishes). String cell arrays
(e.g. ``mpc.bus_name``) are ignored. Written from the MATPOWER file-format description
(MATPOWER manual, Appendix B "Data File Format"); no upstream code copied.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

_MATRIX_RE = re.compile(r"mpc\.(?P<name>\w+)\s*=\s*\[(?P<body>.*?)\]\s*;", re.DOTALL)
_SCALAR_RE = re.compile(r"mpc\.(?P<name>\w+)\s*=\s*(?P<value>[-+0-9.eE]+)\s*;")


def _strip_comments(text: str) -> str:
    return "\n".join(line.split("%", 1)[0] for line in text.splitlines())


def _parse_matrix(body: str) -> np.ndarray:
    rows: list[list[float]] = []
    for raw in re.split(r"[;\n]", body):
        tokens = raw.replace(",", " ").split()
        if tokens:
            rows.append([float(t) for t in tokens])
    if not rows:
        return np.zeros((0, 0))
    width = max(len(r) for r in rows)
    if any(len(r) != width for r in rows):
        raise ValueError("ragged MATPOWER matrix")
    return np.asarray(rows, dtype=float)


def read_case(path: str | Path) -> dict:
    """Return ``{"version", "baseMVA", "bus", "gen", "branch", "gencost"}`` (numpy arrays)."""
    text = _strip_comments(Path(path).read_text(encoding="utf-8"))
    case: dict = {"version": "2"}
    for m in _SCALAR_RE.finditer(text):
        if m.group("name") == "baseMVA":
            case["baseMVA"] = float(m.group("value"))
    for m in _MATRIX_RE.finditer(text):
        name = m.group("name")
        if name in ("bus", "gen", "branch", "gencost"):
            case[name] = _parse_matrix(m.group("body"))
    missing = [k for k in ("baseMVA", "bus", "gen", "branch") if k not in case]
    if missing:
        raise ValueError(f"{path}: missing MATPOWER fields {missing}")
    return case
