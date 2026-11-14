"""DC power-flow sensitivities (PTDF, LODF) used ONLY to rank and size candidate actions.

Every candidate is afterwards evaluated with a full AC power flow; DC numbers never decide
acceptance. Built from the pandapower-internal branch model (``net._ppc`` after ``rundcpp``):
b_k = 1 / (x_k * tap_k) on the in-service branches of the slack-connected component, with the
slack bus as reference (standard textbook PTDF; e.g. Wood & Wollenberg, "Power Generation,
Operation and Control", ch. on linear sensitivity factors).
"""

from __future__ import annotations

import copy
import warnings
from dataclasses import dataclass

import numpy as np
import pandapower as pp

from gridstorm_advisor.network import AdvisorNetwork

_F_BUS, _T_BUS, _BR_X, _TAP, _BR_STATUS = 0, 1, 3, 8, 10


@dataclass
class DCSensitivity:
    branch_ids: list[str]  # rows of ptdf (in-service, energised branches)
    bus_ids: list[str]  # columns of ptdf (energised buses)
    ptdf: np.ndarray  # MW change on branch (from->to) per MW injected at bus, withdrawn at slack
    branch_from: dict[str, str]
    branch_to: dict[str, str]
    dc_flow_mw: dict[str, float]  # DC flow from->to of the evaluated state

    def row(self, branch_id: str) -> dict[str, float]:
        i = self.branch_ids.index(branch_id)
        return dict(zip(self.bus_ids, self.ptdf[i], strict=True))

    def bus_col(self, bus_id: str) -> np.ndarray:
        return self.ptdf[:, self.bus_ids.index(bus_id)]

    def lodf_column(self, outaged: str) -> np.ndarray | None:
        """LODF of every monitored branch for the outage of branch ``outaged``.

        None if the outage disconnects the network in the DC model (PTDF_kk ~= 1).
        """
        k = self.branch_ids.index(outaged)
        transfer = self.bus_col(self.branch_from[outaged]) - self.bus_col(self.branch_to[outaged])
        denom = 1.0 - transfer[k]
        if abs(denom) < 1e-6:
            return None
        col = transfer / denom
        col[k] = -1.0
        return col


def compute(adv: AdvisorNetwork, net: pp.pandapowerNet) -> DCSensitivity | None:
    """DC sensitivities of ``net`` (not mutated). None if the DC power flow fails."""
    work = copy.deepcopy(net)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            pp.rundcpp(work)
    except Exception:  # noqa: BLE001
        return None
    ppc = work._ppc
    bus_lookup = work._pd2ppc_lookups["bus"]
    br_lookup = work._pd2ppc_lookups["branch"]

    # ppc row of each GridStorm branch id
    rows: dict[str, int] = {}
    for bid, ref in adv.branches.items():
        if ref.table not in br_lookup:
            continue
        start, _ = br_lookup[ref.table]
        pos = list(work[ref.table].index).index(ref.index)
        rows[bid] = start + pos

    branch = ppc["branch"]
    n_bus = ppc["bus"].shape[0]
    status = branch[:, _BR_STATUS].real > 0
    f = branch[:, _F_BUS].real.astype(int)
    t = branch[:, _T_BUS].real.astype(int)
    x = branch[:, _BR_X].real
    tap = branch[:, _TAP].real
    tap = np.where(tap == 0, 1.0, tap)

    slack_pp = [int(b) for b in work.ext_grid.bus[work.ext_grid.in_service]]
    slack_pp += [int(b) for b in work.gen.bus[work.gen.in_service & work.gen.slack]]
    if not slack_pp:
        return None
    ref_bus = int(bus_lookup[slack_pp[0]])

    # energised component of the reference bus
    adj: dict[int, list[int]] = {i: [] for i in range(n_bus)}
    for k in np.flatnonzero(status):
        adj[f[k]].append(t[k])
        adj[t[k]].append(f[k])
    seen = {ref_bus}
    stack = [ref_bus]
    while stack:
        u = stack.pop()
        for v in adj[u]:
            if v not in seen:
                seen.add(v)
                stack.append(v)
    comp = sorted(seen)
    pos = {b: i for i, b in enumerate(comp)}

    active = [k for k in np.flatnonzero(status) if f[k] in pos and t[k] in pos]
    b = 1.0 / (x[active] * tap[active])
    nb, nl = len(comp), len(active)
    cf = np.zeros((nl, nb))
    for j, k in enumerate(active):
        cf[j, pos[f[k]]] = 1.0
        cf[j, pos[t[k]]] = -1.0
    bf = cf * b[:, None]
    bbus = cf.T @ bf
    keep = [i for i in range(nb) if comp[i] != ref_bus]
    ptdf_full = np.zeros((nl, nb))
    ptdf_full[:, keep] = bf[:, keep] @ np.linalg.inv(bbus[np.ix_(keep, keep)])

    # map ppc buses -> GridStorm bus ids
    ppc_to_bus: dict[int, str] = {}
    for bid, pp_bus in adv.buses.items():
        ppc_to_bus.setdefault(int(bus_lookup[pp_bus]), bid)
    row_of = {k: j for j, k in enumerate(active)}
    branch_ids = [bid for bid, r in sorted(rows.items(), key=lambda kv: kv[1]) if r in row_of]
    sel = [row_of[rows[bid]] for bid in branch_ids]
    bus_ids = [ppc_to_bus[c] for c in comp if c in ppc_to_bus]
    cols = [pos[c] for c in comp if c in ppc_to_bus]
    ptdf = ptdf_full[np.ix_(sel, cols)]

    dc_flow: dict[str, float] = {}
    for bid in branch_ids:
        ref = adv.branches[bid]
        col = "p_hv_mw" if ref.table == "trafo" else "p_from_mw"
        dc_flow[bid] = float(work[f"res_{ref.table}"].at[ref.index, col])
    branch_from = {bid: ppc_to_bus[int(f[rows[bid]])] for bid in branch_ids}
    branch_to = {bid: ppc_to_bus[int(t[rows[bid]])] for bid in branch_ids}
    # pandapower trafos are oriented hv->lv; flows above use that orientation, so orient the
    # PTDF row consistently with the ppc branch (from->to) and flip the flow sign if needed.
    for bid in branch_ids:
        ref = adv.branches[bid]
        if ref.table == "trafo":
            hv = adv.bus_id_of(int(work.trafo.at[ref.index, "hv_bus"]))
            if hv != branch_from[bid]:
                dc_flow[bid] = -dc_flow[bid]
    return DCSensitivity(branch_ids, bus_ids, ptdf, branch_from, branch_to, dc_flow)
