"""Deterministic generation of operating points, AC N-1 labels and screening features.

All labels produced here are SIMULATOR-GENERATED (pandapower Newton-Raphson AC power flow on
PGLib-OPF test cases); they are not historical outage observations.

Operating point ``(case, seed)``
    * Global load factor ``s ~ U(0.8, 1.2)``; per-bus multiplicative noise
      ``clip(1 + 0.05·N(0,1), 0.7, 1.3)`` applied to both PD and QD (power factor kept).
    * Dispatch: non-slack generators ``PG_g = clip(PG_ref,g · r · exp(0.1·N(0,1)), PMIN, PMAX)``
      with ``r = ΣPD_op / ΣPD_ref``; the reference-bus generator balances (incl. losses).
    * Reference state ``PG_ref`` / ``VG``: PGLib-OPF sets every ``VG = 1.0`` and a non-solved
      ``PG``; with those, case300 does not converge. Where MATPOWER ships the solved original
      (same bus and generator ordering, verified at load time) its ``PG``/``VG`` are used;
      otherwise the PGLib values are kept. The source is recorded per network.
    * Operating points whose base AC power flow does not converge are rejected (counted).

Contingency labels (outage of one ``mpc.branch`` row ``l``; AC warm-started from the base state,
then ``dc`` and ``flat`` initialisation as fall-backs):
    * ``nonconv``: no convergence with any initialisation.
    * ``thermal``: any remaining rated branch has ``max(|S_from|,|S_to|)/rate_A > 100 %``.
    * ``voltage``: any energised bus is outside ``[VMIN, VMAX]``.
    * ``label = nonconv | thermal | voltage`` (absolute post-contingency AC violation).
    * ``aggravated`` (SECONDARY): non-convergence, a new violation, an existing thermal
      violation worsened by 5 percentage points, or voltage-limit excess worsened by 0.01 pu.
    * Islanding and disconnected load are separate diagnostics; unsupplied buses (NaN voltage)
      are not silently classified as numerical non-convergence.
"""

from __future__ import annotations

import copy
import logging
import time
import warnings
import zlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .cases import (
    BUS_TYPE,
    GEN_BUS,
    GEN_STATUS,
    PD,
    PG,
    PMAX,
    PMIN,
    QD,
    RATE_A,
    VG,
    VMAX,
    VMIN,
    MatpowerCase,
    branch_flows,
    build_pp_net,
    find_pglib_file,
    parse_matpower,
    set_branch_in_service,
)
from .dc import Sensitivities, Topology, sensitivities, topology
from .features import AGGRAVATION_PP, FEATURE_NAMES, compute_features

LOAD_RANGE = (0.8, 1.2)
LOAD_NOISE_SD = 0.05
LOAD_NOISE_CLIP = (0.7, 1.3)
GEN_NOISE_SD = 0.1
AGGRAVATION_PU = 0.01
TOL_PCT = 1e-6
TOL_PU = 1e-6

#: GridStorm network ids and MATPOWER originals used for the reference state.
NETWORKS = {
    "case30": ("pglib-case30-ieee", None),
    "case57": ("pglib-case57-ieee", "case57.m"),
    "case118": ("pglib-case118-ieee", "case118.m"),
    "case300": ("pglib-case300-ieee", "case300.m"),
}

LABEL_NAMES = ("label", "thermal", "voltage", "nonconv", "islanding", "aggravated")


@dataclass
class PreparedNetwork:
    name: str
    network_id: str
    case: MatpowerCase  # reference case (PG / VG possibly from MATPOWER original)
    reference_source: str
    inputs: list[dict]
    sens: Sensitivities
    topo: Topology


def prepare_network(name: str, pglib_dirs: list[Path], matpower_dir: Path | None) -> PreparedNetwork:
    network_id, mp_file = NETWORKS[name]
    case = parse_matpower(find_pglib_file(name, pglib_dirs))
    inputs = [{"path": Path(case.source_path).name, "sha256": case.source_sha256}]
    source = "pglib (PG, VG as published)"
    if mp_file is not None and matpower_dir is not None and (Path(matpower_dir) / mp_file).is_file():
        mp = parse_matpower(Path(matpower_dir) / mp_file)
        same = (
            mp.bus.shape[0] == case.bus.shape[0]
            and mp.gen.shape[0] == case.gen.shape[0]
            and np.array_equal(mp.bus[:, 0], case.bus[:, 0])
            and np.array_equal(mp.gen[:, GEN_BUS], case.gen[:, GEN_BUS])
        )
        if same:
            case.gen[:, PG] = mp.gen[:, PG]
            case.gen[:, VG] = mp.gen[:, VG]
            source = f"matpower {mp_file} (PG, VG); all other data pglib"
            inputs.append({"path": f"matpower/data/{mp_file}", "sha256": mp.source_sha256})
    return PreparedNetwork(
        name=name,
        network_id=network_id,
        case=case,
        reference_source=source,
        inputs=inputs,
        sens=sensitivities(case),
        topo=topology(case),
    )


def sample_operating_point(
    ref: MatpowerCase, seed: int, network: str
) -> tuple[MatpowerCase, float]:
    """Return ``(case_op, load_factor)``; deterministic in ``(seed, network)``.

    The RNG is ``default_rng([seed, crc32(network)])`` so equal seeds on different networks give
    independent draws.
    """
    rng = np.random.default_rng([seed, zlib.crc32(network.encode())])
    s = float(rng.uniform(*LOAD_RANGE))
    noise = np.clip(1.0 + LOAD_NOISE_SD * rng.standard_normal(ref.bus.shape[0]), *LOAD_NOISE_CLIP)
    gen_noise = np.exp(GEN_NOISE_SD * rng.standard_normal(ref.gen.shape[0]))
    op = copy.deepcopy(ref)
    op.bus[:, PD] = ref.bus[:, PD] * s * noise
    op.bus[:, QD] = ref.bus[:, QD] * s * noise
    ratio = op.bus[:, PD].sum() / ref.bus[:, PD].sum()
    slack_buses = set(ref.bus[ref.bus[:, BUS_TYPE] == 3, 0].astype(int).tolist())
    for g in range(ref.gen.shape[0]):
        if int(ref.gen[g, GEN_BUS]) in slack_buses or ref.gen[g, GEN_STATUS] <= 0:
            continue
        pg = ref.gen[g, PG] * ratio * gen_noise[g]
        # Upper bound also admits the reference dispatch itself (MATPOWER PG may exceed PGLib PMAX).
        upper = max(ref.gen[g, PMAX], ref.gen[g, PG], ref.gen[g, PMIN])
        op.gen[g, PG] = float(np.clip(pg, ref.gen[g, PMIN], upper))
    return op, s


def _quiet():
    logging.getLogger("pandapower").setLevel(logging.ERROR)
    warnings.filterwarnings("ignore")


def _runpp(net, vm0=None, va0=None) -> bool:
    import pandapower as pp
    from pandapower.auxiliary import LoadflowNotConverged
    attempts = []
    if vm0 is not None:
        attempts.append({"init_vm_pu": vm0, "init_va_degree": va0})
    attempts += [{"init": "dc"}, {"init": "flat"}]
    for kw in attempts:
        try:
            pp.runpp(net, max_iteration=30, numba=True, **kw)
            return True
        except LoadflowNotConverged:
            continue
    return False


@dataclass
class OperatingPointResult:
    ok: bool
    load_factor: float
    features: np.ndarray | None = None  # (m, n_features)
    labels: np.ndarray | None = None  # (m, len(LABEL_NAMES)) uint8
    lost_load_mw: np.ndarray | None = None
    ac_n1_seconds: float = float("nan")
    feature_seconds: float = float("nan")
    base_max_loading_pct: float = float("nan")
    base_thermal_violations: int = 0
    base_voltage_violations: int = 0


def label_operating_point(prep: PreparedNetwork, seed: int) -> OperatingPointResult:
    _quiet()
    op, s = sample_operating_point(prep.case, seed, prep.name)
    net, bmap = build_pp_net(op)
    if not _runpp(net):
        return OperatingPointResult(ok=False, load_factor=s)
    rate = op.branch[:, RATE_A]
    rated = rate > 0
    vmax, vmin = op.bus[:, VMAX], op.bus[:, VMIN]
    p0, s0 = branch_flows(net, bmap)
    load0 = np.where(rated, s0 / np.where(rated, rate, 1.0) * 100.0, 0.0)
    vm0 = net.res_bus.vm_pu.to_numpy(dtype=float).copy()
    va0 = net.res_bus.va_degree.to_numpy(dtype=float).copy()
    q0 = _branch_q_from(net, bmap)

    t0 = time.perf_counter()
    feats = compute_features(
        op, prep.sens, prep.topo, p_from_mw=p0, q_from_mvar=q0, s_max_mva=s0, vm_pu=vm0,
        load_factor=float(op.bus[:, PD].sum() / prep.case.bus[:, PD].sum()),
    )
    feat_s = time.perf_counter() - t0

    over0 = np.maximum(vm0 - vmax, vmin - vm0)  # > 0 means violated
    m = op.branch.shape[0]
    labels = np.zeros((m, len(LABEL_NAMES)), dtype=np.uint8)
    lost = np.zeros(m)
    load_p = net.load.set_index("bus").p_mw.groupby(level=0).sum()
    t0 = time.perf_counter()
    for row in range(m):
        set_branch_in_service(net, bmap, row, False)
        ok = _runpp(net, vm0, va0)
        if not ok:
            labels[row, 3] = 1
        else:
            _, s1 = branch_flows(net, bmap)
            load1 = np.where(rated, s1 / np.where(rated, rate, 1.0) * 100.0, 0.0)
            load1[row] = 0.0
            thermal = load1 > 100.0 + TOL_PCT
            thermal_aggravated = thermal & (
                (load0 <= 100.0 + TOL_PCT) | (load1 >= load0 + AGGRAVATION_PP)
            )
            vm1 = net.res_bus.vm_pu.to_numpy(dtype=float)
            alive = np.isfinite(vm1)
            over1 = np.where(alive, np.maximum(vm1 - vmax, vmin - vm1), -np.inf)
            volt = over1 > TOL_PU
            volt_aggravated = volt & (
                (over0 <= TOL_PU) | (over1 >= over0 + AGGRAVATION_PU)
            )
            labels[row, 1] = thermal.any()
            labels[row, 2] = volt.any()
            labels[row, 5] = thermal_aggravated.any() | volt_aggravated.any()
            if not alive.all():
                labels[row, 4] = 1
                dead = net.res_bus.index[~alive]
                lost[row] = float(load_p.reindex(dead).fillna(0.0).sum())
        labels[row, 0] = labels[row, 1] | labels[row, 2] | labels[row, 3]
        labels[row, 5] |= labels[row, 3]
        set_branch_in_service(net, bmap, row, True)
    ac_s = time.perf_counter() - t0
    return OperatingPointResult(
        ok=True,
        load_factor=s,
        features=feats,
        labels=labels,
        lost_load_mw=lost,
        ac_n1_seconds=ac_s,
        feature_seconds=feat_s,
        base_max_loading_pct=float(load0.max()),
        base_thermal_violations=int((load0 > 100.0 + TOL_PCT).sum()),
        base_voltage_violations=int((over0 > TOL_PU).sum()),
    )


def _branch_q_from(net, bmap) -> np.ndarray:
    from .cases import _RES_COLS

    q = np.zeros(bmap.element_type.shape[0])
    for kind, cols in _RES_COLS.items():
        sel = np.flatnonzero(bmap.element_type == kind)
        if sel.size == 0:
            continue
        res = net[f"res_{kind}"].loc[bmap.element[sel], [cols[2], cols[4]]].to_numpy(dtype=float)
        res = np.nan_to_num(res, nan=0.0)
        q[sel] = np.where(bmap.reversed[sel], res[:, 1], res[:, 0])
    return q


@dataclass
class Dataset:
    """Row-aligned arrays; one row per (network, operating point, outaged branch)."""

    X: np.ndarray  # float64 (N, F)
    y: np.ndarray  # uint8 (N, len(LABEL_NAMES))
    network: np.ndarray  # str
    op_id: np.ndarray  # str "<case>/<seed>" — the leakage unit
    seed: np.ndarray  # int
    branch: np.ndarray  # int, 0-based mpc.branch row
    lost_load_mw: np.ndarray
    feature_names: tuple[str, ...] = FEATURE_NAMES

    def save(self, path: Path) -> None:
        np.savez_compressed(
            path,
            X=self.X.astype(np.float32),
            y=self.y,
            network=self.network,
            op_id=self.op_id,
            seed=self.seed,
            branch=self.branch,
            lost_load_mw=self.lost_load_mw.astype(np.float32),
            feature_names=np.array(self.feature_names),
        )

    @classmethod
    def load(cls, path: Path) -> Dataset:
        z = np.load(path, allow_pickle=False)
        return cls(
            X=z["X"].astype(np.float64),
            y=z["y"],
            network=z["network"],
            op_id=z["op_id"],
            seed=z["seed"],
            branch=z["branch"],
            lost_load_mw=z["lost_load_mw"].astype(np.float64),
            feature_names=tuple(z["feature_names"].tolist()),
        )

    @classmethod
    def concat(cls, parts: list[Dataset]) -> Dataset:
        return cls(
            X=np.concatenate([p.X for p in parts]),
            y=np.concatenate([p.y for p in parts]),
            network=np.concatenate([p.network for p in parts]),
            op_id=np.concatenate([p.op_id for p in parts]),
            seed=np.concatenate([p.seed for p in parts]),
            branch=np.concatenate([p.branch for p in parts]),
            lost_load_mw=np.concatenate([p.lost_load_mw for p in parts]),
        )


def generate_network(
    prep: PreparedNetwork, seeds: list[int], log=print
) -> tuple[Dataset, list[dict]]:
    """Label every seed of one network. Returns the dataset and one record per operating point
    (including rejected ones)."""
    parts: list[Dataset] = []
    records: list[dict] = []
    m = prep.case.branch.shape[0]
    for i, seed in enumerate(seeds):
        r = label_operating_point(prep, seed)
        op_id = f"{prep.name}/{seed}"
        rec = {"op_id": op_id, "network": prep.name, "seed": seed, "load_factor": r.load_factor,
               "base_converged": r.ok}
        if r.ok:
            rec.update(
                ac_n1_seconds=r.ac_n1_seconds,
                feature_seconds=r.feature_seconds,
                base_max_loading_pct=r.base_max_loading_pct,
                base_thermal_violations=r.base_thermal_violations,
                base_voltage_violations=r.base_voltage_violations,
                positives=int(r.labels[:, 0].sum()),
                contingencies=m,
            )
            parts.append(
                Dataset(
                    X=r.features,
                    y=r.labels,
                    network=np.full(m, prep.name),
                    op_id=np.full(m, op_id),
                    seed=np.full(m, seed, dtype=np.int64),
                    branch=np.arange(m, dtype=np.int64),
                    lost_load_mw=r.lost_load_mw,
                )
            )
        records.append(rec)
        log(f"{prep.name} {i + 1}/{len(seeds)} seed={seed} ok={r.ok} s={r.load_factor:.3f} "
            f"pos={rec.get('positives', '-')} t={rec.get('ac_n1_seconds', float('nan')):.1f}s")
    if not parts:
        return Dataset(
            X=np.empty((0, len(FEATURE_NAMES))),
            y=np.empty((0, len(LABEL_NAMES)), dtype=np.uint8),
            network=np.array([], dtype=str),
            op_id=np.array([], dtype=str),
            seed=np.array([], dtype=np.int64),
            branch=np.array([], dtype=np.int64),
            lost_load_mw=np.array([], dtype=float),
        ), records
    return Dataset.concat(parts), records
