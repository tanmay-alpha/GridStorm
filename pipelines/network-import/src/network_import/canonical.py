"""Convert a PyPSA network into a validated ``canonical-grid/1.0`` model.

``from_pypsa`` is the single conversion path used by every importer (and by the PyPSA-Eur builder),
so all networks share identical semantics:

* asset ids are the PyPSA component names, as strings, unchanged;
* values listed in ``null_fields`` (``"<component>.<field>"``) are emitted as ``null`` because the
  source does not provide them and PyPSA only holds a default (e.g. ``lines.length_km`` = 0);
* NaN/inf and empty strings become ``null``;
* line ``x_ohm``/``r_ohm`` are the effective series impedances after PyPSA applies standard line
  types (``calculate_dependent_values``), i.e. what the power-flow equations use;
* load statistics are calculated from the dense ``p_set`` series and generator snapshot weightings.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd
import pypsa
from canonical_grid import CanonicalNetwork, Provenance

COMPONENT_LISTS = (
    "buses", "lines", "transformers", "links", "generators", "loads", "storage_units", "stores",
    "carriers",
)

# Fields derived by this module from other data; always labelled `calculated`.
CALCULATED_FIELDS: dict[str, Provenance] = {
    "lines.v_nom_kv": "calculated",
    "loads.p_peak_mw": "calculated",
    "loads.p_mean_mw": "calculated",
    "loads.energy_mwh": "calculated",
    "generators.is_variable": "calculated",
}


def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _str(v: Any) -> str | None:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    s = str(v)
    return s if s.strip() else None


def _bool(v: Any) -> bool | None:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return bool(v)


def _rows(df: pd.DataFrame, comp: str, spec: Mapping[str, tuple[str, Any]],
          nulls: set[str]) -> list[dict[str, Any]]:
    """Build canonical rows. ``spec`` maps canonical field -> (pypsa column, converter)."""
    out = []
    for name, row in df.iterrows():
        rec: dict[str, Any] = {"id": str(name)}
        for field, (col, conv) in spec.items():
            if f"{comp}.{field}" in nulls or col not in df.columns:
                rec[field] = None
            else:
                rec[field] = conv(row[col])
        out.append(rec)
    return out


def _snapshots(n: pypsa.Network) -> dict[str, Any]:
    snaps = n.snapshots
    if isinstance(snaps, pd.MultiIndex):
        raise ValueError("multi-period (investment period) networks are not supported")
    w = n.snapshot_weightings["generators"].to_numpy()
    uniform = len(w) > 0 and bool((w == w[0]).all())
    if isinstance(snaps, pd.DatetimeIndex):
        start, end = snaps[0].isoformat(), snaps[-1].isoformat()
    else:
        start = end = None
    return {"count": len(snaps), "start": start, "end": end,
            "resolution_h": float(w[0]) if uniform and w[0] > 0 else None}


def from_pypsa(
    n: pypsa.Network,
    network_id: str,
    name: str,
    *,
    coordinate_kind: str = "geographic",
    crs: str | None = None,
    field_provenance: Mapping[str, Provenance] | None = None,
    assumptions: Iterable[str] = (),
    null_fields: Iterable[str] = (),
    bus_name_column: str | None = None,
) -> CanonicalNetwork:
    """Convert ``n`` to a validated :class:`canonical_grid.CanonicalNetwork`.

    Parameters
    ----------
    coordinate_kind, crs:
        ``"geographic"`` (crs defaults to ``EPSG:<n.srid>``) or ``"schematic"`` (crs must be None).
    field_provenance:
        ``{"<component>.<field>": provenance}`` for source-derived fields. Fields computed here
        (``CALCULATED_FIELDS``) are added automatically unless overridden.
    null_fields:
        ``"<component>.<field>"`` entries the source does not provide; emitted as ``null``.
    bus_name_column:
        Optional static bus column holding a human-readable name.
    """
    nulls = set(null_fields)
    if coordinate_kind == "geographic" and crs is None:
        crs = f"EPSG:{int(n.srid)}"
    if coordinate_kind == "schematic" and crs is not None:
        raise ValueError("schematic coordinates must have crs=None")

    # Effective impedances (line types applied) without mutating the caller's network.
    m = n.copy()
    m.calculate_dependent_values()
    c = m.components

    buses_df = c.buses.static.copy()
    buses_df["_name"] = buses_df[bus_name_column] if bus_name_column else None
    buses = _rows(buses_df, "buses", {
        "name": ("_name", _str), "x": ("x", _num), "y": ("y", _num),
        "v_nom_kv": ("v_nom", _num), "carrier": ("carrier", _str),
        "country": ("country", _str),
    }, nulls)

    lines = _rows(c.lines.static, "lines", {
        "bus0": ("bus0", str), "bus1": ("bus1", str), "v_nom_kv": ("v_nom", _num),
        "s_nom_mva": ("s_nom", _num), "x_ohm": ("x", _num), "r_ohm": ("r", _num),
        "length_km": ("length", _num), "num_parallel": ("num_parallel", _num),
        "carrier": ("carrier", _str),
    }, nulls)

    transformers = _rows(c.transformers.static, "transformers", {
        "bus0": ("bus0", str), "bus1": ("bus1", str), "s_nom_mva": ("s_nom", _num),
        "x_pu": ("x", _num), "r_pu": ("r", _num), "tap_ratio": ("tap_ratio", _num),
    }, nulls)

    links = _rows(c.links.static, "links", {
        "bus0": ("bus0", str), "bus1": ("bus1", str), "p_nom_mw": ("p_nom", _num),
        "efficiency": ("efficiency", _num), "carrier": ("carrier", _str),
    }, nulls)

    gen_df = c.generators.static.copy()
    pmax_t = c.generators.dynamic.get("p_max_pu", pd.DataFrame())
    gen_df["_is_variable"] = gen_df.index.isin(pmax_t.columns)
    generators = _rows(gen_df, "generators", {
        "bus": ("bus", str), "carrier": ("carrier", _str), "p_nom_mw": ("p_nom", _num),
        "marginal_cost_eur_per_mwh": ("marginal_cost", _num),
        "p_nom_extendable": ("p_nom_extendable", _bool), "is_variable": ("_is_variable", bool),
    }, nulls)
    extra_assumptions: list[str] = []
    mc_t = c.generators.dynamic.get("marginal_cost", pd.DataFrame())
    if not mc_t.empty:
        extra_assumptions.append(
            f"{mc_t.shape[1]} generators have time-varying marginal costs; canonical "
            "marginal_cost_eur_per_mwh holds the static value only."
        )

    weights = m.snapshot_weightings["generators"]
    load_df = c.loads.static.copy()
    if len(load_df):
        p = m.get_switchable_as_dense("Load", "p_set")
        load_df["_peak"] = p.max()
        load_df["_mean"] = p.mean()
        load_df["_energy"] = p.mul(weights, axis=0).sum()
        total = p.sum(axis=1)
        peak_load, total_load = float(total.max()), float((total * weights).sum())
    else:
        load_df["_peak"] = load_df["_mean"] = load_df["_energy"] = None
        peak_load = total_load = None
    loads = _rows(load_df, "loads", {
        "bus": ("bus", str), "p_peak_mw": ("_peak", _num), "p_mean_mw": ("_mean", _num),
        "energy_mwh": ("_energy", _num),
    }, nulls)

    storage_units = _rows(c.storage_units.static, "storage_units", {
        "bus": ("bus", str), "carrier": ("carrier", _str), "p_nom_mw": ("p_nom", _num),
        "max_hours": ("max_hours", _num), "efficiency_store": ("efficiency_store", _num),
        "efficiency_dispatch": ("efficiency_dispatch", _num),
    }, nulls)

    stores = _rows(c.stores.static, "stores", {
        "bus": ("bus", str), "carrier": ("carrier", _str), "e_nom_mwh": ("e_nom", _num),
    }, nulls)

    carriers = _rows(c.carriers.static, "carriers", {
        "color": ("color", _str), "co2_emissions_t_per_mwh": ("co2_emissions", _num),
        "nice_name": ("nice_name", _str),
    }, nulls)

    capacity: dict[str, float] = {}
    for df in (c.generators.static, c.storage_units.static):
        if len(df):
            active = df[df["active"]] if "active" in df.columns else df
            for carrier, val in active.groupby("carrier")["p_nom"].sum().items():
                key = str(carrier) or "unspecified"
                capacity[key] = capacity.get(key, 0.0) + float(val)

    inactive = []
    for comp in ("lines", "transformers", "links", "generators", "loads", "storage_units",
                 "stores"):
        df = getattr(c, comp).static
        if "active" in df.columns and (~df["active"].astype(bool)).any():
            ids = [str(i) for i in df.index[~df["active"].astype(bool)]]
            inactive.append(f"{comp}: {', '.join(ids[:20])}{' ...' if len(ids) > 20 else ''}")
    if inactive:
        extra_assumptions.append(
            "Components with active=False are included in canonical lists but excluded from "
            "PyPSA calculations: " + "; ".join(inactive)
        )

    provenance: dict[str, Provenance] = dict(CALCULATED_FIELDS)
    provenance.update(field_provenance or {})
    for key in nulls:
        provenance.pop(key, None)

    data = {
        "network_id": network_id,
        "name": name,
        "coordinate_kind": coordinate_kind,
        "crs": crs,
        "snapshots": _snapshots(m),
        "buses": buses,
        "lines": lines,
        "transformers": transformers,
        "links": links,
        "generators": generators,
        "loads": loads,
        "storage_units": storage_units,
        "stores": stores,
        "carriers": carriers,
        "summary": {
            "counts": {k: len(v) for k, v in {
                "buses": buses, "lines": lines, "transformers": transformers, "links": links,
                "generators": generators, "loads": loads, "storage_units": storage_units,
                "stores": stores, "carriers": carriers}.items()},
            "capacity_by_carrier_mw": dict(sorted(capacity.items())),
            "peak_load_mw": peak_load,
            "total_load_mwh": total_load,
        },
        "field_provenance": dict(sorted(provenance.items())),
        "assumptions": [
            *assumptions,
            "summary.capacity_by_carrier_mw sums p_nom of active generators and storage units "
            "by carrier; summary.peak_load_mw is the coincident peak of total load p_set.",
            *extra_assumptions,
        ],
    }
    return CanonicalNetwork.model_validate(data)
