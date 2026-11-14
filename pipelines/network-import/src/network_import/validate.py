"""Dataset validation: schema, checksums, ids, bus references, connectivity, ranges, PyPSA
consistency and (PGLib) source round trip with a DC power flow.

Islands / sub-networks are reported, never hidden or "fixed". Each report is
``{"network_id", "errors": [...], "warnings": [...], "info": {...}}``; any error fails the CLI.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pypsa
from canonical_grid import load_canonical, load_catalog, load_manifest

from network_import.manifest import MAX_NETCDF_BYTES, file_entries
from network_import.matpower import parse_matpower
from network_import.paths import networks_dir

# canonical list -> PyPSA component list name
_PYPSA_LISTS = {
    "buses": "buses",
    "lines": "lines",
    "transformers": "transformers",
    "links": "links",
    "generators": "generators",
    "loads": "loads",
    "storage_units": "storage_units",
    "stores": "stores",
    "carriers": "carriers",
}
_BRANCH_LISTS = ("lines", "transformers", "links")


class _Collect(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage().strip().splitlines()[0][:300])


def _consistency(n: pypsa.Network) -> list[str]:
    handler = _Collect()
    log = logging.getLogger("pypsa")
    log.addHandler(handler)
    try:
        n.consistency_check(
            strict=["unknown_buses", "dispatch_delays", "maintenance", "phase_shift_bounds"]
        )
    finally:
        log.removeHandler(handler)
    return handler.messages


def _connectivity(n: pypsa.Network) -> dict[str, Any]:
    n.determine_network_topology()
    buses = n.c.buses.static
    sizes = buses.groupby("sub_network").size().sort_values(ascending=False)
    connected: set[str] = set()
    for comp in _BRANCH_LISTS:
        df = getattr(n.c, comp).static
        connected.update(df.bus0.astype(str))
        connected.update(df.bus1.astype(str))
    isolated = sorted(set(map(str, buses.index)) - connected)
    return {
        "sub_networks": int(len(sizes)),
        "sub_network_bus_counts": [int(v) for v in sizes.to_numpy()],
        "isolated_buses": isolated,
    }


def _ranges(n: pypsa.Network) -> list[str]:
    errs = []
    c = n.c
    if (c.buses.static.v_nom <= 0).any():
        errs.append(
            "buses with v_nom <= 0: "
            + ", ".join(c.buses.static.index[c.buses.static.v_nom <= 0][:10])
        )
    for comp, col in (
        ("lines", "s_nom"),
        ("transformers", "s_nom"),
        ("links", "p_nom"),
        ("generators", "p_nom"),
        ("storage_units", "p_nom"),
        ("stores", "e_nom"),
    ):
        df = getattr(c, comp).static
        if len(df) and (df[col] < 0).any():
            errs.append(f"{comp} with negative {col}: {list(df.index[df[col] < 0][:10])}")
    for comp, cols in (
        ("links", ("efficiency",)),
        ("storage_units", ("efficiency_store", "efficiency_dispatch")),
    ):
        df = getattr(c, comp).static
        for col in cols:
            if len(df):
                bad = df.index[(df[col] <= 0) | (df[col] > 1)]
                if len(bad):
                    errs.append(f"{comp}.{col} outside (0,1]: {list(bad[:10])}")
    for comp in ("lines", "transformers"):
        df = getattr(c, comp).static
        if len(df) and ((df.x == 0) & (df.r == 0) & (df.get("type", "") == "")).any():
            errs.append(f"{comp} with zero impedance (x = r = 0, no type)")
    return errs


def _pglib_roundtrip(
    d: Path, n: pypsa.Network, canonical, powerflow: bool
) -> tuple[list[str], dict[str, Any]]:
    errs: list[str] = []
    srcs = [p for p in (d / "source").glob("*.m")]
    if len(srcs) != 1:
        return [f"expected exactly one MATPOWER source in source/, found {len(srcs)}"], {}
    case = parse_matpower(srcs[0])
    n_branch = len(canonical.lines) + len(canonical.transformers)
    expected = {
        "buses": len(case.bus),
        "branches": len(case.branch),
        "generators": len(case.gen),
        "loads": sum(1 for b in case.bus if b["pd"] != 0 or b["qd"] != 0),
    }
    got = {
        "buses": len(canonical.buses),
        "branches": n_branch,
        "generators": len(canonical.generators),
        "loads": len(canonical.loads),
    }
    for k, v in expected.items():
        if got[k] != v:
            errs.append(f"{k}: canonical has {got[k]}, source {srcs[0].name} has {v}")
    info: dict[str, Any] = {"source_counts": expected, "canonical_counts": got}
    pd_total = sum(b["pd"] for b in case.bus)
    pg_total = sum(g["pg"] for g in case.gen if int(g["status"]) != 0)
    info["source_total_pd_mw"] = round(pd_total, 6)
    info["source_total_pg_mw"] = round(pg_total, 6)
    # PGLib Pg is an initial point, not a solved dispatch: Pg - Pd is a mismatch, not AC losses.
    info["source_pg_minus_pd_mw"] = round(pg_total - pd_total, 6)
    if powerflow:
        m = n.copy()
        m.lpf()
        gen_p = float(m.c.generators.dynamic["p"].iloc[0].sum())
        load_p = float(m.c.loads.dynamic["p"].iloc[0].sum())
        sh = m.c.shunt_impedances.dynamic.get("p")
        shunt_p = float(sh.iloc[0].sum()) if sh is not None and not sh.empty else 0.0
        imbalance = gen_p - load_p - shunt_p
        slack = m.c.generators.static.index[m.c.generators.static.control == "Slack"]
        slack_dp = float(
            (m.c.generators.dynamic["p"].iloc[0][slack] - m.c.generators.static.p_set[slack]).sum()
        )
        info["dc_powerflow"] = {
            "total_generation_mw": round(gen_p, 6),
            "total_load_mw": round(load_p, 6),
            "total_shunt_mw": round(shunt_p, 6),
            "imbalance_mw": round(imbalance, 9),
            "slack_adjustment_mw": round(slack_dp, 6),
            "max_abs_angle_rad": round(float(np.abs(m.c.buses.dynamic["v_ang"].iloc[0]).max()), 6),
        }
        if abs(imbalance) > 1e-6 * max(1.0, load_p):
            errs.append(f"DC power flow imbalance {imbalance:.6g} MW (gen != load + shunt)")
        if abs(slack_dp + (pg_total - pd_total)) > 1e-6 * max(1.0, load_p) + abs(shunt_p):
            errs.append(
                f"slack adjustment {slack_dp:.6g} MW != -(source Pg - Pd) "
                f"{-(pg_total - pd_total):.6g} MW"
            )
    return errs, info


def validate_dataset(d: Path, *, powerflow: bool = True) -> dict[str, Any]:
    rep: dict[str, Any] = {"network_id": d.name, "errors": [], "warnings": [], "info": {}}
    errors, warnings, info = rep["errors"], rep["warnings"], rep["info"]
    try:
        canonical = load_canonical(d / "canonical.json")  # ids, bus refs, summary, provenance keys
        manifest = load_manifest(d / "manifest.json")
    except Exception as e:  # noqa: BLE001 - report every schema failure, do not crash
        errors.append(f"schema: {e}")
        return rep
    if canonical.network_id != d.name or manifest.network_id != d.name:
        errors.append("network_id does not match directory name")

    listed = {f.path: (f.sha256, f.bytes) for f in manifest.files}
    actual = {f["path"]: (f["sha256"], f["bytes"]) for f in file_entries(d)}
    for path in sorted(set(listed) | set(actual)):
        if path not in actual:
            errors.append(f"manifest lists missing file {path}")
        elif path not in listed:
            errors.append(f"file {path} not listed in manifest")
        elif listed[path] != actual[path]:
            errors.append(f"checksum/size mismatch for {path}")

    nc = d / "network.nc"
    if not nc.exists():
        errors.append("network.nc missing")
        return rep
    if nc.stat().st_size > MAX_NETCDF_BYTES:
        errors.append(f"network.nc is {nc.stat().st_size} bytes > 10 MB")
    n = pypsa.Network(nc)

    for comp, plist in _PYPSA_LISTS.items():
        nc_ids = sorted(map(str, getattr(n.c, plist).static.index))
        can_ids = sorted(r.id for r in getattr(canonical, comp))
        if nc_ids != can_ids:
            errors.append(
                f"{comp}: ids differ between network.nc ({len(nc_ids)}) and "
                f"canonical.json ({len(can_ids)})"
            )
    seen: dict[str, str] = {}
    collisions = set()
    for comp in ("lines", "transformers", "links"):
        for r in getattr(canonical, comp):
            if r.id in seen and seen[r.id] != comp:
                collisions.add(r.id)
            seen.setdefault(r.id, comp)
    if collisions:
        warnings.append(
            f"{len(collisions)} branch ids appear in more than one component list "
            "(ids are unique per list only; line_outage must set component)"
        )
        if "cross_component_id_collision" not in manifest.quality_flags:
            errors.append(
                "cross-list id collisions present but quality flag "
                "'cross_component_id_collision' missing"
            )

    errors.extend(_ranges(n))
    try:
        warnings.extend(f"consistency_check: {m}" for m in _consistency(n))
    except Exception as e:  # noqa: BLE001
        errors.append(f"consistency_check (strict): {e}")
    conn = _connectivity(n)
    info["connectivity"] = conn
    if conn["sub_networks"] > 1:
        warnings.append(
            f"{conn['sub_networks']} sub-networks (islands/DC parts): bus counts "
            f"{conn['sub_network_bus_counts'][:20]}"
        )
    if conn["isolated_buses"]:
        warnings.append(
            f"{len(conn['isolated_buses'])} buses without any branch: {conn['isolated_buses'][:20]}"
        )

    if d.name.startswith("pglib-"):
        errs, pinfo = _pglib_roundtrip(d, n, canonical, powerflow)
        errors.extend(errs)
        info["pglib"] = pinfo
    return rep


def validate_all(ids: list[str] | None = None, *, powerflow: bool = True) -> list[dict[str, Any]]:
    root = networks_dir()
    catalog = load_catalog(root / "catalog.json")
    catalog_ids = [e.id for e in catalog.networks]
    reports = []
    for nid in ids or catalog_ids:
        rep = validate_dataset(root / nid, powerflow=powerflow)
        if nid not in catalog_ids:
            rep["errors"].append("not listed in data/networks/catalog.json")
        reports.append(rep)
    return reports
