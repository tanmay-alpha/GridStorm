"""GeoJSON FeatureCollection from canonical-grid/1.0: buses = Point; lines, links and
transformers = LineString. Features are keyed by (``properties.component``, ``properties.id``)
because PyPSA ids are only unique per component (e.g. SciGRID reuses names across lines and
transformers); the feature-level ``id`` is ``"<component>:<id>"``.

For ``coordinate_kind == "schematic"`` the coordinates are layout coordinates, NOT lon/lat; the
collection carries the foreign members ``coordinate_kind``/``crs`` (RFC 7946 §6.1) and every
feature repeats ``coordinate_kind`` in its properties so clients cannot miss the flag.
Assets with missing coordinates are skipped (counted in ``skipped``), never placed at a guess.
"""

from __future__ import annotations

from typing import Any

from .catalog import NetworkEntry

_BUS_PROPS = ("name", "v_nom_kv", "carrier", "country")
_LINE_PROPS = ("bus0", "bus1", "v_nom_kv", "s_nom_mva", "length_km", "num_parallel", "carrier")
_LINK_PROPS = ("bus0", "bus1", "p_nom_mw", "efficiency", "carrier")
_TRAFO_PROPS = ("bus0", "bus1", "s_nom_mva", "x_pu", "r_pu", "tap_ratio")


def _xy(bus: dict[str, Any] | None) -> list[float] | None:
    if not bus:
        return None
    x, y = bus.get("x"), bus.get("y")
    if x is None or y is None:
        return None
    return [float(x), float(y)]


def build_geojson(entry: NetworkEntry) -> dict[str, Any]:
    kind = entry.coordinate_kind
    buses = entry.asset_ids("buses")
    features: list[dict[str, Any]] = []
    skipped = {"buses": 0, "lines": 0, "links": 0, "transformers": 0}

    for bus_id, bus in buses.items():
        xy = _xy(bus)
        if xy is None:
            skipped["buses"] += 1
            continue
        props = {"id": bus_id, "component": "bus", "coordinate_kind": kind}
        props.update({k: bus.get(k) for k in _BUS_PROPS})
        features.append(
            {
                "type": "Feature",
                "id": f"bus:{bus_id}",
                "geometry": {"type": "Point", "coordinates": xy},
                "properties": props,
            }
        )

    branch_types = (
        ("lines", "line", _LINE_PROPS),
        ("transformers", "transformer", _TRAFO_PROPS),
        ("links", "link", _LINK_PROPS),
    )
    for asset_type, singular, keys in branch_types:
        for asset_id, row in entry.asset_ids(asset_type).items():
            a, b = _xy(buses.get(str(row.get("bus0")))), _xy(buses.get(str(row.get("bus1"))))
            if a is None or b is None:
                skipped[asset_type] += 1
                continue
            props = {"id": asset_id, "component": singular, "coordinate_kind": kind}
            props.update({k: row.get(k) for k in keys})
            features.append(
                {
                    "type": "Feature",
                    "id": f"{singular}:{asset_id}",
                    "geometry": {"type": "LineString", "coordinates": [a, b]},
                    "properties": props,
                }
            )

    return {
        "type": "FeatureCollection",
        "network_id": entry.id,
        "coordinate_kind": kind,
        "crs": entry.canonical.get("crs") if kind == "geographic" else None,
        "provenance": (entry.canonical.get("field_provenance") or {}).get("buses.x"),
        "skipped": skipped,
        "features": features,
    }
