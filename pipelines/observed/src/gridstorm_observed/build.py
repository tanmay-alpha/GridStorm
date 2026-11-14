"""Historical-analogue scenario builder: OPSD stress days -> StormSpec scenarios for scigrid-de.

Usage (from ``pipelines/observed``)::

    uv run python -m gridstorm_observed.build [--network-dir DIR] [--skip-weather]

Steps: (1) read the cached, sha256-verified OPSD 60-min CSV (German columns only); (2) detect the
stress days (:mod:`detect`); (3) map each day onto the network's own 24 snapshots
(:mod:`mapping`); (4) write ``data/scenarios/observed/*.yaml``, the derived parameters and a
manifest to ``data/observed/opsd-de/``; (5) optionally fetch NASA POWER temperature/wind for the
stress windows into ``data/observed/nasa-power-de/``.

Licensing (docs/research/entsoe-reuse-check.md): only the ENTSO-E day-ahead total load forecast
(Reg. 543/2013 Art. 6.1.b, item #1 of the ENTSO-E free re-use list, CC BY 4.0) feeds hourly
committed values. The actual load (Art. 6.1.a) and actual generation (Art. 16.1) are not on that
list, and the capacities (OPSD/BNetzA/netztransparenz.de) carry no declared licence: they are used
to select the stress days and, for renewables, one coarse daily ratio per carrier (rounded to
0.05); no hourly value, statistic or absolute derived from them is written into the repository.
``tests/test_reuse.py`` attempts the reconstruction from the committed files.
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

OPSD_MANIFEST_SCHEMA = "gridstorm-observed-derived/2.0"
WEATHER_MANIFEST_SCHEMA = "gridstorm-observed-extract/1.0"
DERIVED_NAME = "derived-multipliers.json"
MANIFEST_NAME = "manifest.json"
WEATHER_CSV_NAME = "t2m_ws10m_hourly.csv"
WEATHER_PAD_DAYS = 3
HOURS = 24
CARRIERS = tuple(opsd.TECHS.values())


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

    ``load`` is the day-ahead load forecast (openly licensed). Reports, per alignment, the mean
    Pearson r of load and solar CF over the years with complete data, and how often the daily
    load minimum/maximum hour coincides with the network's. Solar CF is the physically decisive
    check (sun position does not depend on behaviour); 1 January load is a holiday profile whose
    timing varies between years. Only these aggregate statistics are committed.
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


def public_detection(det: detect.DayResult) -> dict:
    """The committable part of a detection: date, criterion and counts, no observed value."""
    d = det.detail
    out: dict = {"date": det.date, "criterion": d["criterion"]}
    for key in ("load_quantile", "high_load_days", "complete_days_considered"):
        if key in d:
            out[key] = d[key]
    if "rolling_24h_minimum_any_start" in d:
        w = d["rolling_24h_minimum_any_start"]
        out["rolling_24h_minimum_window_utc"] = [w["start"], w["end"]]
    return out


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
        if rm.multiplier < 1.0:  # w = 1 is a no-op
            events.append(
                {
                    "type": "renewable_availability_multiplier",
                    "carrier": rm.carrier,
                    "value": rm.multiplier,
                    "window": {"start": 0, "end": HOURS},
                }
            )
    w_notes = "; ".join(
        f"{rm.carrier} w = {rm.multiplier:.2f}"
        + (" (ratio above 1, clipped)" if rm.clipped else "")
        for rm in rms
    )
    return {
        "schema_version": stormspec.SCHEMA_VERSION,
        "id": f"{kind.slug}-{day}",
        "name": f"Observed analogue: {kind.title} {day} (Germany, OPSD/ENTSO-E)",
        "description": (
            f"Historical-analogue scenario. The German {kind.title} {day} (UTC), detected "
            f"objectively in Open Power System Data time series {sources.OPSD_VERSION} "
            f"({detection.detail['criterion']}), is mapped onto the 24 snapshots of "
            f"{net.network_id} (2011-01-01 00:00-23:00 UTC): hour by hour, the ENTSO-E day-ahead "
            f"load forecast's shape and level relative to the reference day {ref} (CC BY 4.0); "
            "for wind onshore / wind offshore / solar, one MODELED daily availability multiplier "
            "per carrier (the day's renewable shortfall, rounded to 0.05) on the network's own "
            "hourly profiles. The mapping and every result are MODELED. Generated by "
            "pipelines/observed (gridstorm_observed.build) - do not edit."
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
            f"Demand input (CC BY 4.0): {sources.LOAD_FORECAST_ATTRIBUTION}",
            "Stress-day selection: the date was chosen in OPSD actual load and wind/solar "
            "generation and capacity (ENTSO-E Reg. 543/2013 Art. 6.1.a and 16.1; OPSD "
            "calculations based on BNetzA and netztransparenz.de). Those series are not openly "
            "licensed; GridStorm stores no value or statistic derived from them except the date "
            "and the coarse daily renewable multipliers below (data/observed/opsd-de/manifest.json"
            ", source.column_reuse).",
            "Time alignment: network snapshot h = UTC hour h of the stress day. Evidence "
            "(data/observed/opsd-de/derived-multipliers.json, alignment_evidence): the network's "
            "solar availability matches observed 1 January solar CF far better in UTC than "
            "shifted to local time; for load the evidence is weaker.",
            "MODELED demand mapping, applied uniformly to every load: m_h = [F(d,h) / "
            f"mean_h F(ref,h)] / [L_net(h) / mean_h L_net(h)], F = day-ahead load forecast, "
            f"reference day ref = {ref} (the 1 January nearest to d, i.e. the analogue of the "
            "network's own 1 January profile). The scaled network load follows the forecast "
            "stress-day shape and its level relative to a 1 January; the actual load differs "
            "from the forecast by the forecast error. Multipliers rounded to 4 decimals; clipped "
            f"to (0, 5] at hours [{_fmt_hours(dm.clipped_hours)}].",
            "MODELED renewable shortfall per carrier c (Wind Onshore, Wind Offshore, Solar), "
            "applied to every generator of c for the whole day: w_c = min(round(mean_h CF_obs,c / "
            f"mean_h CF_net,c / {mapping.RENEWABLE_STEP}) * {mapping.RENEWABLE_STEP}, 1), CF_obs = "
            "national generation / national capacity, CF_net = capacity-weighted p_max_pu of the "
            "network's generators of c. The hourly shape stays the network's own 2011-01-01 "
            "shape; the observed hourly profile is deliberately not reproduced (not openly "
            f"licensed). No event when w = 1. {w_notes}.",
            "Aggregate national profiles are applied uniformly to every bus/generator: the spatial "
            "pattern of load and of wind/solar availability remains the network's 2011-01-01 "
            "pattern; only levels change.",
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
    load = de[opsd.LOAD_COL]  # actual load: detection only, never committed
    forecast = de[opsd.LOAD_FORECAST_COL]  # CC BY 4.0: drives the demand multipliers
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
        "provenance": "derived (CC BY 4.0 load forecast + coarse daily renewable ratios, "
        "MODELED mapping)",
        "license": "Demand multipliers: CC BY 4.0, attribution in manifest.json "
        "license.load_forecast_attribution. Renewable multipliers: see manifest.json "
        "source.column_reuse.",
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
        "alignment_evidence": alignment_evidence(forecast, cf, net),
        "scenarios": [],
    }
    written: list[Path] = []
    for kind in KINDS:
        det = detections[kind.key]
        day = det.date
        ref = reference_day(forecast, day)
        fc_day, fc_ref = day_values(forecast, day), day_values(forecast, ref)
        dm = mapping.demand_multipliers(fc_day, fc_ref, net.load_mw)
        rms = []
        flags: list[str] = []
        for tech, carrier in opsd.TECHS.items():
            obs = day_values(cf[tech].rename(tech), day)
            over = int(np.count_nonzero(obs > 1.0))
            if over:
                flags.append(
                    f"{tech}: observed generation exceeds OPSD capacity (CF > 1) in {over} UTC "
                    "hours; possibly lagging capacity data - values kept, not altered"
                )
            rms.append(mapping.renewable_daily_multiplier(carrier, obs, net.cf[carrier]))
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
                "detection": public_detection(det),
                "demand": {
                    "source_column": opsd.LOAD_FORECAST_COL,
                    "multipliers": dm.multipliers,
                    "clipped_hours": dm.clipped_hours,
                    "forecast_stress_day_mean_over_reference_mean": round(
                        float(fc_day.mean()) / dm.reference_mean_mw, 4
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
                        "daily_multiplier": rm.multiplier,
                        "clipped_at_1": rm.clipped,
                        "network_daily_mean_cf": round(float(np.mean(rm.network_cf)), 4),
                        "modeled_daily_mean_cf": round(float(np.mean(mapping.effective_cf(rm))), 4),
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
            "column_reuse": sources.OPSD_COLUMN_REUSE,
        },
        "license": {
            "opsd_package": "No data licence in datapackage.json (licenses: null); the OPSD page "
            "states 'Text is licensed under CC-BY license' (text only). OPSD notes primary data "
            "originate in ENTSO-E Transparency; capacities have separate per-column sources.",
            "entsoe_terms_url": sources.ENTSOE_TERMS_URL,
            "entsoe_reuse_list_url": sources.ENTSOE_REUSE_LIST_URL,
            "entsoe_reuse_list_sha256": sources.ENTSOE_REUSE_LIST_SHA256,
            "entsoe_reuse_list_version": sources.ENTSOE_REUSE_LIST_VERSION,
            "load_forecast_license": "CC-BY-4.0",
            "load_forecast_license_url": sources.CC_BY_4_URL,
            "load_forecast_attribution": sources.LOAD_FORECAST_ATTRIBUTION,
            "assessment": "Checked 2026-11-15 (docs/research/entsoe-reuse-check.md). The hourly "
            "demand multipliers derive only from the ENTSO-E day-ahead total load forecast "
            "(Reg. (EU) 543/2013 Art. 6.1.b), item #1 of the ENTSO-E free re-use list of "
            "2023-10-18 and therefore CC BY 4.0 with attribution and indication of changes. "
            "Actual load (Art. 6.1.a) and actual generation (Art. 16.1.b/c) are NOT on that "
            "list and remain subject to the Primary Owners' rights (Terms of Use 29/03/2023 "
            "cl. 3.1/5.1); no permission has been obtained, so nothing from which their hourly "
            "values can be reconstructed is committed: they only select the stress dates and "
            "set one daily renewable multiplier per carrier, rounded to 0.05. Capacities are "
            "OPSD calculations based on BNetzA and netztransparenz.de (no data licence "
            "declared); no capacity value is committed. Per-column detail: "
            "source.column_reuse.",
            "redistribution": "derived-only",
            "committed_content": "Per stress day: 24 hourly demand multipliers from the CC BY "
            "4.0 load forecast; one MODELED daily availability multiplier per renewable carrier "
            "(ratio of daily-mean observed CF to daily-mean network CF, rounded to 0.05, clipped "
            "to <= 1); the stress and reference dates and the detection criteria. No OPSD "
            "series, no observed MW value or statistic and no hourly observed capacity factor. "
            "pipelines/observed/tests/test_reuse.py attempts the reconstruction: the actual "
            "hourly load misses by more than 500 MW and the hourly observed CF by more than 10 % "
            "of the day's peak CF, even with an oracle scale fitted to the observed values.",
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
        w = {c: r["daily_multiplier"] for c, r in s["renewables"].items()}
        print(
            f"{s['scenario_id']}: day {s['stress_day_utc']} ref {s['reference_day_utc']} "
            f"events {s['events']} renewable w {w}"
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
