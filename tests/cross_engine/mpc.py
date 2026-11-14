"""Shared, engine-free helpers for the GridStorm cross-engine agreement harness.

This module is deliberately independent of every GridStorm component (it does NOT reuse the
network-import parser) so that a parsing or mapping bug in an importer cannot hide itself by being
shared with the harness. It depends only on the Python standard library and numpy, which exist in
every GridStorm engine environment.

Contents
- ``load_case``: strict MATPOWER v2 ``.m`` reader (bus/gen/branch/gencost/baseMVA only).
- ``fixed_dispatch``: the single dispatch definition every engine is given.
- ``reference_dcpf``: textbook MATPOWER DC power flow (``makeBdc`` + ``dcpf`` formulas) in numpy,
  used as an independent arbiter when pandapower and PyPSA disagree.
- id helpers following contracts.md (``bus-<BUS_I>``, ``branch-<row>``, ``gen-<row>``,
  ``load-<BUS_I>``).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
# Same override as the network importer (pipelines/network-import/src/network_import/paths.py).
NETWORKS = Path(os.environ.get("GRIDSTORM_DATA_DIR") or REPO / "data") / "networks"
# Fallback for the raw PGLib files when data/networks/<id>/source/ has not been committed yet:
# a pglib-opf checkout (default: the read-only upstream clone next to the repo).
PGLIB_DIR = Path(os.environ.get("GRIDSTORM_PGLIB_DIR") or REPO.parent / "upstream" / "pglib-opf")
WORK = Path(__file__).resolve().parent / "_work"

# Cases under test: network id -> PGLib file name.
CASES = {
    "pglib-case14-ieee": "pglib_opf_case14_ieee.m",
    "pglib-case118-ieee": "pglib_opf_case118_ieee.m",
}

# MATPOWER column indices (MATPOWER manual, Appendix B "caseformat"), 0-based.
BUS_I, BUS_TYPE, PD, QD, GS, BS, VA, BASE_KV = 0, 1, 2, 3, 4, 5, 8, 9
GEN_BUS, PG, QG, QMAX, QMIN, VG, MBASE, GEN_STATUS, PMAX, PMIN = range(10)
F_BUS, T_BUS, BR_R, BR_X, BR_B, RATE_A, RATE_B, RATE_C, TAP, SHIFT, BR_STATUS = range(11)
ANGMIN, ANGMAX = 11, 12

_BLOCK = re.compile(r"^\s*mpc\.(\w+)\s*=\s*\[(.*?)\]\s*;", re.M | re.S)
_SCALAR = re.compile(r"^\s*mpc\.(\w+)\s*=\s*([-+0-9.eE']+)\s*;", re.M)


def bus_id(b: float) -> str:
    return f"bus-{int(b)}"


def branch_id(row0: int) -> str:
    return f"branch-{row0 + 1}"


def gen_id(row0: int) -> str:
    return f"gen-{row0 + 1}"


def load_id(b: float) -> str:
    return f"load-{int(b)}"


def _matrix(body: str) -> np.ndarray:
    rows = []
    for raw in body.splitlines():
        data = raw.split("%", 1)[0]
        for chunk in data.split(";"):
            toks = chunk.replace(",", " ").split()
            if toks:
                rows.append([float(t) for t in toks])
    width = max(len(r) for r in rows)
    if any(len(r) != width for r in rows):
        raise ValueError("ragged MATPOWER matrix")
    return np.array(rows, dtype=float)


def source_path(network_id: str) -> Path:
    """Raw PGLib file: the importer's committed copy (contracts.md §2), else PGLIB_DIR."""
    for p in (NETWORKS / network_id / "source" / CASES[network_id], PGLIB_DIR / CASES[network_id]):
        if p.exists():
            return p
    raise FileNotFoundError(
        f"{CASES[network_id]} not found under {NETWORKS / network_id / 'source'} or {PGLIB_DIR}; "
        "run the network importer or set GRIDSTORM_PGLIB_DIR to a pglib-opf checkout"
    )


def display_path(path: Path) -> str:
    """Repo-relative POSIX path when inside the repo, otherwise the absolute POSIX path."""
    path = path.resolve()
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return path.as_posix()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_case(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    body = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("%"))
    scalars = dict(_SCALAR.findall(body))
    if scalars.get("version", "").strip("'") != "2":
        raise ValueError(f"{path}: only MATPOWER case format version 2 is supported")
    blocks = {k: _matrix(v) for k, v in _BLOCK.findall(body)}
    case = {
        "baseMVA": float(scalars["baseMVA"]),
        "bus": blocks["bus"],
        "gen": blocks["gen"],
        "branch": blocks["branch"],
        "gencost": blocks.get("gencost"),
    }
    if case["bus"].shape[1] < 13 or case["gen"].shape[1] < 10 or case["branch"].shape[1] < 13:
        raise ValueError(f"{path}: unexpected MATPOWER column count")
    return case


def ref_bus(case: dict) -> float:
    refs = case["bus"][case["bus"][:, BUS_TYPE] == 3, BUS_I]
    if len(refs) != 1:
        raise ValueError(f"expected exactly one reference bus, found {len(refs)}")
    return float(refs[0])


def fixed_dispatch(case: dict, *, balance: bool = True) -> dict:
    """The dispatch every engine receives (or original PG with ``balance=False``).

    PGLib PG columns are not a balanced dispatch (they are a warm start: e.g. case14 sums
    PG=199.5 MW vs PD=259 MW). In a DC power flow the slack absorbs the residual, so the result
    depends on which bus each engine treats as slack. To make the comparison independent of slack
    selection, the residual (sum PD + sum GS - sum PG) is allocated explicitly to the in-service
    generators pro rata to their headroom (Pmax - PG when the residual is positive, PG - Pmin when
    it is negative), so every set point stays inside [Pmin, Pmax]. The resulting dispatch is
    exactly balanced for a lossless DC model, so any slack choice yields the same DC flows. In AC
    the slack generator (first in-service generator at the MATPOWER reference bus) additionally
    picks up the losses.
    """
    bus, gen = case["bus"], case["gen"]
    on = gen[:, GEN_STATUS] > 0
    rb = ref_bus(case)
    slack_rows = np.flatnonzero(on & (gen[:, GEN_BUS] == rb))
    if not len(slack_rows):
        raise ValueError("no in-service generator at the reference bus")
    slack = int(slack_rows[0])
    pg0 = np.where(on, gen[:, PG], 0.0)
    demand = float(bus[:, PD].sum() + bus[:, GS].sum())
    residual = demand - float(pg0.sum())
    room = np.where(on, gen[:, PMAX] - pg0 if residual >= 0 else pg0 - gen[:, PMIN], 0.0).clip(
        min=0.0
    )
    if balance and room.sum() < abs(residual):
        raise ValueError(
            f"residual {residual:.3f} MW exceeds generator headroom {room.sum():.3f} MW"
        )
    pg = pg0 + residual * room / room.sum() if balance and residual else pg0.copy()
    return {
        "gen_p_mw": {gen_id(i): float(pg[i]) for i in range(len(gen)) if on[i]},
        "load_p_mw": {load_id(b[BUS_I]): float(b[PD]) for b in bus if b[PD] != 0.0},
        "bus_gs_mw": {bus_id(b[BUS_I]): float(b[GS]) for b in bus if b[GS] != 0.0},
        "allocation": (
            "PGLib PG + residual pro rata to headroom"
            if balance
            else "unmodified PGLib PG; reference slack absorbs residual"
        ),
        "residual_allocated_mw": residual if balance else 0.0,
        "slack_residual_mw": 0.0 if balance else residual,
        "slack_gen": gen_id(slack),
        "slack_bus": bus_id(rb),
        "slack_gen_p_mw": float(pg[slack]),
        "slack_gen_pmax_mw": float(gen[slack, PMAX]),
        "total_load_mw": float(bus[:, PD].sum()),
        "total_gs_mw": float(bus[:, GS].sum()),
        "pglib_total_pg_mw": float(pg0.sum()),
        "max_utilisation_pmax": float(
            max(pg[i] / gen[i, PMAX] for i in range(len(gen)) if on[i] and gen[i, PMAX] > 0)
        ),
    }


def _bdc(case: dict):
    """MATPOWER makeBdc: b = status / (x * tap), tap = 1 where ratio == 0; Pfinj = -b * shift."""
    bus, br, base = case["bus"], case["branch"], case["baseMVA"]
    nb, nl = len(bus), len(br)
    pos = {float(b): i for i, b in enumerate(bus[:, BUS_I])}
    f = np.array([pos[float(x)] for x in br[:, F_BUS]])
    t = np.array([pos[float(x)] for x in br[:, T_BUS]])
    tap = np.where(br[:, TAP] == 0.0, 1.0, br[:, TAP])
    b = (br[:, BR_STATUS] > 0) / (br[:, BR_X] * tap)
    Cft = np.zeros((nl, nb))
    Cft[np.arange(nl), f] = 1.0
    Cft[np.arange(nl), t] = -1.0
    Bf = b[:, None] * Cft
    Bbus = Cft.T @ Bf
    Pfinj = b * (-np.deg2rad(br[:, SHIFT]))
    Pbusinj = Cft.T @ Pfinj
    return pos, f, t, Bbus, Bf, Pfinj, Pbusinj, base


def reference_dcpf(case: dict, dispatch: dict) -> dict:
    bus, gen = case["bus"], case["gen"]
    pos, f, t, Bbus, Bf, Pfinj, Pbusinj, base = _bdc(case)
    nb = len(bus)
    pinj = -bus[:, PD] - bus[:, GS]
    for gid, p in dispatch["gen_p_mw"].items():
        row = int(gid.split("-")[1]) - 1
        pinj[pos[float(gen[row, GEN_BUS])]] += p
    rb = pos[ref_bus(case)]
    va_ref = np.deg2rad(bus[rb, VA])
    pbus = pinj / base - Pbusinj
    keep = np.array([i for i in range(nb) if i != rb])
    va = np.full(nb, va_ref)
    rhs = pbus[keep] - Bbus[np.ix_(keep, [rb])].ravel() * va_ref
    va[keep] = np.linalg.solve(Bbus[np.ix_(keep, keep)], rhs)
    pf = (Bf @ va + Pfinj) * base
    # Solved injection (slack absorbs whatever the fixed dispatch did not balance; ~0 by design).
    pbus_solved = (Bbus @ va + Pbusinj) * base
    return {
        "branch_flow_mw": {branch_id(i): float(pf[i]) for i in range(len(pf))},
        "bus_angle_deg": {bus_id(bus[i, BUS_I]): float(np.rad2deg(va[i])) for i in range(nb)},
        "bus_injection_mw": {bus_id(bus[i, BUS_I]): float(pbus_solved[i]) for i in range(nb)},
        "slack_mismatch_mw": float(pbus_solved[rb] - pinj[rb]),
    }


def reference_dcopf(case: dict) -> dict:
    """MATPOWER-style DC OPF as an LP via scipy HiGHS (only valid for linear gencost).

    Variables: in-service Pg (MW) and all bus angles (rad, ref fixed). Constraints: nodal DC
    balance, |branch flow| <= RATE_A (RATE_A == 0 => unlimited), Pmin <= Pg <= Pmax. Branch
    angle-difference limits (ANGMIN/ANGMAX) are NOT imposed because neither pandapower's from_ppc
    nor the PyPSA model carries them; the largest angle difference of the optimum is reported.
    """
    from scipy.optimize import linprog

    bus, gen, br, gc = case["bus"], case["gen"], case["branch"], case["gencost"]
    if gc is None:
        return {"status": "skipped", "reason": "no gencost"}
    if np.any(gc[: len(gen), 0] != 2):
        return {"status": "skipped", "reason": "non-polynomial gencost"}
    pos, f, t, Bbus, Bf, Pfinj, Pbusinj, base = _bdc(case)
    on = np.flatnonzero(gen[:, GEN_STATUS] > 0)
    ng, nb = len(on), len(bus)
    c1 = np.zeros(ng)
    c0 = np.zeros(ng)
    for k, g in enumerate(on):
        row = gc[g]
        n = int(row[3])
        coeffs = row[4 : 4 + n]  # highest order first
        if n >= 3 and np.any(coeffs[: n - 2] != 0):
            return {
                "status": "skipped",
                "reason": "quadratic or higher-order gencost; LP reference not valid",
            }
        c1[k] = coeffs[n - 2] if n >= 2 else 0.0
        c0[k] = coeffs[n - 1]
    rb = pos[ref_bus(case)]
    # x = [Pg (MW) ; Va (rad)]
    Cg = np.zeros((nb, ng))
    for k, g in enumerate(on):
        Cg[pos[float(gen[g, GEN_BUS])], k] = 1.0
    A_eq = np.hstack([Cg / base, -Bbus])
    b_eq = (bus[:, PD] + bus[:, GS]) / base + Pbusinj
    ref_row = np.zeros(ng + nb)
    ref_row[ng + rb] = 1.0
    A_eq = np.vstack([A_eq, ref_row])
    b_eq = np.append(b_eq, np.deg2rad(bus[rb, VA]))
    lim = br[:, RATE_A] > 0
    Bl = Bf[lim]
    A_ub = np.vstack(
        [np.hstack([np.zeros((lim.sum(), ng)), Bl]), np.hstack([np.zeros((lim.sum(), ng)), -Bl])]
    )
    rate = br[lim, RATE_A] / base
    b_ub = np.concatenate([rate - Pfinj[lim], rate + Pfinj[lim]])
    bounds = [(gen[g, PMIN], gen[g, PMAX]) for g in on] + [(None, None)] * nb
    c = np.concatenate([c1, np.zeros(nb)])
    res = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")
    if res.status != 0:
        return {"status": "failed", "message": res.message}
    pg = res.x[:ng]
    va = res.x[ng:]
    pf = (Bf @ va + Pfinj) * base
    return {
        "status": "optimal",
        "objective_linear_part": float(c1 @ pg),
        "objective_constant_part": float(c0.sum()),
        "objective": float(c1 @ pg + c0.sum()),
        "gen_p_mw": {gen_id(int(g)): float(pg[k]) for k, g in enumerate(on)},
        "branch_flow_mw": {branch_id(i): float(pf[i]) for i in range(len(pf))},
        "max_abs_angle_diff_deg": float(np.max(np.abs(np.rad2deg(va[f] - va[t])))),
        "solver": "scipy.optimize.linprog(method='highs')",
    }


def write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, sort_keys=True), encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
