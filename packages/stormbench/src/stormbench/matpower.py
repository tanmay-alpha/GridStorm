"""Minimal MATPOWER (version 2) case-file reader.

Reads the numeric matrices ``mpc.bus``, ``mpc.gen``, ``mpc.branch`` and the scalar ``mpc.baseMVA``
from a ``.m`` case file (e.g. PGLib-OPF). Column layout follows the MATPOWER manual
(R. D. Zimmerman, C. E. Murillo-Sanchez, "MATPOWER User's Manual", Appendix B). Written from the
format specification; no upstream code is copied.

Asset ids (GridStorm contract): buses ``bus-<BUS_I>``, branches ``branch-<1-based row>``,
generators ``gen-<1-based row>``, loads ``load-<BUS_I>``.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

# MATPOWER column indices (0-based).
BUS_I, BUS_TYPE, PD, QD, GS, BS, BUS_AREA, VM, VA, BASE_KV, ZONE, VMAX, VMIN = range(13)
GEN_BUS, PG, QG, QMAX, QMIN, VG, MBASE, GEN_STATUS, PMAX, PMIN = range(10)
F_BUS, T_BUS, BR_R, BR_X, BR_B, RATE_A, RATE_B, RATE_C, TAP, SHIFT, BR_STATUS, ANGMIN, ANGMAX = (
    range(13)
)
REF_BUS_TYPE = 3
ISOLATED_BUS_TYPE = 4

_MATRIX_RE = re.compile(r"mpc\.(\w+)\s*=\s*\[(.*?)\]\s*;", re.DOTALL)
_BASEMVA_RE = re.compile(r"mpc\.baseMVA\s*=\s*([-+0-9.eE]+)\s*;")


@dataclass
class MatpowerCase:
    """Numeric MATPOWER case data (arrays are float64, MATPOWER column order)."""

    name: str
    base_mva: float
    bus: np.ndarray
    gen: np.ndarray
    branch: np.ndarray
    source_path: str | None = None
    source_sha256: str | None = None
    extra: dict[str, np.ndarray] = field(default_factory=dict)

    @property
    def branch_ids(self) -> list[str]:
        return [f"branch-{i + 1}" for i in range(self.branch.shape[0])]

    @property
    def bus_ids(self) -> list[str]:
        return [f"bus-{int(b)}" for b in self.bus[:, BUS_I]]

    def to_ppc(self) -> dict:
        """Return a MATPOWER-style ``ppc`` dict (copies) for pandapower's ``from_ppc``."""
        ppc = {
            "version": "2",
            "baseMVA": float(self.base_mva),
            "bus": self.bus.copy(),
            "gen": self.gen.copy(),
            "branch": self.branch.copy(),
        }
        if "gencost" in self.extra:
            ppc["gencost"] = self.extra["gencost"].copy()
        return ppc


def _parse_matrix(body: str) -> np.ndarray:
    rows: list[list[float]] = []
    for raw_line in body.splitlines():
        line = raw_line.split("%", 1)[0]
        for chunk in line.split(";"):
            tokens = chunk.replace(",", " ").split()
            if tokens:
                rows.append([float(tok) for tok in tokens])
    if not rows:
        return np.zeros((0, 0))
    width = max(len(r) for r in rows)
    if any(len(r) != width for r in rows):
        raise ValueError("ragged MATPOWER matrix")
    return np.asarray(rows, dtype=float)


def parse_matpower(path: str | Path) -> MatpowerCase:
    """Parse a MATPOWER ``.m`` file into a :class:`MatpowerCase`."""
    path = Path(path)
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    m = _BASEMVA_RE.search(text)
    if m is None:
        raise ValueError(f"{path}: mpc.baseMVA not found")
    matrices: dict[str, np.ndarray] = {}
    for name, body in _MATRIX_RE.findall(text):
        matrices[name] = _parse_matrix(body)
    for req in ("bus", "gen", "branch"):
        if req not in matrices:
            raise ValueError(f"{path}: mpc.{req} not found")
    extra = {k: v for k, v in matrices.items() if k not in ("bus", "gen", "branch")}
    return MatpowerCase(
        name=path.stem,
        base_mva=float(m.group(1)),
        bus=matrices["bus"],
        gen=matrices["gen"],
        branch=matrices["branch"],
        source_path=str(path),
        source_sha256=hashlib.sha256(raw).hexdigest(),
        extra=extra,
    )


def case_from_ppc(ppc: dict, name: str) -> MatpowerCase:
    """Wrap an in-memory MATPOWER/pandapower ``ppc`` dict (e.g. ``net._ppc``)."""
    return MatpowerCase(
        name=name,
        base_mva=float(ppc["baseMVA"]),
        bus=np.asarray(ppc["bus"], dtype=float)[:, :13].copy(),
        gen=np.asarray(ppc["gen"], dtype=float)[:, :10].copy(),
        branch=np.asarray(ppc["branch"], dtype=float)[:, :13].real.copy(),
    )
