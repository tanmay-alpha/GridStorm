"""MATPOWER / PGLib case loading with an explicit GridStorm id map.

Contract ids (same as ``pipelines/network-import`` and ``packages/stormbench``):

* buses ``bus-<BUS_I>`` (pandapower bus index == ``BUS_I``),
* branches ``branch-<1-based row in mpc.branch>``; component ``transformer`` when the off-nominal
  ratio is not in {0, 1}, the phase shift is non-zero or the two ends have different ``baseKV``,
  else ``line``. pandapower may represent a contract ``line`` as ``line`` or ``impedance`` (equal
  ratio but different ``baseKV``) and a ``transformer`` as ``trafo`` or ``impedance``,
* generators ``gen-<1-based row in mpc.gen>`` -> pandapower ``ext_grid`` | ``gen`` | ``sgen``,
* loads ``load-<BUS_I>`` for every bus with ``Pd != 0`` or ``Qd != 0`` (negative ``Pd`` is kept as
  a load with negative ``p_mw``; pandapower's converter would otherwise turn it into an sgen).

The converter is :func:`pandapower.converter.pypower.from_ppc.from_ppc`; its ``_from_ppc_lookups``
give the row -> element mapping, which is stored here and never re-derived from names.
"""

from __future__ import annotations

import copy
import logging
import math
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandapower as pp
from matpowercaseframes import CaseFrames
from pandapower.converter.pypower.from_ppc import from_ppc

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_DATA = PACKAGE_ROOT / "reference_data"

#: GridStorm network id -> PGLib file name (vendored copy in reference_data/pglib).
PGLIB_FILES: dict[str, str] = {
    "pglib-case14-ieee": "pglib_opf_case14_ieee.m",
    "pglib-case118-ieee": "pglib_opf_case118_ieee.m",
    "pglib-case300-ieee": "pglib_opf_case300_ieee.m",
}

DEFAULT_VM_MIN_PU = 0.94
DEFAULT_VM_MAX_PU = 1.06

# MATPOWER column indices (0-based)
BUS_I, BUS_TYPE, PD, QD, GS, BS, VM, VA, BASE_KV, VMAX, VMIN = 0, 1, 2, 3, 4, 5, 7, 8, 9, 11, 12
F_BUS, T_BUS, RATE_A, TAP, SHIFT, BR_STATUS = 0, 1, 5, 8, 9, 10
GEN_BUS, PG, PMAX = 0, 1, 8

_PPC_ARRAYS = ("bus", "gen", "branch", "gencost")


@dataclass(frozen=True)
class BranchRef:
    id: str
    component: str  # contract component: "line" | "transformer"
    table: str  # pandapower table: "line" | "trafo" | "impedance"
    index: int
    from_bus: str
    to_bus: str
    rate_a_mva: float | None  # None = unlimited (RATE_A == 0)


@dataclass(frozen=True)
class GenRef:
    id: str
    table: str  # "ext_grid" | "gen" | "sgen"
    index: int
    bus: str


@dataclass
class GridModel:
    """A pandapower net plus the bidirectional contract id map."""

    network_id: str
    net: pp.pandapowerNet
    ppc: dict
    source_path: Path | None
    buses: list[str]
    branches: list[BranchRef]
    gens: list[GenRef]
    loads: dict[str, int]  # load id -> pandapower load index
    vm_limits: dict[str, tuple[float, float]]  # bus id -> (vmin, vmax)
    vm_limits_source: str
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._branch_by_key = {(b.component, b.id): b for b in self.branches}
        self._branch_by_element = {(b.table, b.index): b for b in self.branches}
        self._gen_by_id = {g.id: g for g in self.gens}
        self._gen_by_element = {(g.table, g.index): g for g in self.gens}
        self._load_by_index = {v: k for k, v in self.loads.items()}

    # -- id map ---------------------------------------------------------------------------
    def branch(self, asset_id: str, component: str = "line") -> BranchRef:
        try:
            return self._branch_by_key[(component, asset_id)]
        except KeyError:
            raise KeyError(f"no {component} with id {asset_id!r} in {self.network_id}") from None

    def branch_for_element(self, table: str, index: int) -> BranchRef:
        return self._branch_by_element[(table, int(index))]

    def gen(self, asset_id: str) -> GenRef:
        try:
            return self._gen_by_id[asset_id]
        except KeyError:
            raise KeyError(f"no generator with id {asset_id!r} in {self.network_id}") from None

    def gen_for_element(self, table: str, index: int) -> GenRef:
        return self._gen_by_element[(table, int(index))]

    def load_id_for_index(self, index: int) -> str:
        return self._load_by_index[int(index)]

    @staticmethod
    def bus_id(bus_index: int) -> str:
        return f"bus-{int(bus_index)}"

    @staticmethod
    def bus_index(bus_id: str) -> int:
        if not bus_id.startswith("bus-"):
            raise KeyError(f"not a bus id: {bus_id!r}")
        return int(bus_id[4:])

    def copy(self) -> GridModel:
        """Deep copy of the network; the (immutable) id map is shared."""
        clone = copy.copy(self)
        clone.net = copy.deepcopy(self.net)
        return clone

    # -- canonical view for stormspec.validate ---------------------------------------------
    def canonical_index(self) -> dict:
        """Minimal canonical-grid/1.0-shaped dict (ids only) for :func:`stormspec.validate`."""
        load_bus = {lid: f"bus-{lid[5:]}" for lid in self.loads}
        return {
            "schema_version": "canonical-grid/1.0",
            "network_id": self.network_id,
            "snapshots": {"count": 1},
            "buses": [{"id": b} for b in self.buses],
            "lines": [{"id": b.id} for b in self.branches if b.component == "line"],
            "transformers": [{"id": b.id} for b in self.branches if b.component == "transformer"],
            "links": [],
            "generators": [{"id": g.id, "bus": g.bus, "is_variable": False} for g in self.gens],
            "loads": [{"id": lid, "bus": bus} for lid, bus in load_bus.items()],
            "storage_units": [],
            "stores": [],
            "carriers": [],
        }


def read_mpc(path: str | Path) -> dict:
    """Parse a MATPOWER ``.m`` case into a PYPOWER-style dict of float arrays."""
    cf = CaseFrames(str(path))
    ppc: dict = {}
    for key in cf._attributes:
        value = getattr(cf, key)
        if key in _PPC_ARRAYS:
            ppc[key] = np.array(value.values if hasattr(value, "values") else value, dtype=float)
        else:
            ppc[key] = value
    ppc["baseMVA"] = float(ppc["baseMVA"])
    ppc["version"] = str(ppc.get("version", "2"))
    return ppc


def branch_components(ppc: dict) -> list[str]:
    """Contract component per branch row (see module docstring)."""
    kv = dict(zip(ppc["bus"][:, BUS_I].astype(int), ppc["bus"][:, BASE_KV], strict=True))
    out = []
    for row in ppc["branch"]:
        ratio, shift = row[TAP], row[SHIFT]
        kv_differs = kv[int(row[F_BUS])] != kv[int(row[T_BUS])]
        is_trafo = (ratio not in (0.0, 1.0)) or shift != 0.0 or kv_differs
        out.append("transformer" if is_trafo else "line")
    return out


def model_from_ppc(ppc: dict, network_id: str, source_path: Path | None = None) -> GridModel:
    """Convert a PYPOWER case dict to pandapower and build the id map."""
    ppc = copy.deepcopy(ppc)
    notes: list[str] = []
    bus = ppc["bus"]
    zero_kv = bus[:, BASE_KV] <= 0
    components = branch_components(ppc)  # before any baseKV patch: same rule as the importer
    if zero_kv.any():
        # Per-unit impedances do not depend on baseKV; pandapower needs a positive voltage level.
        bus[zero_kv, BASE_KV] = 1.0
        notes.append(
            f"{int(zero_kv.sum())} bus(es) with baseKV <= 0 converted with baseKV = 1 kV "
            "(per-unit model unchanged)"
        )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        logging.getLogger("pandapower").setLevel(logging.ERROR)
        net = from_ppc(ppc, f_hz=60, validate_conversion=False, check_costs=False)
    lookups = net._from_ppc_lookups

    # Loads: replace converter loads + negative-Pd sgens by one load per contract load id.
    neg_sgen = net.sgen.index[: int((bus[:, PD] < 0).sum())]
    gen_sgens = set(lookups["gen"].loc[lookups["gen"].element_type == "sgen", "element"].astype(int))
    assert not (set(neg_sgen) & gen_sgens), "negative-load sgens must precede generator sgens"
    net.sgen.drop(index=neg_sgen, inplace=True)
    net.load.drop(index=net.load.index, inplace=True)
    loads: dict[str, int] = {}
    for row in bus:
        if row[PD] != 0 or row[QD] != 0:
            b = int(row[BUS_I])
            loads[f"load-{b}"] = int(pp.create_load(net, bus=b, p_mw=row[PD], q_mvar=row[QD]))

    buses = [f"bus-{int(b)}" for b in bus[:, BUS_I]]
    branches = []
    for r, (et, el) in enumerate(
        zip(lookups["branch"].element_type, lookups["branch"].element, strict=True)
    ):
        br = ppc["branch"][r]
        rate = float(br[RATE_A])
        branches.append(
            BranchRef(
                id=f"branch-{r + 1}",
                component=components[r],
                table=str(et),
                index=int(el),
                from_bus=f"bus-{int(br[F_BUS])}",
                to_bus=f"bus-{int(br[T_BUS])}",
                rate_a_mva=rate if rate > 0 else None,
            )
        )
    gens = [
        GenRef(
            id=f"gen-{r + 1}",
            table=str(et),
            index=int(el),
            bus=f"bus-{int(ppc['gen'][r, GEN_BUS])}",
        )
        for r, (et, el) in enumerate(
            zip(lookups["gen"].element_type, lookups["gen"].element, strict=True)
        )
    ]
    vmin, vmax = bus[:, VMIN], bus[:, VMAX]
    valid = (vmin > 0) & (vmax > vmin)
    vm_limits = {
        f"bus-{int(b)}": (float(lo), float(hi)) if ok else (DEFAULT_VM_MIN_PU, DEFAULT_VM_MAX_PU)
        for b, lo, hi, ok in zip(bus[:, BUS_I], vmin, vmax, valid, strict=True)
    }
    if valid.all():
        vm_source = "case file VMIN/VMAX per bus"
    elif not valid.any():
        vm_source = f"default [{DEFAULT_VM_MIN_PU}, {DEFAULT_VM_MAX_PU}] pu (case has none)"
    else:
        vm_source = (
            f"case file VMIN/VMAX; default [{DEFAULT_VM_MIN_PU}, {DEFAULT_VM_MAX_PU}] pu for "
            f"{int((~valid).sum())} bus(es) without valid limits"
        )
    return GridModel(
        network_id=network_id,
        net=net,
        ppc=ppc,
        source_path=source_path,
        buses=buses,
        branches=branches,
        gens=gens,
        loads=loads,
        vm_limits=vm_limits,
        vm_limits_source=vm_source,
        notes=notes,
    )


def load_matpower(path: str | Path, network_id: str) -> GridModel:
    path = Path(path)
    return model_from_ppc(read_mpc(path), network_id, source_path=path)


def resolve_case_file(network_id: str, network_dir: str | Path | None = None) -> Path:
    """MATPOWER source for ``network_id``: ``<network_dir>/source/*.m``, else the vendored PGLib copy."""
    if network_dir is not None:
        src = Path(network_dir) / "source"
        found = sorted(src.glob("*.m")) if src.is_dir() else []
        if len(found) == 1:
            return found[0]
        if len(found) > 1:
            raise ValueError(f"ambiguous MATPOWER sources in {src}: {[p.name for p in found]}")
    name = PGLIB_FILES.get(network_id)
    if name is None:
        raise FileNotFoundError(
            f"network {network_id!r} has no MATPOWER/PGLib source; the pandapower engine only "
            "supports MATPOWER cases"
        )
    return REFERENCE_DATA / "pglib" / name


def is_finite(x: float | None) -> bool:
    return x is not None and math.isfinite(x)
