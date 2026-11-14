"""Operating-point construction: DC optimal power flow (B-theta formulation) solved with HiGHS.

PGLib-OPF case files are OPF *inputs*: their ``PG`` / ``VG`` columns are not a solved operating
point (VG is flattened to 1.0). StormBench therefore builds a reproducible N-0 operating point:

    min  sum_g C_g(P_g)                          (PGLib quadratic costs, convex piecewise-linear
                                                  approximation, ``segments`` equal-width pieces)
    s.t. B_bus theta + P_bus,shift = C_g P_g - P_d - G_s     (DC nodal balance, p.u.)
         |B_f theta + P_f,shift| <= RATE_A / baseMVA      (branches with RATE_A > 0 only)
         P_min <= P_g <= P_max,  theta_ref = 0

This is a deterministic LP (scipy.optimize.linprog, method="highs"). It is N-0 secure in the DC
model only; it is *not* N-1 (security-constrained) — exactly so that single outages can create
post-contingency overloads that the screening has to find.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp
from scipy.optimize import linprog

from .dc import DCNetwork
from .matpower import GEN_BUS, GEN_STATUS, PMAX, PMIN, MatpowerCase


@dataclass
class DCOPFResult:
    status: str  # "optimal" or the HiGHS message
    objective: float | None  # cost of the piecewise-linear objective (currency units / h)
    pg_mw: np.ndarray | None  # per mpc.gen row (out-of-service rows = 0)
    max_loading_pct: float | None


def _pwl_slopes(coeffs: np.ndarray, pmin: float, pmax: float, segments: int) -> np.ndarray:
    poly = np.poly1d(coeffs)
    edges = np.linspace(pmin, pmax, segments + 1)
    vals = poly(edges)
    width = (pmax - pmin) / segments
    return np.diff(vals) / width


def solve_dc_opf(case: MatpowerCase, net: DCNetwork, segments: int = 10) -> DCOPFResult:
    gencost = case.extra.get("gencost")
    if gencost is None:
        raise ValueError("case has no mpc.gencost")
    if np.any(gencost[:, 0] != 2):
        raise NotImplementedError("only polynomial (model 2) generator costs are supported")
    pos = {int(b): i for i, b in enumerate(net.bus_numbers)}
    gen = case.gen
    on = np.flatnonzero(
        (gen[:, GEN_STATUS] > 0) & np.isin(gen[:, GEN_BUS].astype(int), net.bus_numbers)
    )
    base = net.base_mva
    n, ng, S = net.n_bus, on.size, segments
    pmin = gen[on, PMIN] / base
    pmax = gen[on, PMAX] / base
    width = (pmax - pmin) / S

    cost = np.zeros(ng * S)
    for j, g in enumerate(on):
        ncost = int(gencost[g, 3])
        coeffs = gencost[g, 4 : 4 + ncost]  # highest order first, in MW
        if pmax[j] > pmin[j]:
            cost[j * S : (j + 1) * S] = _pwl_slopes(coeffs, gen[g, PMIN], gen[g, PMAX], S)
    constant = sum(
        float(np.poly1d(gencost[g, 4 : 4 + int(gencost[g, 3])])(gen[g, PMIN])) for g in on
    )
    # variables: [delta (ng*S, p.u.), theta (n)]
    c = np.r_[cost * base, np.zeros(n)]
    gbus = np.array([pos[int(b)] for b in gen[on, GEN_BUS]])
    rows = np.repeat(gbus, S)
    Cg_seg = sp.csr_matrix((np.ones(ng * S), (rows, np.arange(ng * S))), shape=(n, ng * S))
    Cg = sp.csr_matrix((np.ones(ng), (gbus, np.arange(ng))), shape=(n, ng))
    p_fixed = net.p_inj_pu.copy()
    # remove the case's own generation from p_inj (keep loads/shunts only)
    pg_case = np.zeros(n)
    np.add.at(pg_case, gbus, gen[on, 1] / base)
    load_part = p_fixed - pg_case  # = -(Pd + Gs)/base
    # Bbus theta - Cg_seg delta = Cg pmin + load_part - pbus_shift
    A_eq = sp.hstack([-Cg_seg, net.Bbus]).tocsr()
    b_eq = Cg @ pmin + load_part - net.pbus_shift
    mon = np.flatnonzero(net.rate_a_mw > 0)
    Bf_m = net.Bf[mon]
    rate = net.rate_a_mw[mon] / base
    zeros = sp.csr_matrix((mon.size, ng * S))
    A_ub = sp.vstack([sp.hstack([zeros, Bf_m]), sp.hstack([zeros, -Bf_m])]).tocsr()
    b_ub = np.r_[rate - net.pf_shift[mon], rate + net.pf_shift[mon]]
    bounds = [(0.0, float(w)) for w in np.repeat(width, S)] + [(None, None)] * n
    bounds[ng * S + net.slack] = (0.0, 0.0)
    res = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")
    if res.status != 0:
        return DCOPFResult(
            status=str(res.message), objective=None, pg_mw=None, max_loading_pct=None
        )
    delta = res.x[: ng * S].reshape(ng, S)
    theta = res.x[ng * S :]
    pg = np.zeros(gen.shape[0])
    pg[on] = (pmin + delta.sum(axis=1)) * base
    flows = (net.Bf @ theta + net.pf_shift) * base
    max_loading = float(np.max(np.abs(flows[mon]) / net.rate_a_mw[mon]) * 100) if mon.size else None
    return DCOPFResult(
        status="optimal",
        objective=float(res.fun + constant),
        pg_mw=pg,
        max_loading_pct=max_loading,
    )
