"""Historical-analogue scenario builder: OPSD stress days -> StormSpec scenarios for scigrid-de.

Usage (from ``pipelines/observed``)::

    uv run python -m gridstorm_observed.build [--network-dir DIR] [--skip-weather]

Steps: (1) read the cached, sha256-verified OPSD 60-min CSV (German columns only); (2) detect the
stress days (:mod:`detect`); (3) map each day onto the network's own 24 snapshots
(:mod:`mapping`); (4) write ``data/scenarios/observed/*.yaml``, the derived parameters and a
manifest to ``data/observed/opsd-de/``; (5) optionally fetch NASA POWER temperature/wind for the
stress windows into ``data/observed/nasa-power-de/``.

Licensing: OPSD German load/generation columns derive from ENTSO-E Transparency; capacities are
OPSD calculations based on BNetzA and netztransparenz.de (per-column datapackage metadata).
Redistribution permission for the ENTSO-E-derived series is not established. No observed hourly
OPSD series is written into the repository: only derived multipliers, summary statistics,
source URLs and sha256 checksums.
"""

from __future__ import annotations

import argparse
import json
import warnings
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import stormspec
import yaml

from . import detect, mapping, opsd, sources, weather

OPSD_MANIFEST_SCHEMA = "gridstorm-observed-derived/1.0"
WEATHER_MANIFEST_SCHEMA = "gridstorm-observed-extract/1.0"
DERIVED_NAME = "derived-multipliers.json"
MANIFEST_NAME = "manifest.json"
WEATHER_CSV_NAME = "t2m_ws10m_hourly.csv"
WEATHER_PAD_DAYS = 3
HOURS = 24
CARRIERS = tuple(opsd.TECHS.values())

ENTSOE_TERMS_URL = "https://transparencyplatform.zendesk.com/hc/en-us/articles/40921911218961-Legal-Terms-and-Conditions"
ENTSOE_REUSE_LIST_URL = (
    "https://transparencyplatform.zendesk.com/hc/en-us/article_attachments/40921869379729"
)
ENTSOE_REUSE_LIST_SHA256 = "b21717e8a5a41b9b8544db730d11c2a717abc9b07f89704437a89332b708ff9a"


@dataclass(frozen=True)
class Kind:
    key: str
    slug: str
    title: str


KINDS = (
    Kind("highest_load", "observed-peak-load", "highest-load day"),
    Kind("dunkelflaute", "observed-dunkelflaute", "winter Dunkelflaute day"),
    Kind("combined", "observed-high-load-low-res", "combined high-load / low-renewable day"),
)


# --- network side ---------------------------------------------------------------------------


@dataclass
class NetworkProfiles:
    network_id: str
    nc_sha256: str
    snapshots: list[str]
    load_mw: np.ndarray  # (24,)
    cf: dict[str, np.ndarray]  # carrier -> (24,) capacity-weighted CF
    p_nom_mw: dict[str, float]
    variable_generators: dict[str, int]


def network_profiles(network_dir: Path, network_id: str = sources.NETWORK_ID) -> NetworkProfiles:
    import pypsa

    nc = Path(network_dir) / "network.nc"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        n = pypsa.Network(str(nc))
    if len(n.snapshots) != HOURS:
        raise ValueError(f"{nc}: expected {HOURS} snapshots, found {len(n.snapshots)}")
    load = n.get_switchable_as_dense("Load", "p_set").sum(axis=1).to_numpy(dtype=float)
    pmax = n.generators_t.p_max_pu
    cf, p_nom, counts = {}, {}, {}
    for carrier in CARRIERS:
        gens = [g for g in pmax.columns if n.generators.at[g, "carrier"] == carrier]
        if not gens:
            raise ValueError(f"{nc}: no variable generators of carrier {carrier!r}")
        caps = n.generators.loc[gens, "p_nom"].to_numpy(dtype=float)
        cf[carrier] = mapping.capacity_weighted_cf(pmax[gens].to_numpy(dtype=float), caps)
        p_nom[carrier] = float(caps.sum())
        counts[carrier] = len(gens)
    return NetworkProfiles(
        network_id=network_id,
        nc_sha256=sources.sha256_file(nc),
        snapshots=[pd.Timestamp(s).isoformat() for s in n.snapshots],
        load_mw=load,
        cf=cf,
        p_nom_mw=p_nom,
        variable_generators=counts,
    )


# --- observed side --------------------------------------------------------------------------


def day_values(s: pd.Series, day: str) -> np.ndarray:
    d = pd.Timestamp(day, tz="UTC")
    v = s.loc[d : d + pd.Timedelta(hours=HOURS - 1)].to_numpy(dtype=float)
    if v.shape != (HOURS,) or not np.all(np.isfinite(v)):
        raise ValueError(f"{s.name}: day {day} is incomplete")
    return v


def reference_day(load: pd.Series, day: str) -> str:
    """1 January (UTC) nearest to ``day`` whose 24 load hours are all present."""
    d = pd.Timestamp(day, tz="UTC")
    years = sorted(
        {d.year - 1, d.year, d.year + 1},
        key=lambda y: abs((pd.Timestamp(f"{y}-01-01", tz="UTC") - d).total_seconds()),
    )
    for y in years:
        cand = f"{y}-01-01"
        try:
            day_values(load, cand)
        except (ValueError, KeyError):
            continue
        return cand
    raise ValueError(f"no complete 1 January near {day}")


def alignment_evidence(load: pd.Series, cf: pd.DataFrame, net: NetworkProfiles) -> dict:
    """Compare observed 1-January profiles with the network's under UTC vs local-time days.

    Reports, per alignment, the mean Pearson r of load and solar CF over the years with complete
    data, and how often the observed daily load minimum/maximum hour coincides with the
    network's. Solar CF is the physically decisive check (sun position does not depend on
    behaviour); 1 January load is a holiday profile whose timing varies between years.
    """
    net_lo, net_hi = int(np.argmin(net.load_mw)), int(np.argmax(net.load_mw))
    out: dict[str, dict] = {}
    for tz in ("UTC", "Europe/Berlin"):
        rs_load, rs_pv, lo_hits, hi_hits = [], [], 0, 0
        for y in range(2015, 2021):
            start = pd.Timestamp(f"{y}-01-01", tz=tz).tz_convert("UTC")
            idx = pd.date_range(start, periods=HOURS, freq="h")
            lv = load.reindex(idx).to_numpy(dtype=float)
            pv = cf["solar"].reindex(idx).to_numpy(dtype=float)
            if np.all(np.isfinite(lv)):
                rs_load.append(float(np.corrcoef(lv, net.load_mw)[0, 1]))
                lo_hits += int(np.argmin(lv)) == net_lo
                hi_hits += int(np.argmax(lv)) == net_hi
            if np.all(np.isfinite(pv)):
                rs_pv.append(float(np.corrcoef(pv, net.cf["Solar"])[0, 1]))
        out[tz] = {
            "load_r_mean": round(float(np.mean(rs_load)), 4),
            "load_years": len(rs_load),
            "load_min_hour_matches_network": lo_hits,
            "load_max_hour_matches_network": hi_hits,
            "solar_cf_r_mean": round(float(np.mean(rs_pv)), 4),
            "solar_years": len(rs_pv),
        }
    out["network_load_min_max_snapshot"] = [net_lo, net_hi]
    return out


# --- scenario assembly ----------------------------------------------------------------------


def _fmt_hours(hours: list[int]) -> str:
    return "none" if not hours else ", ".join(str(h) for h in hours)


def scenario_dict(
    kind: Kind,
    day: str,
    ref: str,
    net: NetworkProfiles,
    dm: mapping.DemandMapping,
    rms: list[mapping.RenewableMapping],
    detection: detect.DayResult,
) -> dict:
    events: list[dict] = [
        {"type": "demand_multiplier", "value": v, "window": {"start": h, "end": h + 1}}
        for h, v in enumerate(dm.multipliers)
    ]
    for rm in rms:
        for h, w in enumerate(rm.multipliers):
            if w is None or w == 1.0:  # undefined (network CF = 0) or clipped to a no-op
                continue
            events.append(
                {
                    "type": "renewable_availability_multiplier",
                    "carrier": rm.carrier,
                    "value": w,
                    "window": {"start": h, "end": h + 1},
                }
            )
    clip_notes = "; ".join(
        f"{rm.carrier}: clipped to 1 at hours [{_fmt_hours(rm.clipped_hours)}], "
        f"undefined (network CF = 0) at hours [{_fmt_hours(rm.undefined_hours)}]"
        for rm in rms
    )
    return {
        "schema_version": stormspec.SCHEMA_VERSION,
        "id": f"{kind.slug}-{day}",
        "name": f"Observed analogue: {kind.title} {day} (Germany, OPSD/ENTSO-E)",
        "description": (
            f"Historical-analogue scenario. The observed German {kind.title} {day} (UTC), "
            f"detected objectively in Open Power System Data time series {sources.OPSD_VERSION} "
            f"({detection.detail['criterion']}), is mapped hour by hour onto the 24 snapshots of "
            f"{net.network_id} (2011-01-01 00:00-23:00 UTC): national demand shape and level "
            f"relative to the observed reference day {ref}, and wind onshore / wind offshore / "
            "solar capacity factors. The inputs are OBSERVED; the mapping and every result are "
            "MODELED. Generated by pipelines/observed (gridstorm_observed.build) - do not edit."
        ),
        "dataset": {"network_id": net.network_id, "sha256": net.nc_sha256},
        "horizon": {"start": 0, "snapshots": HOURS},
        "events": events,
        "mitigation": {
            "storage_dispatch": True,
            "curtailment": True,
            "load_shedding": {"enabled": True, "voll_eur_per_mwh": 10000.0},
        },
        "execution": {
            "engine": "pypsa",
            "formulation": "lopf",
            "solver": "highs",
            "solver_options": {"time_limit_s": 600.0, "threads": 1},
            "deterministic": True,
            "seed": 0,
        },
        "assumptions": [
            f"OBSERVED input: OPSD time series {sources.OPSD_VERSION} "
            f"({sources.OPSD_DOI}), German columns DE_load_actual_entsoe_transparency and "
            "DE_{wind_onshore,wind_offshore,solar}_{generation_actual,capacity}; load/generation "
            "derive from ENTSO-E Transparency, capacities from OPSD calculations based on BNetzA "
            "and netztransparenz.de. Only derived multipliers are stored in GridStorm "
            "(redistribution permission for the hourly series is not established).",
            "Time alignment: network snapshot h = observed UTC hour h of the stress day. "
            "Evidence (data/observed/opsd-de/derived-multipliers.json, alignment_evidence): the "
            "network's solar availability matches observed 1 January solar CF far better in UTC "
            "than shifted to local time; for load the evidence is weaker (correlation slightly "
            "higher in local time, daily minimum/maximum hours coincide in UTC).",
            "MODELED demand mapping, applied uniformly to every load: m_h = [L_obs(d,h) / "
            f"mean_h L_obs(ref,h)] / [L_net(h) / mean_h L_net(h)] with reference day ref = {ref} "
            "(the observed 1 January nearest to d, i.e. the analogue of the network's own "
            "1 January profile). The scaled network load follows the observed day's shape and its "
            "level relative to an observed 1 January. Multipliers rounded to 4 decimals; "
            f"clipped to (0, 5] at hours [{_fmt_hours(dm.clipped_hours)}].",
            "MODELED renewable mapping per carrier c (Wind Onshore, Wind Offshore, Solar), "
            "applied uniformly to every generator of c: w_c,h = clip(CF_obs,c(h) / CF_net,c(h), "
            "0, 1), CF_obs = national generation / national capacity, CF_net = capacity-weighted "
            "mean p_max_pu of the network's generators of c. StormSpec only allows w <= 1, so "
            "hours with CF_obs > CF_net keep the network's own (lower) availability and no event "
            f"is emitted. {clip_notes}.",
            "Aggregate national profiles are applied uniformly to every bus/generator: the spatial "
            "pattern of load and of wind/solar availability remains the network's 2011-01-01 "
            "pattern; only hourly levels change.",
            "The network (2011 grid topology, 2014 renewable capacities, 2011 demand profile) "
            "differs from the observed year's system; installed capacities are NOT rescaled. "
            "This is an analogue stress test, not a reconstruction of the observed day.",
        ],
    }


def build(network_dir: Path, *, csv_path: Path | None = None) -> dict:
    """Detect, map and write scenarios + derived parameters + manifest. Returns the summary."""
    csv = csv_path or opsd.fetch_csv()
    csv_sha = sources.sha256_file(csv)
    if csv_sha != sources.OPSD_CSV_SHA256:
        raise ValueError(f"{csv}: sha256 {csv_sha} != published {sources.OPSD_CSV_SHA256}")
    datapackage_path = opsd.fetch_datapackage()
    datapackage = json.loads(datapackage_path.read_text(encoding="utf-8"))
    resource = next(r for r in datapackage["resources"] if r["name"] == "opsd_time_series_60min")
    if resource["hash"] != csv_sha or resource["bytes"] != csv.stat().st_size:
        raise ValueError("OPSD source does not match the official datapackage metadata")
    fields = {f["name"]: f for f in resource["schema"]["fields"]}
    retrieved_at = datetime.fromtimestamp(csv.stat().st_mtime, UTC).replace(microsecond=0)
    de = opsd.read_de(csv)
    cf = opsd.capacity_factors(de)
    load = de[opsd.LOAD_COL]
    net = network_profiles(network_dir)

    detections = {
        "highest_load": detect.highest_load_day(load),
        "dunkelflaute": detect.lowest_cf_day(cf["wind_solar"]),
        "combined": detect.combined_day(load, cf["wind_solar"]),
    }

    sources.SCENARIO_OUT_DIR.mkdir(parents=True, exist_ok=True)
    sources.OPSD_OUT_DIR.mkdir(parents=True, exist_ok=True)
    derived: dict = {
        "schema_version": OPSD_MANIFEST_SCHEMA,
        "provenance": "derived (observed inputs, MODELED mapping)",
        "network": {
            "network_id": net.network_id,
            "network_nc_sha256": net.nc_sha256,
            "snapshots_utc": [net.snapshots[0], net.snapshots[-1]],
            "load_mw": [round(float(v), 3) for v in net.load_mw],
            "load_mean_mw": round(float(net.load_mw.mean()), 3),
            "capacity_factor": {c: [round(float(v), 5) for v in a] for c, a in net.cf.items()},
            "variable_capacity_mw": {c: round(v, 3) for c, v in net.p_nom_mw.items()},
            "variable_generators": net.variable_generators,
        },
        "alignment_evidence": alignment_evidence(load, cf, net),
        "scenarios": [],
    }
    written: list[Path] = []
    for kind in KINDS:
        det = detections[kind.key]
        day = det.date
        ref = reference_day(load, day)
        dm = mapping.demand_multipliers(day_values(load, day), day_values(load, ref), net.load_mw)
        rms = []
        flags: list[str] = []
        for tech, carrier in opsd.TECHS.items():
            obs = day_values(cf[tech].rename(tech), day)
            over = [int(h) for h in np.flatnonzero(obs > 1.0)]
            if over:
                flags.append(
                    f"{tech}: observed generation exceeds OPSD capacity (CF > 1) at UTC hours "
                    f"{over}; possibly lagging capacity data - values kept, not altered"
                )
            rms.append(mapping.renewable_multipliers(carrier, obs, net.cf[carrier]))
        scen = scenario_dict(kind, day, ref, net, dm, rms, det)
        model = stormspec.Scenario.model_validate(scen)
        body = model.model_dump(mode="json")
        path = sources.SCENARIO_OUT_DIR / f"{model.id}.yaml"
        header = (
            "# GENERATED by pipelines/observed (python -m gridstorm_observed.build); do not edit.\n"
            "# Observed-analogue StormSpec scenario; provenance and checksums in\n"
            "# data/observed/opsd-de/manifest.json and derived-multipliers.json.\n"
        )
        text = header + yaml.safe_dump(body, sort_keys=False, allow_unicode=True, width=100)
        path.write_bytes(text.encode("utf-8"))
        written.append(path)
        derived["scenarios"].append(
            {
                "scenario_id": model.id,
                "kind": kind.key,
                "stress_day_utc": day,
                "reference_day_utc": ref,
                "detection": det.as_dict(),
                "demand": {
                    "multipliers": dm.multipliers,
                    "clipped_hours": dm.clipped_hours,
                    "reference_day_mean_load_mw": round(dm.reference_mean_obs_mw, 1),
                    "stress_day_mean_over_reference_mean": round(
                        float(np.mean(day_values(load, day))) / dm.reference_mean_obs_mw, 4
                    ),
                    "scaled_network_peak_mw": round(
                        float(np.max(np.asarray(dm.multipliers) * net.load_mw)), 1
                    ),
                    "scaled_network_energy_mwh": round(
                        float(np.sum(np.asarray(dm.multipliers) * net.load_mw)), 1
                    ),
                },
                "renewables": {
                    rm.carrier: {
                        "multipliers": rm.multipliers,
                        "clipped_hours": rm.clipped_hours,
                        "max_raw_ratio_in_clipped_hours": (
                            round(max(rm.raw[h] for h in rm.clipped_hours), 4)
                            if rm.clipped_hours
                            else None
                        ),
                        "undefined_hours": rm.undefined_hours,
                        "network_daily_mean_cf": round(float(np.mean(rm.network_cf)), 4),
                        "observed_daily_mean_cf": round(float(np.mean(rm.observed_cf)), 4),
                        "modeled_daily_mean_cf_after_mapping": round(
                            float(np.mean(mapping.effective_cf(rm))), 4
                        ),
                    }
                    for rm in rms
                },
                "quality_flags": flags,
                "events": len(model.events),
                "scenario_sha256": sources.sha256_file(path),
            }
        )

    derived_path = sources.OPSD_OUT_DIR / DERIVED_NAME
    derived_path.write_bytes(
        (json.dumps(derived, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    )
    coverage = opsd.coverage_report(de)
    manifest = {
        "schema_version": OPSD_MANIFEST_SCHEMA,
        "dataset_id": "opsd-de-observed-analogues",
        "title": "Derived observed-analogue parameters from OPSD time series (Germany)",
        "provenance": "derived",
        "source": {
            "name": "Open Power System Data - Time series",
            "version": sources.OPSD_VERSION,
            "doi": sources.OPSD_DOI,
            "url": sources.OPSD_CSV_URL,
            "datapackage_url": sources.OPSD_DATAPACKAGE_URL,
            "datapackage_sha256": sources.sha256_file(datapackage_path),
            "file": sources.OPSD_CSV_NAME,
            "bytes": sources.OPSD_CSV_BYTES,
            "sha256": csv_sha,
            "sha256_source": "published in datapackage.json resources[opsd_time_series_60min]"
            ".hash and verified on the downloaded file",
            "retrieved_at": retrieved_at.isoformat(),
            "columns_used": list(sources.OPSD_DE_COLUMNS),
            "coverage": coverage,
            "column_sources": {
                c: {"unit": fields[c]["unit"], **fields[c]["source"]}
                for c in sources.OPSD_DE_COLUMNS
            },
        },
        "license": {
            "opsd_package": "No data licence in datapackage.json (licenses: null); the OPSD page "
            "states 'Text is licensed under CC-BY license' (text only). OPSD notes primary data "
            "originate in ENTSO-E Transparency; capacities have separate per-column sources.",
            "entsoe_terms_url": ENTSOE_TERMS_URL,
            "entsoe_reuse_list_url": ENTSOE_REUSE_LIST_URL,
            "entsoe_reuse_list_sha256": ENTSOE_REUSE_LIST_SHA256,
            "entsoe_reuse_list_version": "2023-10-18",
            "assessment": "Redistribution permission for the load/generation columns derived "
            "from ENTSO-E Transparency has not been established. Capacities are OPSD "
            "calculations based on BNetzA and netztransparenz.de; no hourly OPSD series are "
            "redistributed, including these capacity columns.",
            "redistribution": "restricted",
            "committed_content": "derived hourly multipliers and summary statistics only; no "
            "observed hourly series",
        },
        "attribution": sources.OPSD_ATTRIBUTION,
        "units": {
            "multipliers": "dimensionless",
            "load": "MW",
            "capacity_factor": "fraction of installed capacity",
            "time": "UTC hour start",
        },
        "missing_value_policy": "No interpolation or filling. Hours absent from the source or "
        "empty are NaN; any UTC day/window with a NaN hour is excluded from detection; a mapped "
        "day must be complete.",
        "quality_flags": {s["scenario_id"]: s["quality_flags"] for s in derived["scenarios"]},
        "derived_files": {DERIVED_NAME: sources.sha256_file(derived_path)},
        "scenario_files": {
            p.relative_to(sources.REPO_ROOT).as_posix(): sources.sha256_file(p) for p in written
        },
        "generator": "pipelines/observed: python -m gridstorm_observed.build",
    }
    (sources.OPSD_OUT_DIR / MANIFEST_NAME).write_bytes(
        (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    )
    return {"derived": derived, "manifest": manifest, "scenarios": written}


def build_weather(days: list[str]) -> dict:
    """Fetch NASA POWER for each stress day +- WEATHER_PAD_DAYS at every point; write extract."""
    frames, headers, requests = [], [], []
    for day in days:
        d = pd.Timestamp(day)
        start = (d - pd.Timedelta(days=WEATHER_PAD_DAYS)).strftime("%Y%m%d")
        end = (d + pd.Timedelta(days=WEATHER_PAD_DAYS)).strftime("%Y%m%d")
        for pt in sources.POWER_POINTS:
            path = weather.fetch_point(pt, start, end)
            df, header = weather.parse_point(path, pt)
            frames.append(df)
            headers.append(header)
            requests.append(
                {
                    "point": pt.id,
                    "url": weather.point_url(pt, start, end),
                    "response_sha256": sources.sha256_file(path),
                    "retrieved_at": datetime.fromtimestamp(path.stat().st_mtime, UTC)
                    .replace(microsecond=0)
                    .isoformat(),
                }
            )
    allw = pd.concat(frames)
    allw = allw.reset_index().drop_duplicates(["utc", "point"]).sort_values(["utc", "point"])
    sources.POWER_OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = sources.POWER_OUT_DIR / WEATHER_CSV_NAME
    out = allw.assign(utc=allw["utc"].dt.strftime("%Y-%m-%dT%H:%MZ"))
    csv_path.write_bytes(out.to_csv(index=False, lineterminator="\n").encode("utf-8"))
    indexed = allw.set_index("utc")
    summaries = [weather.day_summary(indexed, day) for day in days]
    api_versions = sorted({h["api"]["version"] for h in headers})
    manifest = {
        "schema_version": WEATHER_MANIFEST_SCHEMA,
        "dataset_id": "nasa-power-de-stress-windows",
        "title": "NASA POWER hourly T2M/WS10M at four German cities around observed stress days",
        "provenance": "observed (reanalysis-derived: MERRA-2 via NASA POWER), not station data",
        "source": {
            "name": "NASA Langley Research Center POWER Project, Hourly API",
            "api_url": sources.POWER_HOURLY_URL,
            "api_versions": api_versions,
            "data_sources": sorted({s for h in headers for s in h.get("sources", [])}),
            "requests": requests,
        },
        "license": {
            "terms": "NASA Earthdata guidance permits factual use and redistribution of "
            "unrestricted NASA material without explicit permission, with acknowledgement and "
            "no implied endorsement. POWER requires service/version/access-date attribution "
            "and requests notification when data are redistributed to other researchers. "
            "No POWER-specific SPDX licence is asserted.",
            "data_use_url": sources.POWER_DATA_USE_URL,
            "referencing_url": sources.POWER_REFERENCING_URL,
            "redistribution": "permitted",
        },
        "attribution": "The data was obtained from the National Aeronautics and Space "
        "Administration (NASA) Langley Research Center (LaRC) Prediction of Worldwide Energy "
        "Resource (POWER) Project funded through the NASA Earth Science/Applied Science "
        f"Program. POWER Hourly API {', '.join(api_versions)}, accessed "
        f"{min(r['retrieved_at'] for r in requests)[:10]}.",
        "points": [
            {"id": p.id, "name": p.name, "lat": p.lat, "lon": p.lon} for p in sources.POWER_POINTS
        ],
        "windows_utc": [{"stress_day": d, "days_before_after": WEATHER_PAD_DAYS} for d in days],
        "units": {
            "T2M": weather.UNITS["T2M"],
            "WS10M": weather.UNITS["WS10M"],
            "utc": "UTC hour start",
        },
        "missing_value_policy": "POWER fill value -999 -> empty cell; never interpolated.",
        "missing_values": {p: int(allw[p].isna().sum()) for p in weather.PARAMETERS},
        "rows": int(len(allw)),
        "files": {WEATHER_CSV_NAME: sources.sha256_file(csv_path)},
        "stress_day_summaries": summaries,
        "generator": "pipelines/observed: python -m gridstorm_observed.build",
    }
    (sources.POWER_OUT_DIR / MANIFEST_NAME).write_bytes(
        (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--network-dir",
        type=Path,
        default=sources.NETWORK_DIR,
        help="directory containing network.nc (default data/networks/scigrid-de)",
    )
    ap.add_argument("--csv", type=Path, default=None, help="pre-downloaded OPSD 60-min CSV")
    ap.add_argument("--skip-weather", action="store_true")
    args = ap.parse_args(argv)
    res = build(args.network_dir, csv_path=args.csv)
    for s in res["derived"]["scenarios"]:
        print(
            f"{s['scenario_id']}: day {s['stress_day_utc']} ref {s['reference_day_utc']} "
            f"events {s['events']} detection {s['detection']['value']:.4f}"
        )
    if not args.skip_weather:
        days = [s["stress_day_utc"] for s in res["derived"]["scenarios"]]
        wm = build_weather(days)
        for sm in wm["stress_day_summaries"]:
            print(
                f"weather {sm['date']}: T2M mean {sm['t2m_mean_all_points_c']} C, "
                f"WS10M mean {sm['ws10m_mean_all_points_ms']} m/s"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
