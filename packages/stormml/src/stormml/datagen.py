"""Deterministic generation of operating points, AC N-1 labels and screening features.

All labels produced here are SIMULATOR-GENERATED (pandapower Newton-Raphson AC power flow on
PGLib-OPF test cases); they are not historical outage observations.

Operating point ``(case, seed)``
    * Global load factor ``s ~ U(0.8, 1.2)``; per-bus multiplicative noise
      ``clip(1 + 0.05·N(0,1), 0.7, 1.3)`` applied to both PD and QD (power factor kept).
    * Dispatch diversity: every generator's PGLib cost coefficients are multiplied by
      ``exp(0.1·N(0,1))``.
    * Dispatch: pandapower AC OPF (PIPS, flat start) with PGLib costs, PMIN/PMAX, bus VMIN/VMAX
      and apparent-power branch limits ``max(|S_from|, |S_to|) <= alpha·RATE_A``
      (``OPF_FLOW_LIM=0``; pandapower's default limits current, which admits ``VMAX·RATE_A``
      MVA). ``alpha ~ U(0.8, 1.0)`` is an operator-style N-0 security margin and the OPF upper
      voltage limit is ``VMAX - 0.01`` (loss minimisation otherwise parks voltages exactly on
      VMAX). Without margins every binding branch sits at 100 % and almost every outage pushes
      it over the limit (smoke check: 88 % positives on 4 case118 operating points, 81 % on 3
      case300 ones), which makes absolute labels nearly uninformative. If PIPS fails, deterministic
      fall-backs drop the voltage margin and raise alpha to 0.9, 0.95, 1.0; the realised
      settings and attempt count are recorded per operating point.
    * Generator reactive limits are relaxed to ``±1e5`` Mvar because the labelling power flow
      does not enforce them either and pandapower's PIPS does not converge on PGLib case300 with
      them; the number of generators whose dispatched Q lies outside the PGLib limits is recorded
      per operating point. Branch angle-difference limits (ANGMIN/ANGMAX) are not enforced.
      Labels always use the unmodified RATE_A, VMIN and VMAX.
    * The dispatched PG and generator-bus voltage magnitudes become the PV set-points of the base
      AC power flow (reference generator balances).
    * Operating points are rejected (and counted) when the AC OPF fails, the base AC power flow
      fails, or the base state is not N-0 secure. With an insecure base every outage inherits the
      pre-existing violation, so absolute labels would be uninformative.

Contingency labels (outage of one ``mpc.branch`` row ``l``; AC warm-started from the base state,
then ``dc`` and ``flat`` initialisation as fall-backs):
    * ``nonconv``: no convergence with any initialisation.
    * ``thermal``: any remaining rated branch has ``max(|S_from|,|S_to|)/RATE_A > 100 %``.
    * ``voltage``: any energised bus is outside ``[VMIN, VMAX]``.
    * ``label = nonconv | thermal | voltage`` (PRIMARY: absolute post-contingency AC violation).
    * ``aggravated`` (SECONDARY): non-convergence, a new violation, an existing thermal
      violation worsened by 5 percentage points, or voltage-limit excess worsened by 0.01 pu.
      On N-0 secure bases every violation is new, so it differs from ``label`` only for
      operating points labelled without the base-security requirement (diagnostic use).
    * Islanding and disconnected load are separate diagnostics; unsupplied buses (NaN voltage)
      are not silently classified as numerical non-convergence.
    * Numerical tolerances: 0.01 percentage points of loading and 1e-4 pu of voltage (above the
      OPF feasibility tolerance), identical for base-security checks and labels.
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
    GEN_STATUS,
    PD,
    PG,
    QD,
    QMAX,
    QMIN,
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
COST_NOISE_SD = 0.1
DISPATCH_LIMIT_RANGE = (0.8, 1.0)
DISPATCH_VOLTAGE_MARGIN_PU = 0.01
DISPATCH_FALLBACK_LIMITS = (0.9, 0.95, 1.0)
Q_RELAX_MVAR = 1e5
AGGRAVATION_PU = 0.01
TOL_PCT = 1e-2
TOL_PU = 1e-4
Q_LIMIT_TOL_MVAR = 1e-3

#: GridStorm network ids of the PGLib-OPF cases.
NETWORKS = {
    "case30": "pglib-case30-ieee",
    "case57": "pglib-case57-ieee",
    "case118": "pglib-case118-ieee",
    "case300": "pglib-case300-ieee",
}

LABEL_NAMES = ("label", "thermal", "voltage", "nonconv", "islanding", "aggravated")

#: Operating-point outcomes recorded by ``generate_network``.
STATUS_OK = "ok"
STATUS_OPF_FAILED = "rejected_ac_opf_not_converged"
STATUS_BASE_PF_FAILED = "rejected_base_ac_pf_not_converged"
STATUS_BASE_INSECURE = "rejected_base_not_n0_secure"


@dataclass
class PreparedNetwork:
    name: str
    network_id: str
    case: MatpowerCase  # PGLib reference case
    inputs: list[dict]
    sens: Sensitivities
    topo: Topology


def prepare_network(name: str, pglib_dirs: list[Path]) -> PreparedNetwork:
    case = parse_matpower(find_pglib_file(name, pglib_dirs))
    return PreparedNetwork(
        name=name,
        network_id=NETWORKS[name],
        case=case,
        inputs=[{"path": Path(case.source_path).name, "sha256": case.source_sha256}],
        sens=sensitivities(case),
        topo=topology(case),
    )


def sample_operating_point(
    ref: MatpowerCase, seed: int, network: str
) -> tuple[MatpowerCase, float, float]:
    """Return ``(case_op, load_factor, branch_limit_fraction)``: sampled loads, perturbed
    generator costs and the dispatch branch-limit fraction ``alpha``.

    Deterministic in ``(seed, network)``: the RNG is ``default_rng([seed, crc32(network)])`` so
    equal seeds on different networks give independent draws. PG is left for the dispatch.
    """
    rng = np.random.default_rng([seed, zlib.crc32(network.encode())])
    s = float(rng.uniform(*LOAD_RANGE))
    noise = np.clip(1.0 + LOAD_NOISE_SD * rng.standard_normal(ref.bus.shape[0]), *LOAD_NOISE_CLIP)
    cost_noise = np.exp(COST_NOISE_SD * rng.standard_normal(ref.gen.shape[0]))
    alpha = float(rng.uniform(*DISPATCH_LIMIT_RANGE))
    op = copy.deepcopy(ref)
    op.bus[:, PD] = ref.bus[:, PD] * s * noise
    op.bus[:, QD] = ref.bus[:, QD] * s * noise
    if op.gencost is not None:
        ng = ref.gen.shape[0]
        if not np.all(op.gencost[:ng, 0] == 2):
            raise ValueError("only polynomial (model 2) generator costs are supported")
        op.gencost[:ng, 4:] *= cost_noise[:, None]
    return op, s, alpha


def dispatch_ac_opf(
    op: MatpowerCase, branch_limit_fraction: float = 1.0, voltage_margin_pu: float = 0.0
) -> tuple[MatpowerCase, int] | None:
    """AC OPF dispatch (see module docstring). Returns ``(dispatched_case, n_q_outside)``.

    Branch limits are ``branch_limit_fraction · RATE_A`` and the upper bus voltage limit is
    ``VMAX - voltage_margin_pu`` inside the OPF only (loss minimisation drives voltages to VMAX).
    ``dispatched_case`` carries the optimal PG and the generator-bus voltage magnitudes as VG;
    ``n_q_outside`` counts in-service generators whose optimal Q is outside [QMIN, QMAX].
    ``None`` when pandapower's OPF does not converge.
    """
    import pandapower as pp
    from pandapower.auxiliary import OPFNotConverged

    if op.gencost is None:
        raise ValueError(f"{op.name}: AC OPF dispatch needs mpc.gencost")
    net, _ = build_pp_net(op)
    net.ext_grid["controllable"] = True
    for kind in ("line", "trafo"):
        net[kind]["max_loading_percent"] = 100.0 * branch_limit_fraction
    net.bus["max_vm_pu"] -= voltage_margin_pu
    for kind in ("gen", "ext_grid"):
        net[kind]["min_q_mvar"] = -Q_RELAX_MVAR
        net[kind]["max_q_mvar"] = Q_RELAX_MVAR
    try:
        pp.runopp(net, init="flat", numba=True, OPF_FLOW_LIM=0)
    except OPFNotConverged:
        return None
    out = copy.deepcopy(op)
    lookup = net._from_ppc_lookups["gen"]
    q_outside = 0
    for row, (el, kind) in enumerate(zip(lookup["element"], lookup["element_type"], strict=True)):
        if kind not in ("gen", "ext_grid"):
            continue
        res = net[f"res_{kind}"]
        out.gen[row, PG] = float(res.p_mw.at[el])
        out.gen[row, VG] = float(net.res_bus.vm_pu.at[net[kind].bus.at[el]])
        q = float(res.q_mvar.at[el])
        if op.gen[row, GEN_STATUS] > 0 and (
            q > op.gen[row, QMAX] + Q_LIMIT_TOL_MVAR or q < op.gen[row, QMIN] - Q_LIMIT_TOL_MVAR
        ):
            q_outside += 1
    return out, q_outside


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
    status: str = STATUS_OK
    features: np.ndarray | None = None  # (m, n_features)
    labels: np.ndarray | None = None  # (m, len(LABEL_NAMES)) uint8
    lost_load_mw: np.ndarray | None = None
    opf_seconds: float = float("nan")
    ac_n1_seconds: float = float("nan")
    feature_seconds: float = float("nan")
    base_max_loading_pct: float = float("nan")
    base_max_voltage_excess_pu: float = float("nan")
    base_thermal_violations: int = 0
    base_voltage_violations: int = 0
    gen_q_outside_limits: int = 0
    branch_limit_fraction: float = float("nan")
    voltage_margin_pu: float = float("nan")
    sampled_branch_limit_fraction: float = float("nan")
    opf_attempts: int = 0


def dispatch_settings(alpha: float) -> list[tuple[float, float]]:
    """Deterministic ``(branch_limit_fraction, voltage_margin_pu)`` attempts for one operating
    point: the sampled margin first, then progressively looser settings. pandapower's PIPS is
    numerically fragile on these cases (failures are not monotone in the margins), so the
    realised setting and the attempt count are recorded per operating point."""
    out = [(alpha, DISPATCH_VOLTAGE_MARGIN_PU), (alpha, 0.0)]
    out += [(a, 0.0) for a in DISPATCH_FALLBACK_LIMITS if a > alpha]
    return out


def label_operating_point(prep: PreparedNetwork, seed: int) -> OperatingPointResult:
    """Sample, dispatch (AC OPF) and label one operating point; insecure bases are rejected."""
    _quiet()
    op, s, alpha = sample_operating_point(prep.case, seed, prep.name)
    t0 = time.perf_counter()
    dispatched = None
    attempts = 0
    for setting in dispatch_settings(alpha):
        attempts += 1
        dispatched = dispatch_ac_opf(op, *setting)
        if dispatched is not None:
            break
    opf_s = time.perf_counter() - t0
    if dispatched is None:
        return OperatingPointResult(
            ok=False,
            load_factor=s,
            status=STATUS_OPF_FAILED,
            opf_seconds=opf_s,
            sampled_branch_limit_fraction=alpha,
            opf_attempts=attempts,
        )
    case, q_outside = dispatched
    r = label_case(prep, case, s, require_secure_base=True)
    r.opf_seconds = opf_s
    r.gen_q_outside_limits = q_outside
    r.sampled_branch_limit_fraction = alpha
    r.branch_limit_fraction, r.voltage_margin_pu = setting
    r.opf_attempts = attempts
    return r


def label_case(
    prep: PreparedNetwork, op: MatpowerCase, load_factor: float, require_secure_base: bool
) -> OperatingPointResult:
    """Base AC power flow of ``op`` (PV set-points as given) and AC N-1 labels of every branch.

    With ``require_secure_base`` the N-1 loop is skipped for N-0 insecure bases.
    """
    _quiet()
    net, bmap = build_pp_net(op)
    if not _runpp(net):
        return OperatingPointResult(ok=False, load_factor=load_factor, status=STATUS_BASE_PF_FAILED)
    rate = op.branch[:, RATE_A]
    rated = rate > 0
    vmax, vmin = op.bus[:, VMAX], op.bus[:, VMIN]
    p0, s0 = branch_flows(net, bmap)
    load0 = np.where(rated, s0 / np.where(rated, rate, 1.0) * 100.0, 0.0)
    vm0 = net.res_bus.vm_pu.to_numpy(dtype=float).copy()
    va0 = net.res_bus.va_degree.to_numpy(dtype=float).copy()
    q0 = _branch_q_from(net, bmap)
    over0 = np.maximum(vm0 - vmax, vmin - vm0)  # > 0 means violated
    base = dict(
        load_factor=load_factor,
        base_max_loading_pct=float(load0.max()),
        base_max_voltage_excess_pu=float(over0.max()),
        base_thermal_violations=int((load0 > 100.0 + TOL_PCT).sum()),
        base_voltage_violations=int((over0 > TOL_PU).sum()),
    )
    if require_secure_base and (base["base_thermal_violations"] or base["base_voltage_violations"]):
        return OperatingPointResult(ok=False, status=STATUS_BASE_INSECURE, **base)

    t0 = time.perf_counter()
    feats = compute_features(
        op,
        prep.sens,
        prep.topo,
        p_from_mw=p0,
        q_from_mvar=q0,
        s_max_mva=s0,
        vm_pu=vm0,
        load_factor=float(op.bus[:, PD].sum() / prep.case.bus[:, PD].sum()),
    )
    feat_s = time.perf_counter() - t0

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
            volt_aggravated = volt & ((over0 <= TOL_PU) | (over1 >= over0 + AGGRAVATION_PU))
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
        features=feats,
        labels=labels,
        lost_load_mw=lost,
        ac_n1_seconds=ac_s,
        feature_seconds=feat_s,
        **base,
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
        rec = {
            "op_id": op_id,
            "network": prep.name,
            "seed": seed,
            "load_factor": r.load_factor,
            "sampled_branch_limit_fraction": r.sampled_branch_limit_fraction,
            "status": r.status,
            "opf_attempts": r.opf_attempts,
            "opf_seconds": r.opf_seconds,
        }
        if r.status != STATUS_OPF_FAILED:
            rec.update(
                gen_q_outside_limits=r.gen_q_outside_limits,
                branch_limit_fraction=r.branch_limit_fraction,
                voltage_margin_pu=r.voltage_margin_pu,
            )
        if r.status not in (STATUS_OPF_FAILED, STATUS_BASE_PF_FAILED):
            rec.update(
                base_max_loading_pct=r.base_max_loading_pct,
                base_max_voltage_excess_pu=r.base_max_voltage_excess_pu,
                base_thermal_violations=r.base_thermal_violations,
                base_voltage_violations=r.base_voltage_violations,
            )
        if r.ok:
            rec.update(
                ac_n1_seconds=r.ac_n1_seconds,
                feature_seconds=r.feature_seconds,
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
        log(
            f"{prep.name} {i + 1}/{len(seeds)} seed={seed} {r.status} s={r.load_factor:.3f} "
            f"pos={rec.get('positives', '-')} t={rec.get('ac_n1_seconds', float('nan')):.1f}s"
        )
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
