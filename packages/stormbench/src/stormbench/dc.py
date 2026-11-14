"""DC (linearised) power-flow sensitivities from first principles: B matrices, PTDF, LODF.

Model (MATPOWER DC convention, Zimmerman et al., MATPOWER manual §3.7):
  per in-service branch l = (f -> t) with series reactance x_l, off-nominal tap tau_l (0 => 1)
  and phase shift phi_l [rad]:
      b_l = 1 / (x_l * tau_l)
      P_ft,l = b_l * (theta_f - theta_t - phi_l)            (branch flow, from side, p.u.)
  in matrix form   P_f = B_f theta + P_f,shift,  P_f,shift = -b * phi
                   P_bus = B_bus theta + P_bus,shift,  B_bus = C^T B_f,  P_bus,shift = C^T P_f,shift
  with C = C_f - C_t (branch-bus incidence, m x n).  Bus injections are
      P_bus = (P_g - P_d - G_s) / baseMVA   (G_s = shunt conductance consumption at V = 1 p.u.).

Slack handling: a single angle reference / slack bus r (the MATPOWER REF bus). Its angle is fixed
and it absorbs the power mismatch. The PTDF H (m x n) maps a bus injection balanced by an equal
withdrawal at r to branch flows, so column r of H is zero:
      H[:, nr] = B_f[:, nr] B_bus[nr, nr]^{-1},  H[:, r] = 0           (nr = non-reference buses)
Branch-to-branch transfer sensitivities  H_ll' = (H C^T)  (flow on l per 1 p.u. transferred from
f_l' to t_l') are slack-independent, hence so is the LODF:
      LODF[k, l] = H_ll[k, l] / (1 - H_ll[l, l]),   LODF[l, l] = -1
      post-outage flow of k after losing l:  f_k^(l) = f_k + LODF[k, l] f_l
References: A. J. Wood, B. F. Wollenberg, G. B. Sheblé, "Power Generation, Operation, and Control",
3rd ed., Wiley 2014, ch. 7 (linear sensitivity factors); T. Güler, G. Gross, M. Liu, "Generalized
line outage distribution factors", IEEE Trans. Power Syst. 22(2):879-881, 2007.

Islanding: outaging a *bridge* branch (no alternative path between its terminals) splits the grid.
Then 1 - H_ll[l, l] = 0 analytically and the LODF is undefined; such contingencies are classified
``islanding`` (detected structurally with a bridge search, cross-checked numerically) and never
divided through. Independent implementation; no upstream code copied.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from .matpower import (
    BR_STATUS,
    BR_X,
    BUS_I,
    BUS_TYPE,
    F_BUS,
    GEN_BUS,
    GEN_STATUS,
    GS,
    ISOLATED_BUS_TYPE,
    PD,
    PG,
    RATE_A,
    REF_BUS_TYPE,
    SHIFT,
    T_BUS,
    TAP,
    MatpowerCase,
)

#: |1 - H_ll| below this is treated as numerically islanding (cross-check of the structural test).
ISLANDING_EPS = 1e-8


@dataclass
class DCNetwork:
    """DC network in internal (consecutive) indexing. Branch arrays: in-service branches only."""

    base_mva: float
    bus_numbers: np.ndarray  # external BUS_I per internal bus index
    branch_rows: np.ndarray  # 0-based row in mpc.branch per internal branch index
    f: np.ndarray  # internal from-bus index per branch
    t: np.ndarray  # internal to-bus index per branch
    b: np.ndarray  # series susceptance 1/(x*tau), p.u.
    phi: np.ndarray  # phase shift, rad
    rate_a_mw: np.ndarray  # RATE_A in MVA (0 = unlimited / unmonitored, MATPOWER convention)
    p_inj_pu: np.ndarray  # net injection per bus (Pg - Pd - Gs)/baseMVA
    slack: int
    Cft: sp.csr_matrix  # m x n incidence C_f - C_t
    Bf: sp.csr_matrix  # m x n
    Bbus: sp.csc_matrix  # n x n
    pf_shift: np.ndarray  # m, p.u.
    pbus_shift: np.ndarray  # n, p.u.
    warnings: list[str]

    @property
    def n_bus(self) -> int:
        return self.bus_numbers.shape[0]

    @property
    def n_branch(self) -> int:
        return self.f.shape[0]

    @property
    def non_slack(self) -> np.ndarray:
        return np.flatnonzero(np.arange(self.n_bus) != self.slack)


def build_dc_network(case: MatpowerCase, slack_bus_number: int | None = None) -> DCNetwork:
    """Assemble DC matrices from MATPOWER data (in-service buses/branches/generators only)."""
    bus, gen, branch = case.bus, case.gen, case.branch
    warnings: list[str] = []
    bus_on = bus[:, BUS_TYPE] != ISOLATED_BUS_TYPE
    bus_numbers = bus[bus_on, BUS_I].astype(np.int64)
    pos = {int(b): i for i, b in enumerate(bus_numbers)}
    n = bus_numbers.shape[0]

    fb = branch[:, F_BUS].astype(np.int64)
    tb = branch[:, T_BUS].astype(np.int64)
    br_on = (branch[:, BR_STATUS] > 0) & np.array(
        [int(a) in pos and int(c) in pos for a, c in zip(fb, tb, strict=True)], dtype=bool
    )
    rows = np.flatnonzero(br_on)
    f = np.array([pos[int(v)] for v in fb[rows]], dtype=np.int64)
    t = np.array([pos[int(v)] for v in tb[rows]], dtype=np.int64)
    x = branch[rows, BR_X]
    if np.any(x == 0):
        raise ValueError("branch with zero series reactance: DC model undefined")
    tap = branch[rows, TAP].copy()
    tap[tap == 0] = 1.0
    b = 1.0 / (x * tap)
    phi = np.deg2rad(branch[rows, SHIFT])
    m = rows.shape[0]

    ar = np.arange(m)
    Cft = sp.csr_matrix(
        (np.r_[np.ones(m), -np.ones(m)], (np.r_[ar, ar], np.r_[f, t])), shape=(m, n)
    )
    Bf = sp.csr_matrix((np.r_[b, -b], (np.r_[ar, ar], np.r_[f, t])), shape=(m, n))
    Bbus = (Cft.T @ Bf).tocsc()
    pf_shift = -b * phi
    pbus_shift = Cft.T @ pf_shift

    p = np.zeros(n)
    gen_on = gen[:, GEN_STATUS] > 0
    for g_bus, pg in zip(gen[gen_on, GEN_BUS].astype(np.int64), gen[gen_on, PG], strict=True):
        if int(g_bus) in pos:
            p[pos[int(g_bus)]] += pg
    p -= bus[bus_on, PD] + bus[bus_on, GS]
    p /= case.base_mva

    if slack_bus_number is None:
        refs = np.flatnonzero(bus[bus_on, BUS_TYPE] == REF_BUS_TYPE)
        if refs.size == 0:
            raise ValueError("no reference (type 3) bus")
        if refs.size > 1:
            warnings.append(
                f"{refs.size} reference buses; using the first (bus {bus_numbers[refs[0]]}) as the "
                "single DC slack"
            )
        slack = int(refs[0])
    else:
        slack = pos[int(slack_bus_number)]

    return DCNetwork(
        base_mva=case.base_mva,
        bus_numbers=bus_numbers,
        branch_rows=rows,
        f=f,
        t=t,
        b=b,
        phi=phi,
        rate_a_mw=branch[rows, RATE_A].copy(),
        p_inj_pu=p,
        slack=slack,
        Cft=Cft,
        Bf=Bf,
        Bbus=Bbus,
        pf_shift=pf_shift,
        pbus_shift=pbus_shift,
        warnings=warnings,
    )


def solve_dc_flows(net: DCNetwork) -> np.ndarray:
    """Base-case DC power flow; returns branch flows (from side) in MW."""
    nr = net.non_slack
    rhs = (net.p_inj_pu - net.pbus_shift)[nr]
    theta = np.zeros(net.n_bus)
    theta[nr] = spla.spsolve(net.Bbus[nr][:, nr].tocsc(), rhs)
    return (net.Bf @ theta + net.pf_shift) * net.base_mva


def ptdf(net: DCNetwork) -> np.ndarray:
    """Dense PTDF (m x n) w.r.t. the single slack bus (slack column = 0)."""
    nr = net.non_slack
    lu = spla.splu(net.Bbus[nr][:, nr].tocsc())
    # H[:, nr] = Bf[:, nr] B^{-1}  =>  H[:, nr]^T = B^{-T} Bf[:, nr]^T ; B_bus is symmetric.
    rhs = net.Bf[:, nr].T.toarray()
    h_nr_t = lu.solve(rhs, trans="T")
    H = np.zeros((net.n_branch, net.n_bus))
    H[:, nr] = h_nr_t.T
    return H


def branch_transfer_ptdf(net: DCNetwork, H: np.ndarray) -> np.ndarray:
    """H_ll = H C^T (m x m): flow on k per 1 p.u. transferred from f_l to t_l."""
    return np.asarray((net.Cft @ H.T).T)


def find_bridges(n_bus: int, f: np.ndarray, t: np.ndarray) -> np.ndarray:
    """Boolean mask of bridge branches (iterative Tarjan low-link; parallel branches: no bridge)."""
    m = f.shape[0]
    adj: list[list[tuple[int, int]]] = [[] for _ in range(n_bus)]
    for e in range(m):
        a, c = int(f[e]), int(t[e])
        if a == c:
            continue
        adj[a].append((c, e))
        adj[c].append((a, e))
    disc = -np.ones(n_bus, dtype=np.int64)
    low = np.zeros(n_bus, dtype=np.int64)
    is_bridge = np.zeros(m, dtype=bool)
    timer = 0
    for root in range(n_bus):
        if disc[root] >= 0:
            continue
        disc[root] = low[root] = timer
        timer += 1
        stack: list[tuple[int, int, int]] = [(root, -1, 0)]  # node, parent edge, next adj pos
        while stack:
            v, pe, i = stack[-1]
            if i < len(adj[v]):
                stack[-1] = (v, pe, i + 1)
                w, e = adj[v][i]
                if e == pe:
                    continue
                if disc[w] < 0:
                    disc[w] = low[w] = timer
                    timer += 1
                    stack.append((w, e, 0))
                else:
                    low[v] = min(low[v], disc[w])
            else:
                stack.pop()
                if stack:
                    u = stack[-1][0]
                    low[u] = min(low[u], low[v])
                    if low[v] > disc[u]:
                        is_bridge[pe] = True
    return is_bridge


@dataclass
class LODFResult:
    lodf: np.ndarray  # m x m; columns of islanding outages are NaN
    islanding: np.ndarray  # bool per branch (structural bridge)
    numeric_islanding: np.ndarray  # bool per branch, |1 - H_ll| < ISLANDING_EPS
    denominator: np.ndarray  # 1 - H_ll[l, l]


def lodf(net: DCNetwork, H: np.ndarray | None = None) -> LODFResult:
    """Line outage distribution factors with explicit islanding classification."""
    if H is None:
        H = ptdf(net)
    Hll = branch_transfer_ptdf(net, H)
    den = 1.0 - np.diag(Hll).copy()
    islanding = find_bridges(net.n_bus, net.f, net.t)
    numeric = np.abs(den) < ISLANDING_EPS
    ok = ~islanding
    L = np.full_like(Hll, np.nan)
    L[:, ok] = Hll[:, ok] / den[ok]
    idx = np.flatnonzero(ok)
    L[idx, idx] = -1.0
    return LODFResult(lodf=L, islanding=islanding, numeric_islanding=numeric, denominator=den)


def post_contingency_flows(base_flow_mw: np.ndarray, L: np.ndarray) -> np.ndarray:
    """F[k, l] = f_k + LODF[k, l] f_l (MW). Column l = state after outage of l (NaN: islanding)."""
    return base_flow_mw[:, None] + L * base_flow_mw[None, :]


def island_effect(net: DCNetwork, l: int) -> dict:
    """For an islanding outage: buses / net injection separated from the slack's component."""
    keep = np.ones(net.n_branch, dtype=bool)
    keep[l] = False
    g = sp.csr_matrix(
        (np.ones(int(keep.sum())), (net.f[keep], net.t[keep])), shape=(net.n_bus, net.n_bus)
    )
    _, labels = sp.csgraph.connected_components(g, directed=False)
    cut = labels != labels[net.slack]
    return {
        "islanded_bus_count": int(cut.sum()),
        "islanded_net_injection_mw": float(net.p_inj_pu[cut].sum() * net.base_mva),
    }


def dc_n1_resolve(net: DCNetwork, outages: np.ndarray) -> np.ndarray:
    """Exact DC N-1 by refactorising the reduced B matrix per outage (own sparse solver).

    Only for non-islanding outages (caller's responsibility). Returns m x len(outages) flows in MW
    with the outaged branch's own flow set to 0.
    """
    nr = net.non_slack
    rhs = (net.p_inj_pu - net.pbus_shift)[nr]
    out = np.empty((net.n_branch, outages.shape[0]))
    Cft = net.Cft.tocsr()
    for j, l in enumerate(outages):
        w = np.ones(net.n_branch)
        w[l] = 0.0
        Bf = sp.diags(net.b * w) @ Cft
        Bbus = (Cft.T @ Bf).tocsc()
        pshift = Cft.T @ (net.pf_shift * w)
        theta = np.zeros(net.n_bus)
        theta[nr] = spla.splu(Bbus[nr][:, nr].tocsc()).solve(
            (net.p_inj_pu - pshift)[nr] if net.phi.any() else rhs
        )
        out[:, j] = (Bf @ theta + net.pf_shift * w) * net.base_mva
    return out
