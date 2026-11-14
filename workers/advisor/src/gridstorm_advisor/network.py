"""Advisor network model: a pandapower net plus the GridStorm asset-id mapping and cost data.

Asset ids follow the GridStorm contract for MATPOWER/PGLib-derived networks:
``bus-<BUS_I>``, ``branch-<1-based row in mpc.branch>``, ``gen-<1-based row in mpc.gen>``,
``load-<BUS_I>``. pandapower built-in cases use ``bus-<idx>``, ``line-<idx>``, ``trafo-<idx>``,
``gen-<idx>``, ``ext_grid-<idx>``, ``load-<idx>`` (pandapower table indices, NOT MATPOWER rows).
"""

from __future__ import annotations

import copy
import hashlib
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandapower as pp

from gridstorm_advisor.matpower import read_case

# MATPOWER column indices (MATPOWER manual, Appendix B).
_BUS_I, _BUS_TYPE, _PD, _QD = 0, 1, 2, 3
_GEN_BUS, _PG, _GEN_STATUS, _PMAX, _PMIN = 0, 1, 7, 8, 9
_RATE_A = 5
_MODEL, _NCOST = 0, 3


@dataclass(frozen=True)
class ElementRef:
    """Reference to a pandapower element: table name and index."""

    table: str
    index: int


@dataclass
class CostCurve:
    """MATPOWER gencost row: model 2 (polynomial, highest order first) or 1 (piecewise linear)."""

    model: int
    params: tuple[float, ...]

    def __call__(self, p_mw: float) -> float:
        if self.model == 2:
            return float(np.polyval(np.asarray(self.params), p_mw))
        if self.model == 1:
            xs = np.asarray(self.params[0::2])
            ys = np.asarray(self.params[1::2])
            if p_mw <= xs[0]:
                slope = (ys[1] - ys[0]) / (xs[1] - xs[0])
                return float(ys[0] + slope * (p_mw - xs[0]))
            if p_mw >= xs[-1]:
                slope = (ys[-1] - ys[-2]) / (xs[-1] - xs[-2])
                return float(ys[-1] + slope * (p_mw - xs[-1]))
            return float(np.interp(p_mw, xs, ys))
        raise ValueError(f"unsupported gencost model {self.model}")

    def marginal(self, p_mw: float) -> float:
        eps = 1e-3
        return (self(p_mw + eps) - self(p_mw - eps)) / (2 * eps)


@dataclass
class AdvisorNetwork:
    """A pandapower net with GridStorm ids. ``net`` is never mutated by the advisor."""

    network_id: str
    net: pp.pandapowerNet
    buses: dict[str, int]
    branches: dict[str, ElementRef]
    generators: dict[str, ElementRef]
    loads: dict[str, list[int]]
    branch_rating_mva: dict[str, float | None]
    gen_cost: dict[str, CostCurve] = field(default_factory=dict)
    loading_basis: str = "apparent_power_vs_rate_a"
    source_files: list[dict] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    operating_point: dict = field(
        default_factory=lambda: {"method": "setpoints stored in the network data"}
    )

    def copy_net(self) -> pp.pandapowerNet:
        return copy.deepcopy(self.net)

    def bus_id_of(self, pp_bus: int) -> str:
        return self._bus_ids[int(pp_bus)]

    def __post_init__(self) -> None:
        self._bus_ids = {v: k for k, v in self.buses.items()}
        self._branch_ids = {(r.table, r.index): k for k, r in self.branches.items()}
        self._gen_ids = {(r.table, r.index): k for k, r in self.generators.items()}

    def branch_id_of(self, table: str, index: int) -> str:
        return self._branch_ids[(table, int(index))]

    def gen_id_of(self, table: str, index: int) -> str:
        return self._gen_ids[(table, int(index))]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_matpower(path: str | Path, network_id: str) -> AdvisorNetwork:
    """Build an AdvisorNetwork from a MATPOWER/PGLib ``.m`` file using contract asset ids."""
    from pandapower.converter.pypower.from_ppc import from_ppc

    path = Path(path)
    mpc = read_case(path)
    ppc = {k: mpc[k] for k in ("version", "baseMVA", "bus", "gen", "branch")}
    if "gencost" in mpc:
        ppc["gencost"] = mpc["gencost"]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        net = from_ppc(copy.deepcopy(ppc), f_hz=60, check_costs=False)
    lookups = net._from_ppc_lookups

    bus_ids = {f"bus-{int(b)}": int(b) for b in mpc["bus"][:, _BUS_I]}

    branches: dict[str, ElementRef] = {}
    ratings: dict[str, float | None] = {}
    for row, (etype, element) in enumerate(
        zip(lookups["branch"]["element_type"], lookups["branch"]["element"], strict=True)
    ):
        if etype not in ("line", "trafo", "impedance"):
            raise ValueError(f"{path}: branch row {row + 1} converted to unsupported {etype!r}")
        bid = f"branch-{row + 1}"
        branches[bid] = ElementRef(str(etype), int(element))
        rate = float(mpc["branch"][row, _RATE_A])
        ratings[bid] = rate if rate > 0 else None  # MATPOWER: rateA == 0 means unlimited

    generators: dict[str, ElementRef] = {}
    for row, (etype, element) in enumerate(
        zip(lookups["gen"]["element_type"], lookups["gen"]["element"], strict=True)
    ):
        generators[f"gen-{row + 1}"] = ElementRef(str(etype), int(element))

    loads: dict[str, list[int]] = {}
    for idx, bus in zip(net.load.index, net.load.bus, strict=True):
        loads.setdefault(f"load-{int(bus)}", []).append(int(idx))

    costs: dict[str, CostCurve] = {}
    if "gencost" in mpc:
        gc = mpc["gencost"]
        for row in range(min(len(gc), len(mpc["gen"]))):
            n = int(gc[row, _NCOST])
            model = int(gc[row, _MODEL])
            width = n if model == 2 else 2 * n
            costs[f"gen-{row + 1}"] = CostCurve(model, tuple(float(v) for v in gc[row, 4:4 + width]))

    return AdvisorNetwork(
        network_id=network_id,
        net=net,
        buses=bus_ids,
        branches=branches,
        generators=generators,
        loads=loads,
        branch_rating_mva=ratings,
        gen_cost=costs,
        loading_basis="apparent_power_vs_rate_a",
        source_files=[{"path": path.name, "sha256": _sha256(path)}],
        assumptions=[
            "Network converted from the MATPOWER case with pandapower.converter.from_ppc (f_hz=60).",
            "Generator active-power setpoints are the Pg values stored in the case file "
            "(an operating point, not an optimised dispatch).",
            "Branch loading = max(|S_from|, |S_to|) / rateA (MVA), MATPOWER convention; "
            "rateA == 0 is treated as unlimited.",
            "Bus voltage limits are the VMIN/VMAX columns of the case file.",
        ],
    )


def find_matpower_source(network_dir: str | Path) -> Path:
    """Return the single ``source/*.m`` file of a GridStorm network directory."""
    files = sorted(Path(network_dir, "source").glob("*.m"))
    if len(files) != 1:
        raise FileNotFoundError(
            f"expected exactly one MATPOWER file in {Path(network_dir, 'source')}, found {len(files)}"
        )
    return files[0]


def set_opf_operating_point(adv: AdvisorNetwork) -> dict:
    """Replace the stored generator setpoints by a pandapower AC-OPF (PIPS) dispatch of the
    pre-crisis case: cost-minimal P and voltage setpoints respecting branch limits
    (max_loading_percent=100), bus voltage limits and generator P/Q limits.

    PGLib ``.m`` files store Pg/Vg values that are NOT a feasible operating point (e.g. the
    pglib_opf_case118_ieee slack exceeds its Pmax at the stored Pg), so a defensible pre-crisis
    state needs a dispatch. Mutates ``adv.net`` and returns a description for the artifact.

    pandapower's OPF limits branch CURRENT (``max_i_ka`` derived from rateA at 1.0 p.u.), while
    MATPOWER rateA is an MVA limit: at |V| = 1.06 p.u. a current-feasible branch carries 106 % of
    rateA. Each branch's ``max_loading_percent`` is therefore set to 100 / max(VMAX of its
    terminal buses), which guarantees |S| <= rateA (conservative when |V| < VMAX).
    """
    work = copy.deepcopy(adv.net)
    vmax = work.bus.max_vm_pu
    work.line["max_loading_percent"] = 100.0 / np.maximum(
        vmax.loc[work.line.from_bus].to_numpy(), vmax.loc[work.line.to_bus].to_numpy()
    )
    if len(work.trafo):
        work.trafo["max_loading_percent"] = 100.0 / np.maximum(
            vmax.loc[work.trafo.hv_bus].to_numpy(), vmax.loc[work.trafo.lv_bus].to_numpy()
        )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        pp.runopp(work, calculate_voltage_angles=True, init="flat")
    if not work.OPF_converged:
        raise RuntimeError(f"{adv.network_id}: AC-OPF for the operating point did not converge")
    net = adv.net
    for idx in net.gen.index:
        net.gen.at[idx, "p_mw"] = float(work.res_gen.at[idx, "p_mw"])
        net.gen.at[idx, "vm_pu"] = float(work.res_gen.at[idx, "vm_pu"])
    for idx in net.ext_grid.index:
        bus = int(net.ext_grid.at[idx, "bus"])
        net.ext_grid.at[idx, "vm_pu"] = float(work.res_bus.at[bus, "vm_pu"])
    info = {
        "method": "pandapower.runopp (PIPS interior point, AC-OPF, pre-crisis case)",
        "branch_limit": "max_loading_percent = 100 / max(VMAX of terminal buses) so that "
                        "|S| <= rateA (pandapower limits current)",
        "objective_eur_per_h": round(float(work.res_cost), 2),
        "pandapower_version": pp.__version__,
    }
    adv.operating_point = info
    adv.assumptions.append(
        "Pre-crisis operating point = pandapower AC-OPF dispatch of the uncontingented case "
        f"(objective {info['objective_eur_per_h']} EUR/h, generator P and V setpoints); the case "
        "file Pg/Vg are not used. OPF branch limits tightened to 100/VMAX % of current rating so "
        "the MVA rating holds."
    )
    return info


def from_pandapower(
    net: pp.pandapowerNet,
    network_id: str,
    *,
    gen_cost: dict[str, CostCurve] | None = None,
    branch_rating_mva: dict[str, float | None] | None = None,
) -> AdvisorNetwork:
    """Wrap a pandapower net with table-based ids (built-in cases, constructed test networks).

    If ``branch_rating_mva`` is omitted, branch loading uses pandapower's ``loading_percent``
    (current-based for lines, apparent power vs ``sn_mva`` for transformers).
    """
    branches = {f"line-{int(i)}": ElementRef("line", int(i)) for i in net.line.index}
    branches.update({f"trafo-{int(i)}": ElementRef("trafo", int(i)) for i in net.trafo.index})
    generators = {f"ext_grid-{int(i)}": ElementRef("ext_grid", int(i)) for i in net.ext_grid.index}
    generators.update({f"gen-{int(i)}": ElementRef("gen", int(i)) for i in net.gen.index})
    if gen_cost is None:
        gen_cost = {}
        if "poly_cost" in net and len(net.poly_cost):
            for _, row in net.poly_cost.iterrows():
                gid = f"{row['et']}-{int(row['element'])}"
                if gid in generators:
                    gen_cost[gid] = CostCurve(
                        2,
                        (
                            float(row["cp2_eur_per_mw2"]),
                            float(row["cp1_eur_per_mw"]),
                            float(row["cp0_eur"]),
                        ),
                    )
    basis = "apparent_power_vs_rate_a" if branch_rating_mva is not None else "pandapower_loading_percent"
    return AdvisorNetwork(
        network_id=network_id,
        net=net,
        buses={f"bus-{int(i)}": int(i) for i in net.bus.index},
        branches=branches,
        generators=generators,
        loads={f"load-{int(i)}": [int(i)] for i in net.load.index},
        branch_rating_mva=branch_rating_mva or {b: None for b in branches},
        gen_cost=gen_cost,
        loading_basis=basis,
        assumptions=[
            "pandapower table-index asset ids (line-/trafo-/gen-/ext_grid-/load-<index>)."
        ],
    )


def load_pandapower_case(name: str) -> AdvisorNetwork:
    """Load a pandapower built-in case, e.g. ``case14`` or ``case118``."""
    import pandapower.networks as pn

    fn = getattr(pn, name, None)
    if fn is None or not name.startswith("case"):
        raise ValueError(f"unknown pandapower built-in case {name!r}")
    adv = from_pandapower(fn(), f"pandapower-{name}")
    adv.assumptions.append(
        f"pandapower built-in {name}; ratings as shipped by pandapower (may be placeholders)."
    )
    return adv
