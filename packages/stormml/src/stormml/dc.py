"""DC sensitivities (PTDF / LODF) and static topology descriptors for screening features.

DC model: branch susceptance ``b_l = 1 / (x_l * tap_l)`` (``tap = 1`` where MATPOWER stores 0),
resistance, shunts and phase shifts ignored; slack = MATPOWER reference bus (type 3).

* PTDF ``H = B_f[:, ~slack] · B_bus[~slack, ~slack]^{-1}`` (slack column = 0).
* ``H_ll[k, l] = H[k, f_l] - H[k, t_l]``: flow on ``k`` per 1 p.u. injected at ``f_l`` and
  withdrawn at ``t_l``.
* ``LODF[k, l] = H_ll[k, l] / (1 - H_ll[l, l])`` for ``k != l``; ``LODF[l, l] = -1``.
  Outages with ``|1 - H_ll[l, l]| < ISLANDING_EPS`` (bridges) get a NaN column.

Post-contingency DC estimate: ``f_k^(l) = f_k + LODF[k, l] · f_l`` using the *base AC* active
flows (``f`` in MW, from-side) — the usual LODF screening applied to a solved AC state.
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx
import numpy as np

from .cases import BR_STATUS, BR_X, BUS_I, BUS_TYPE, F_BUS, T_BUS, TAP, MatpowerCase

ISLANDING_EPS = 1e-8


@dataclass
class Sensitivities:
    ptdf: np.ndarray  # m x n
    lodf: np.ndarray  # m x m, NaN columns for islanding outages
    islanding: np.ndarray  # bool per branch


@dataclass
class Topology:
    f: np.ndarray  # internal from-bus index per branch
    t: np.ndarray  # internal to-bus index per branch
    bus_degree: np.ndarray  # number of distinct neighbouring buses
    is_bridge: np.ndarray  # bool per branch (parallel branches are never bridges)
    edge_betweenness: np.ndarray  # normalised, per branch (shared by parallel branches)
    neighbours: list[np.ndarray]  # per branch: indices of other branches sharing a terminal bus


def branch_endpoints(case: MatpowerCase) -> tuple[np.ndarray, np.ndarray]:
    pos = {int(b): i for i, b in enumerate(case.bus[:, BUS_I])}
    f = np.array([pos[int(b)] for b in case.branch[:, F_BUS]], dtype=np.int64)
    t = np.array([pos[int(b)] for b in case.branch[:, T_BUS]], dtype=np.int64)
    return f, t


def sensitivities(case: MatpowerCase) -> Sensitivities:
    """PTDF / LODF for the full (all branches in service) topology of ``case``."""
    if case.branch.shape[1] > BR_STATUS and not np.all(case.branch[:, BR_STATUS] > 0):
        raise ValueError("sensitivities() expects all branches in service")
    n = case.bus.shape[0]
    m = case.branch.shape[0]
    f, t = branch_endpoints(case)
    tap = case.branch[:, TAP].copy()
    tap[tap == 0] = 1.0
    b = 1.0 / (case.branch[:, BR_X] * tap)
    cft = np.zeros((m, n))
    cft[np.arange(m), f] = 1.0
    cft[np.arange(m), t] = -1.0
    bf = b[:, None] * cft
    bbus = cft.T @ bf
    slack = np.flatnonzero(case.bus[:, BUS_TYPE] == 3)
    if slack.size != 1:
        raise ValueError(f"expected exactly one reference bus, found {slack.size}")
    keep = np.flatnonzero(np.arange(n) != slack[0])
    h = np.zeros((m, n))
    h[:, keep] = np.linalg.solve(bbus[np.ix_(keep, keep)], bf[:, keep].T).T
    hll = h[:, f] - h[:, t]
    den = 1.0 - np.diag(hll)
    isl = np.abs(den) < ISLANDING_EPS
    with np.errstate(divide="ignore", invalid="ignore"):
        lodf = hll / den[None, :]
    np.fill_diagonal(lodf, -1.0)
    lodf[:, isl] = np.nan
    return Sensitivities(ptdf=h, lodf=lodf, islanding=isl)


def topology(case: MatpowerCase) -> Topology:
    n = case.bus.shape[0]
    f, t = branch_endpoints(case)
    g = nx.Graph()
    g.add_nodes_from(range(n))
    mult: dict[tuple[int, int], int] = {}
    for a, c in zip(f.tolist(), t.tolist(), strict=True):
        key = (min(a, c), max(a, c))
        mult[key] = mult.get(key, 0) + 1
        g.add_edge(*key)
    bridges = {(min(a, c), max(a, c)) for a, c in nx.bridges(g)}
    eb = nx.edge_betweenness_centrality(g, normalized=True)
    eb = {(min(a, c), max(a, c)): v for (a, c), v in eb.items()}
    keys = [(min(a, c), max(a, c)) for a, c in zip(f.tolist(), t.tolist(), strict=True)]
    is_bridge = np.array([k in bridges and mult[k] == 1 for k in keys])
    betw = np.array([eb[k] for k in keys])
    degree = np.array([g.degree(i) for i in range(n)], dtype=float)
    at_bus: list[list[int]] = [[] for _ in range(n)]
    for i, (a, c) in enumerate(zip(f.tolist(), t.tolist(), strict=True)):
        at_bus[a].append(i)
        at_bus[c].append(i)
    neighbours = [
        np.array(sorted((set(at_bus[a]) | set(at_bus[c])) - {i}), dtype=np.int64)
        for i, (a, c) in enumerate(zip(f.tolist(), t.tolist(), strict=True))
    ]
    return Topology(
        f=f,
        t=t,
        bus_degree=degree,
        is_bridge=is_bridge,
        edge_betweenness=betw,
        neighbours=neighbours,
    )


def dc_post_contingency_loading(
    p_from_mw: np.ndarray, rate_mva: np.ndarray, lodf: np.ndarray
) -> np.ndarray:
    """``E[k, l]`` = estimated |post-outage-of-l flow on k| / rate_k · 100.

    NaN if branch ``k`` is unrated or outage ``l`` islands the network.

    The outaged branch itself (diagonal) is set to 0.
    """
    post = np.abs(p_from_mw[:, None] + lodf * p_from_mw[None, :])
    with np.errstate(divide="ignore", invalid="ignore"):
        est = post / np.where(rate_mva > 0, rate_mva, np.nan)[:, None] * 100.0
    np.fill_diagonal(est, 0.0)
    return est
