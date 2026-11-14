"""PGLib-OPF / MATPOWER case loading and the pandapower bridge used for labelling.

The ``.m`` reader parses only the numeric matrices ``mpc.bus``, ``mpc.gen``, ``mpc.branch``,
``mpc.gencost`` and the scalar ``mpc.baseMVA`` (column layout: MATPOWER User's Manual, Appendix B).
Conversion to pandapower uses pandapower's own ``from_ppc`` converter; no power-flow code is
re-implemented here.

Asset ids follow the GridStorm contract: ``bus-<BUS_I>``, ``branch-<1-based mpc.branch row>``.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

# MATPOWER column indices (0-based).
BUS_I, BUS_TYPE, PD, QD, GS, BS, BUS_AREA, VM, VA, BASE_KV, ZONE, VMAX, VMIN = range(13)
GEN_BUS, PG, QG, QMAX, QMIN, VG, MBASE, GEN_STATUS, PMAX, PMIN = range(10)
F_BUS, T_BUS, BR_R, BR_X, BR_B, RATE_A = range(6)
TAP, SHIFT, BR_STATUS = 8, 9, 10

_MATRIX_RE = re.compile(r"mpc\.(\w+)\s*=\s*\[(.*?)\]\s*;", re.DOTALL)
_BASEMVA_RE = re.compile(r"mpc\.baseMVA\s*=\s*([-+0-9.eE]+)\s*;")

#: Repository-relative default locations searched for PGLib files (first hit wins).
PGLIB_FILES = {
    "case30": "pglib_opf_case30_ieee.m",
    "case57": "pglib_opf_case57_ieee.m",
    "case118": "pglib_opf_case118_ieee.m",
    "case300": "pglib_opf_case300_ieee.m",
}


@dataclass
class MatpowerCase:
    name: str
    base_mva: float
    bus: np.ndarray
    gen: np.ndarray
    branch: np.ndarray
    gencost: np.ndarray | None = None
    source_path: str | None = None
    source_sha256: str | None = None
    extra: dict[str, np.ndarray] = field(default_factory=dict)

    @property
    def branch_ids(self) -> list[str]:
        return [f"branch-{i + 1}" for i in range(self.branch.shape[0])]

    def to_ppc(self) -> dict:
        ppc = {
            "version": "2",
            "baseMVA": float(self.base_mva),
            "bus": self.bus.copy(),
            "gen": self.gen.copy(),
            "branch": self.branch.copy(),
        }
        if self.gencost is not None:
            ppc["gencost"] = self.gencost.copy()
        return ppc


def _parse_matrix(body: str) -> np.ndarray:
    rows: list[list[float]] = []
    for raw in body.splitlines():
        line = raw.split("%", 1)[0]
        for chunk in line.split(";"):
            toks = chunk.replace(",", " ").split()
            if toks:
                rows.append([float(t) for t in toks])
    if not rows:
        return np.zeros((0, 0))
    width = max(len(r) for r in rows)
    if any(len(r) != width for r in rows):
        raise ValueError("ragged MATPOWER matrix")
    return np.asarray(rows, dtype=float)


def parse_matpower(path: str | Path) -> MatpowerCase:
    path = Path(path)
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    m = _BASEMVA_RE.search(text)
    if m is None:
        raise ValueError(f"{path}: mpc.baseMVA not found")
    mats = {name: _parse_matrix(body) for name, body in _MATRIX_RE.findall(text)}
    for req in ("bus", "gen", "branch"):
        if req not in mats:
            raise ValueError(f"{path}: mpc.{req} not found")
    return MatpowerCase(
        name=path.stem,
        base_mva=float(m.group(1)),
        bus=mats["bus"],
        gen=mats["gen"],
        branch=mats["branch"],
        gencost=mats.get("gencost"),
        source_path=str(path),
        source_sha256=hashlib.sha256(raw).hexdigest(),
        extra={k: v for k, v in mats.items() if k not in ("bus", "gen", "branch", "gencost")},
    )


def find_pglib_file(case: str, search_dirs: list[Path]) -> Path:
    fname = PGLIB_FILES[case]
    for d in search_dirs:
        p = Path(d) / fname
        if p.is_file():
            return p
    raise FileNotFoundError(f"{fname} not found in {[str(d) for d in search_dirs]}")


# --------------------------------------------------------------------------------------------
# pandapower bridge
# --------------------------------------------------------------------------------------------

_RES_COLS = {
    "line": ("from_bus", "p_from_mw", "q_from_mvar", "p_to_mw", "q_to_mvar"),
    "impedance": ("from_bus", "p_from_mw", "q_from_mvar", "p_to_mw", "q_to_mvar"),
    "trafo": ("hv_bus", "p_hv_mw", "q_hv_mvar", "p_lv_mw", "q_lv_mvar"),
}


@dataclass
class BranchMap:
    """Mapping of each ``mpc.branch`` row to its pandapower element."""

    element_type: np.ndarray  # str per row: line | trafo | impedance
    element: np.ndarray  # int pandapower index per row
    reversed: np.ndarray  # bool: pandapower first side is the MATPOWER to-bus


def build_pp_net(case: MatpowerCase, f_hz: float = 60.0):
    """Convert with pandapower ``from_ppc``; returns ``(net, BranchMap)``."""
    from pandapower.converter.pypower.from_ppc import from_ppc

    logger = logging.getLogger("pandapower")
    old = logger.level
    logger.setLevel(logging.ERROR)
    try:
        net = from_ppc(case.to_ppc(), f_hz=f_hz, validate_conversion=False, check_costs=False)
    finally:
        logger.setLevel(old)
    lk = net._from_ppc_lookups["branch"]
    et = lk["element_type"].to_numpy().astype(str)
    el = lk["element"].to_numpy().astype(np.int64)
    bus_pos = {int(b): i for i, b in enumerate(case.bus[:, BUS_I])}
    from_pp = net.bus.index.to_numpy()[[bus_pos[int(b)] for b in case.branch[:, F_BUS]]]
    rev = np.zeros(et.shape[0], dtype=bool)
    for kind, cols in _RES_COLS.items():
        sel = et == kind
        if sel.any():
            rev[sel] = net[kind].loc[el[sel], cols[0]].to_numpy() != from_pp[sel]
    return net, BranchMap(element_type=et, element=el, reversed=rev)


def set_branch_in_service(net, bmap: BranchMap, row: int, on: bool) -> None:
    net[bmap.element_type[row]].at[int(bmap.element[row]), "in_service"] = on


def branch_flows(net, bmap: BranchMap) -> tuple[np.ndarray, np.ndarray]:
    """``(p_from_mw, s_max_mva)`` per ``mpc.branch`` row from the last power-flow results.

    ``p_from_mw`` is oriented MATPOWER from -> to; ``s_max_mva`` = max(|S_from|, |S_to|).
    NaN results (de-energised elements) become 0.
    """
    n = bmap.element_type.shape[0]
    p_from = np.zeros(n)
    s_max = np.zeros(n)
    for kind, cols in _RES_COLS.items():
        sel = np.flatnonzero(bmap.element_type == kind)
        if sel.size == 0:
            continue
        res = net[f"res_{kind}"].loc[bmap.element[sel], list(cols[1:])].to_numpy(dtype=float)
        res = np.nan_to_num(res, nan=0.0)
        p1, q1, p2, q2 = res.T
        p_from[sel] = np.where(bmap.reversed[sel], p2, p1)
        s_max[sel] = np.maximum(np.hypot(p1, q1), np.hypot(p2, q2))
    return p_from, s_max
