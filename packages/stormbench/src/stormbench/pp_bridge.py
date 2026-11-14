"""pandapower adapter: MATPOWER case -> pandapower net; per-branch results keyed by mpc.branch row.

pandapower's ``from_ppc`` splits ``mpc.branch`` rows into ``line``, ``trafo`` and ``impedance``
elements and records the mapping in ``net._from_ppc_lookups['branch']``. Transformers are oriented
hv -> lv, which may be the reverse of the MATPOWER from -> to orientation; results are re-oriented
here so that ``p_from_mw`` is always the active power entering the branch at the MATPOWER
from-bus.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandapower as pp
from pandapower.converter.pypower.from_ppc import from_ppc

from .matpower import BUS_I, F_BUS, MatpowerCase

_RES_COLS = {
    "line": ("from_bus", "p_from_mw", "q_from_mvar", "p_to_mw", "q_to_mvar"),
    "impedance": ("from_bus", "p_from_mw", "q_from_mvar", "p_to_mw", "q_to_mvar"),
    "trafo": ("hv_bus", "p_hv_mw", "q_hv_mvar", "p_lv_mw", "q_lv_mvar"),
}


@dataclass
class BranchMap:
    element_type: np.ndarray  # str per mpc.branch row
    element: np.ndarray  # int pandapower index per row
    reversed: np.ndarray  # bool: pandapower first side is the MATPOWER to-bus


def build_pp_net(case: MatpowerCase, f_hz: float = 60.0) -> tuple[pp.pandapowerNet, BranchMap]:
    """Convert with pandapower ``from_ppc`` (logging from the converter is silenced)."""
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
            first_side = net[kind].loc[el[sel], cols[0]].to_numpy()
            rev[sel] = first_side != from_pp[sel]
    return net, BranchMap(element_type=et, element=el, reversed=rev)


def set_branch_in_service(net: pp.pandapowerNet, bmap: BranchMap, row: int, on: bool) -> None:
    net[bmap.element_type[row]].at[int(bmap.element[row]), "in_service"] = on


def branch_results(net: pp.pandapowerNet, bmap: BranchMap) -> tuple[np.ndarray, np.ndarray]:
    """Return (p_from_mw, s_max_mva) per mpc.branch row from the last power-flow results.

    ``s_max_mva`` = max(|S| at both ends) (= |P| in DC). Out-of-service / de-energised -> 0.
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
