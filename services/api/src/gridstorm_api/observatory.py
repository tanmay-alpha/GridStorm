"""Data Observatory: one research-data catalog merged from three file-backed sources.

1. The curated bundle ``<data>/observatory/`` (``catalog.json`` + ``series/<id>.csv`` +
   ``manifest.json``), produced by the licence-gated publication pipeline and baked into the image.
   Every file is sha256-verified against ``manifest.json`` when the bundle is first loaded; a
   dataset whose file is missing or does not match is reported with a failed ``checksum`` check and
   its series/export endpoints answer 503 — unverified bytes are never served. An unverifiable
   ``catalog.json`` (or a missing/invalid manifest) drops every bundle entry.
2. One ``network_model`` entry per network of the existing :class:`NetworkCatalog`.
3. One ``precomputed_experiment`` entry per research study group of the precomputed artifact
   index (the groups of the Research Workbench), linking to the existing research routes.

Nothing is copied into SQL (ADR 0003). Series are parsed once into ``array`` columns (8 bytes per
value, NaN = missing) so the bundle costs well under a few MB of RSS. Missing values stay null:
absent timestamps and empty CSV cells are never interpolated or turned into 0.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import math
import re
import threading
from array import array
from bisect import bisect_left
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from .catalog import NetworkCatalog, NetworkEntry, sha256_file
from .errors import Conflict, Forbidden, NotFound, ServiceUnavailable, Unprocessable
from .precomputed import PrecomputedArtifacts
from .schemas import DatasetEntry

if TYPE_CHECKING:
    from .config import Settings

log = logging.getLogger("gridstorm_api.observatory")

SCHEMA_VERSION = "gridstorm-observatory/1.0"
REPO_BLOB = "https://github.com/tanmay-alpha/GridStorm/blob/main/"
REPO_TREE = "https://github.com/tanmay-alpha/GridStorm/tree/main/"

# Series bounds (contract): at most 3 years per request, ≤ 2000 points, default 1500.
MAX_RANGE_S = 1096 * 86400
DEFAULT_WINDOW_S = 31 * 86400
MAX_POINTS = 2000
DEFAULT_MAX_POINTS = 1500
# Aggregation buckets: (code, seconds, UTC alignment offset from the epoch). The epoch is a UTC
# midnight, so PT3H buckets start at 00/03/…/21 UTC and P1D at 00:00 UTC; P7D buckets are ISO
# weeks starting Monday 00:00 UTC (1970-01-05 is the first Monday after the epoch).
BUCKETS: tuple[tuple[str, int, int], ...] = (
    ("PT3H", 3 * 3600, 0),
    ("P1D", 86400, 0),
    ("P7D", 7 * 86400, 4 * 86400),
)
_DURATION = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")


def parse_duration(value: str | None) -> int | None:
    """Seconds of a simple ISO-8601 duration (``PT1H``, ``P1D``, ``PT15M``), else None."""
    m = _DURATION.match(value or "")
    if not m or not any(m.groups()):
        return None
    d, h, mi, s = (int(g) if g else 0 for g in m.groups())
    seconds = d * 86400 + h * 3600 + mi * 60 + s
    return seconds or None


def iso_utc(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_csv_utc(value: str) -> int:
    return int(datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).timestamp())


def parse_query_utc(value: str, name: str) -> int:
    """Query timestamp: ISO-8601 date or date-time; a value without offset is taken as UTC."""
    text = value.strip()
    if text[-1:] in ("Z", "z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise Unprocessable(
            f"{name} must be an ISO-8601 date or date-time (UTC)",
            code="invalid_datetime",
            details={name: value},
        ) from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return math.floor(dt.timestamp())


# --- bundle -------------------------------------------------------------------------------------
@dataclass
class SeriesTable:
    """A verified series CSV: sorted UTC epoch seconds + a float column per series (NaN = null)."""

    times: array
    columns: dict[str, array]
    step_s: int

    @property
    def rows(self) -> int:
        return len(self.times)


@dataclass
class BundleDataset:
    entry: dict[str, Any]
    table: SeriesTable | None = None
    failure: str | None = None


@dataclass
class BundleState:
    status: str  # ok | degraded | absent | error
    schema_version: str | None = None
    bundle_version: str | None = None
    sha256: str | None = None
    detail: str | None = None
    datasets: dict[str, BundleDataset] = field(default_factory=dict)

    def describe(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "schema_version": self.schema_version,
            "bundle_version": self.bundle_version,
            "sha256": self.sha256,
            "detail": self.detail,
            "failed_datasets": sorted(i for i, d in self.datasets.items() if d.failure),
        }


def _check(entry: dict[str, Any], name: str, status: str, detail: str) -> None:
    quality = entry.setdefault("quality", {})
    quality.setdefault("checks", []).append({"name": name, "status": status, "detail": detail})


def _parse_table(path: Path, series_ids: list[str], step_s: int) -> SeriesTable:
    times = array("q")
    columns = {sid: array("d") for sid in series_ids}
    nan = math.nan
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader, None)
        if not header or header[0] != "utc":
            raise ValueError("first CSV column must be 'utc'")
        missing = [s for s in series_ids if s not in header]
        if missing:
            raise ValueError(f"series column(s) missing from CSV: {missing}")
        idx = [(columns[s], header.index(s)) for s in series_ids]
        prev: int | None = None
        for lineno, row in enumerate(reader, start=2):
            if not row:
                continue
            t = _parse_csv_utc(row[0])
            if prev is not None and t <= prev:
                raise ValueError(f"line {lineno}: utc not strictly increasing")
            if prev is not None and (t - times[0]) % step_s:
                raise ValueError(f"line {lineno}: utc {row[0]} is off the {step_s}s grid")
            prev = t
            times.append(t)
            for col, i in idx:
                cell = row[i].strip() if i < len(row) else ""
                col.append(float(cell) if cell else nan)
    return SeriesTable(times=times, columns=columns, step_s=step_s)


def load_bundle(root: Path) -> BundleState:
    if not root.is_dir():
        return BundleState(status="absent", detail=f"no bundle directory ({root.name}/)")
    catalog_path, manifest_path = root / "catalog.json", root / "manifest.json"
    if not catalog_path.is_file():
        return BundleState(status="absent", detail="catalog.json missing")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        declared = {
            str(f["path"]): (str(f["sha256"]).lower(), f.get("bytes"))
            for f in manifest.get("files") or []
        }
    except (OSError, ValueError, KeyError, TypeError) as exc:
        log.error("observatory manifest unusable: %s", exc)
        return BundleState(status="error", detail=f"manifest.json unusable: {exc}")
    root_resolved = root.resolve()
    verified: dict[str, str] = {}
    mismatched: dict[str, str] = {}
    for rel, (sha, _size) in declared.items():
        path = (root / rel).resolve()
        if not path.is_relative_to(root_resolved) or not path.is_file():
            mismatched[rel] = "file missing"
            continue
        actual = sha256_file(path)
        if actual == sha:
            verified[rel] = actual
        else:
            mismatched[rel] = f"sha256 {actual} != manifest {sha}"
    if "catalog.json" not in verified:
        reason = mismatched.get("catalog.json", "not listed in manifest.json")
        log.error("observatory catalog.json not verified (%s); bundle not served", reason)
        return BundleState(status="error", detail=f"catalog.json not verified: {reason}")
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return BundleState(status="error", detail=f"catalog.json invalid: {exc}")
    state = BundleState(
        status="ok",
        schema_version=catalog.get("schema_version"),
        bundle_version=catalog.get("bundle_version"),
        sha256=sha256_file(manifest_path),
    )
    if state.schema_version != SCHEMA_VERSION:
        return BundleState(
            status="error",
            detail=f"unsupported schema_version {state.schema_version!r} (want {SCHEMA_VERSION})",
        )
    invalid: list[str] = []
    for raw in catalog.get("entries") or []:
        try:
            entry = DatasetEntry.model_validate(raw).model_dump(mode="json")
        except ValidationError as exc:
            ident = raw.get("id") if isinstance(raw, dict) else None
            log.error("observatory entry %r invalid: %s", ident, exc)
            invalid.append(str(ident))
            continue
        ds_id = entry["id"]
        if not _SAFE_ID.match(ds_id) or ds_id in state.datasets:
            invalid.append(ds_id)
            continue
        state.datasets[ds_id] = ds = BundleDataset(entry=entry)
        artifact = entry.get("artifact")
        if artifact is None:
            continue
        rel = artifact["path"]
        if rel not in verified:
            ds.failure = f"{rel}: {mismatched.get(rel, 'not listed in manifest.json')}"
        elif verified[rel] != artifact["sha256"].lower():
            ds.failure = f"{rel}: entry sha256 {artifact['sha256']} != file {verified[rel]}"
        if ds.failure is None and entry["series"]:
            step = parse_duration((entry.get("temporal") or {}).get("resolution"))
            if step is None:
                ds.failure = "temporal.resolution missing or not an ISO-8601 duration"
            else:
                try:
                    ds.table = _parse_table(root / rel, [s["id"] for s in entry["series"]], step)
                except (OSError, ValueError, IndexError) as exc:
                    ds.failure = f"{rel}: {exc}"
        if ds.failure:
            log.error("observatory dataset %s not served: %s", ds_id, ds.failure)
            _check(entry, "checksum", "fail", ds.failure)
        else:
            _check(
                entry,
                "checksum",
                "pass",
                f"{rel} sha256 verified against manifest.json when the API loaded the bundle",
            )
    if invalid or any(d.failure for d in state.datasets.values()):
        state.status = "degraded"
        if invalid:
            state.detail = f"invalid entries skipped: {invalid}"
    return state


# --- derived entries ----------------------------------------------------------------------------
@dataclass(frozen=True)
class StudyGroup:
    id: str
    title: str
    summary: str
    engine: str
    kind: str | None
    provenance: str
    data_nature: str
    route: str
    docs: tuple[tuple[str, str], ...]
    only_prefix: str | None = None
    exclude_prefix: str | None = None
    # Research Workbench study id when it differs from the group id (the analogue artifacts are
    # PyPSA results listed under the Workbench's `pypsa-presets` study).
    workbench_study: str | None = None

    def matches(self, item: dict[str, Any]) -> bool:
        aid = item["artifact_id"]
        return (
            item["engine"] == self.engine
            and (self.kind is None or item["kind"] == self.kind)
            and (self.only_prefix is None or aid.startswith(self.only_prefix))
            and (self.exclude_prefix is None or not aid.startswith(self.exclude_prefix))
        )


ANALOGUE_PREFIX = "observed-"
ANALOGUE_DOC = "docs/research/observed-analogue-scenarios.md"

# Mirrors the Research Workbench study groups (apps/web/src/features/workbench/studies.ts);
# summaries are its UI copy, provenance is the artifacts' own label.
STUDY_GROUPS: tuple[StudyGroup, ...] = (
    StudyGroup(
        "stormbench",
        "StormBench — DC PTDF/LODF screening vs exact N-1",
        "How well and how fast linear DC sensitivity screening finds the single-branch outages "
        "that exact DC and AC N-1 power flows flag.",
        "stormbench",
        "benchmark",
        "calculated",
        "Benchmark results computed offline on PGLib-OPF cases",
        "/benchmarks#stormbench",
        (("StormBench benchmark report", "docs/benchmarks/stormbench.md"),),
    ),
    StudyGroup(
        "stormrisk",
        "StormRisk — Monte Carlo expected energy not served",
        "Probability-weighted unserved energy (EENS) over sampled component-outage states, each "
        "solved as a DC linear OPF.",
        "stormrisk",
        "risk",
        "modeled",
        "Monte Carlo estimate over modelled outage probabilities (not observed outages)",
        "/benchmarks#stormrisk",
        (("Probabilistic stress method", "docs/research/probabilistic-stress.md"),),
    ),
    StudyGroup(
        "crisis-advisor",
        "Crisis Response Advisor — AC-verified remedial actions",
        "Deterministic candidate search (redispatch, switching, load shedding) for a crisis state; "
        "every candidate is accepted or rejected by full AC power flow.",
        "advisor",
        "advisor",
        "calculated",
        "Deterministic AC power-flow search results",
        "/contingency#advisor",
        (("Crisis advisor method", "docs/research/crisis-advisor.md"),),
    ),
    StudyGroup(
        "grid2op-agents",
        "Grid2Op — baseline agents over week-long episodes",
        "Three deterministic agents operate the l2rpn_case14_sandbox grid for up to one week, "
        "with and without a forced line outage.",
        "grid2op",
        "episode",
        "modeled",
        "Simulated episodes on synthetic chronics (not measurements)",
        "/operations",
        (("Grid2Op integration", "docs/research/grid2op-integration.md"),),
    ),
    StudyGroup(
        "pandapower-n1",
        "pandapower AC N-1 contingency screening",
        "Every in-service branch taken out of an AC-OPF base point and re-solved by "
        "Newton–Raphson; outages classified as secure, overload, voltage, islanding or "
        "non-convergent.",
        "pandapower",
        "n_minus_1",
        "calculated",
        "AC power-flow contingency results on PGLib-OPF cases",
        "/contingency#n1",
        (("AC validation", "docs/research/ac-validation.md"),),
    ),
    StudyGroup(
        "ac-reference",
        "pandapower AC power-flow reference validation",
        "pandapower Newton–Raphson results compared with MATPOWER/PYPOWER reference solutions on "
        "the same cases.",
        "pandapower",
        "benchmark",
        "calculated",
        "Solver agreement checks against reference solutions",
        "/benchmarks#ac-reference",
        (("AC validation", "docs/research/ac-validation.md"),),
    ),
    StudyGroup(
        "simbench-distribution",
        "SimBench LV feeder — AC time-series studies",
        "Week-long quasi-static AC power flows of one rural low-voltage feeder under load, PV and "
        "voltage-boundary stress, with two PV mitigations.",
        "distribution",
        "timeseries",
        "calculated",
        "AC time-series power flows on synthetic SimBench profiles",
        "/workbench?study=simbench-distribution",
        (("SimBench distribution studies", "docs/research/simbench-distribution.md"),),
    ),
    StudyGroup(
        "cross-engine",
        "Cross-engine agreement — pandapower vs PyPSA vs MATPOWER formulas",
        "The same PGLib cases solved by pandapower, PyPSA and an independent implementation of the "
        "MATPOWER DC equations, compared within fixed tolerances.",
        "cross-engine",
        "benchmark",
        "calculated",
        "Cross-solver agreement checks",
        "/benchmarks#cross-engine",
        (("Cross-engine benchmark", "docs/benchmarks/cross-engine.md"),),
    ),
    StudyGroup(
        "stormml",
        "StormML — ML contingency screening vs DC-LODF baselines",
        "Whether models trained on simulator-generated AC N-1 labels rank outages better than "
        "transparent DC-LODF and pre-loading screening, on unseen operating points and unseen "
        "networks.",
        "stormml",
        "benchmark",
        "modeled",
        "Model predictions evaluated against simulator labels",
        "/workbench?study=stormml",
        (("ML contingency screening", "docs/research/ml-contingency-screening.md"),),
    ),
    StudyGroup(
        "pypsa-presets",
        "PyPSA preset scenarios — operational LOPF",
        "Published StormSpec presets (baselines, outages, demand and renewable stress) solved as "
        "linear optimal power flow on fixed capacities with load shedding.",
        "pypsa",
        "simulation",
        "modeled",
        "Linear optimal power flow results of published presets",
        "/benchmarks#pypsa",
        (("PyPSA preset benchmarks", "docs/benchmarks/pypsa-presets.md"),),
        exclude_prefix=ANALOGUE_PREFIX,
    ),
    StudyGroup(
        "observed-analogues",
        "Observed-analogue stress days on SciGRID Germany",
        "Three historical German stress days (OPSD/ENTSO-E day-ahead load forecast, modelled "
        "renewable shortfall) mapped onto the scigrid-de day and solved as linear optimal power "
        "flow with load shedding.",
        "pypsa",
        "simulation",
        "modeled",
        "Modelled analogue of observed stress days (not a reconstruction of the observed system)",
        "/studio?network=scigrid-de",
        (("Observed-analogue scenarios", ANALOGUE_DOC),),
        only_prefix=ANALOGUE_PREFIX,
        workbench_study="pypsa-presets",
    ),
)

_REDISTRIBUTION = {"permitted", "derived-only", "restricted"}
_COUNTRY_NAMES = {"BE": "Belgium", "DE": "Germany", "NO": "Norway", "UK": "United Kingdom"}
# Networks whose buses carry no country although the manifest's coverage states one.
# scigrid-de: manifest coverage.geographic = "Germany, 220 kV and 380 kV transmission level …".
_NETWORK_COUNTRY = {"scigrid-de": "DE"}


def _doc(label: str, path: str) -> dict[str, str]:
    return {"label": label, "href": REPO_BLOB + path}


def _first_sentence(text: str | None) -> str:
    text = (text or "").strip()
    m = re.search(r"(?<=[.!?])\s", text)
    return text[: m.start()] if m else text


def _iso_duration(hours: float | None) -> str | None:
    if not hours or hours <= 0:
        return None
    if hours % 24 == 0:
        return f"P{int(hours // 24)}D"
    if float(hours).is_integer():
        return f"PT{int(hours)}H"
    return f"PT{round(hours * 60)}M"


def _quality(checks: list[dict[str, Any]], warnings: list[str]) -> dict[str, Any]:
    return {
        "rows": None,
        "expected_rows": None,
        "completeness_pct": None,
        "missing_values": {},
        "missing_policy": "kept-as-null",
        "checks": checks,
        "warnings": warnings,
    }


def network_entry(
    net: NetworkEntry, preset_ids: list[str], live: bool, studio_ready: bool
) -> dict[str, Any]:
    m, c = net.manifest, net.canonical
    lic, src, cov = m.get("license") or {}, m.get("source") or {}, m.get("coverage") or {}
    provenance = m.get("provenance_class") or "modeled"
    coord = net.coordinate_kind
    countries = sorted({str(b["country"]) for b in c.get("buses") or [] if b.get("country")})
    # Country only when grounded (one bus country, or the manifest coverage for _NETWORK_COUNTRY);
    # schematic cases without any country are benchmark test systems (PGLib/IEEE).
    region = None
    code = _NETWORK_COUNTRY.get(net.id) or (countries[0] if len(countries) == 1 else None)
    if code:
        region = {"code": code, "name": _COUNTRY_NAMES.get(code, code), "kind": "country"}
    elif coord == "schematic" and not countries:
        region = {
            "code": "benchmark",
            "name": "Benchmark test system (no geography)",
            "kind": "benchmark",
        }
    snaps = c.get("snapshots") or {}
    temporal = None
    warnings: list[str] = []
    if snaps.get("start") and snaps.get("end"):
        temporal = {
            "start_utc": f"{snaps['start']}Z",
            "end_utc": f"{snaps['end']}Z",
            "resolution": _iso_duration(snaps.get("resolution_h")),
            "timezone": "UTC",
            "windows": None,
        }
        warnings.append(
            "Snapshot timestamps are timezone-naive in the source network; listed here as UTC."
        )
    warnings += [f"quality flag: {q}" for q in m.get("quality_flags") or [] if isinstance(q, str)]
    checks = [
        {
            "name": "canonical_sha256",
            "status": "pass",
            "detail": f"canonical.json sha256 {net.canonical_sha256} computed at load",
        },
        {
            "name": "network_file",
            "status": "pass" if net.network_nc.is_file() else "warn",
            "detail": "network.nc present"
            if net.network_nc.is_file()
            else "network.nc missing: browse only, no simulation",
        },
    ]
    description = "\n\n".join(
        p
        for p in (
            m.get("description"),
            f"**Geographic coverage:** {cov['geographic']}" if cov.get("geographic") else None,
            f"**Temporal coverage:** {cov['temporal']}" if cov.get("temporal") else None,
        )
        if p
    )
    if studio_ready:
        mode = "live solves" if live else "precomputed preset results only"
        rationale = f"Open in Crisis Studio ({mode}; {len(preset_ids)} preset(s))."
    else:
        rationale = "Not runnable here: no live execution and no published presets."
    redistribution = lic.get("redistribution")
    return {
        "id": f"network-{net.id}",
        "title": net.name,
        "summary": _first_sentence(m.get("description")) or net.name,
        "description": description or net.name,
        "category": "network_model",
        "provenance": provenance,
        "data_nature": f"{provenance} power-system model"
        + ("; schematic layout, no geography" if coord == "schematic" else "; lon/lat buses"),
        "region": region,
        "source": {
            "name": net.name,
            "publisher": None,
            "url": src.get("url"),
            "version": src.get("version"),
            "doi": None,
            "retrieved_at": m.get("retrieved_at"),
            "source_sha256": None,
            "license": {
                "id": lic.get("spdx"),
                "name": lic.get("spdx"),
                "url": lic.get("url"),
                "redistribution": redistribution
                if redistribution in _REDISTRIBUTION
                else "restricted",
            },
            "attribution": lic.get("attribution"),
        },
        "temporal": temporal,
        "spatial": {"kind": "network", "points": None},
        "series": [],
        "quality": _quality(checks, warnings),
        "transformations": [
            {"step": str(t.get("step")), "description": str(t.get("description") or "")}
            for t in m.get("transformations") or []
            if isinstance(t, dict) and t.get("step")
        ],
        "transformation_version": c.get("schema_version"),
        "artifact": None,
        "links": {
            "network_id": net.id,
            "scenario_ids": preset_ids,
            "study_route": "/explore",
            "docs": [_doc("Network data catalog", "docs/research/data-catalog.md")],
        },
        "use_in_scenario": {
            "available": studio_ready,
            "network_id": net.id,
            "preset_id": None,
            "route": f"/studio?network={net.id}" if studio_ready else None,
            "rationale": rationale,
        },
        # Network models have no tabular series to export (the network itself: /api/v1/networks).
        "exportable": False,
    }


def experiment_entry(
    group: StudyGroup,
    items: list[dict[str, Any]],
    header: dict[str, Any] | None,
    network_ids: set[str],
    preset_ids: set[str],
) -> dict[str, Any]:
    available = [i for i in items if i["available"]]
    nets = sorted({str(i["network_id"]) for i in items if i.get("network_id")})
    single_net = nets[0] if len(nets) == 1 and nets[0] in network_ids else None
    scenario_ids = sorted(
        str(i.get("scenario_id") or i["artifact_id"]) for i in items if group.engine == "pypsa"
    )
    use = {
        "available": False,
        "network_id": None,
        "preset_id": None,
        "route": None,
        "rationale": "Precomputed study results; open the research page to explore them.",
    }
    if group.id == "observed-analogues":
        runnable = [s for s in scenario_ids if s in preset_ids]
        if runnable and single_net and len(runnable) == len(available) == len(items):
            use = {
                "available": True,
                "network_id": single_net,
                "preset_id": runnable[0],
                "route": f"/studio?network={single_net}&preset={runnable[0]}",
                "rationale": "Published as precomputed scigrid-de presets with full PyPSA results "
                f"({', '.join(runnable)}); Studio serves the committed result.",
            }
        else:
            use["rationale"] = "Analogue presets are not published in this deployment."
    checks = [
        {
            "name": "artifact_files",
            "status": "pass" if len(available) == len(items) else "warn",
            "detail": f"{len(available)} of {len(items)} indexed artifact file(s) present; payload "
            "sha256 is verified per artifact by /api/v1/artifacts/{engine}/{artifact_id}",
        }
    ]
    return {
        "id": f"study-{group.id}",
        "title": group.title,
        "summary": group.summary,
        "description": f"{group.summary}\n\nArtifacts: "
        + ", ".join(f"`{group.engine}/{i['artifact_id']}`" for i in items),
        "category": "precomputed_experiment",
        "provenance": group.provenance,
        "data_nature": group.data_nature,
        "region": None,
        "source": {
            "name": f"GridStorm precomputed artifacts ({group.engine})",
            "publisher": "GridStorm",
            "url": f"{REPO_TREE}data/artifacts/{group.engine}",
            "version": (header or {}).get("engine_version"),
            "doi": None,
            "retrieved_at": None,
            "source_sha256": None,
            "license": {
                "id": "MIT",
                "name": "GridStorm (MIT); input networks keep their own licences",
                "url": f"{REPO_BLOB}LICENSE",
                "redistribution": "derived-only",
            },
            "attribution": "GridStorm contributors; inputs listed in each artifact header",
        },
        "temporal": None,
        "spatial": {"kind": "network" if single_net else "none", "points": None},
        "series": [],
        "quality": _quality(checks, []),
        "transformations": [],
        "transformation_version": (header or {}).get("schema_version"),
        "artifact": None,
        "links": {
            "network_id": single_net,
            "scenario_ids": scenario_ids,
            "study_route": group.route,
            "docs": [_doc(label, path) for label, path in group.docs]
            + [
                {
                    "label": "Research Workbench",
                    "href": f"/workbench?study={group.workbench_study or group.id}",
                }
            ],
        },
        "use_in_scenario": use,
        "exportable": False,
    }


# --- merged catalog -----------------------------------------------------------------------------
SUMMARY_DROP = ("description", "transformations")


def summarize(entry: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in entry.items() if k not in SUMMARY_DROP}
    out["quality"] = {k: v for k, v in entry["quality"].items() if k != "checks"}
    return out


def validate_use_in_scenario(
    entry: dict[str, Any], presets: dict[str, list[str]], network_ids: set[str]
) -> dict[str, Any]:
    """A bundle entry's declared ``use_in_scenario`` mapping, checked against this deployment.

    ``available: true`` survives only when its network is in the catalog and its ``preset_id``
    (if any) is a valid preset of that network; otherwise it is downgraded to ``available:
    false`` with a quality warning. Returns a copy; the loaded bundle entry is left untouched.
    """
    use = entry["use_in_scenario"]
    if not use["available"]:
        return entry
    net, preset = use.get("network_id"), use.get("preset_id")
    problem = None
    if net not in network_ids:
        problem = f"network {net!r} is not in the network catalog"
    elif preset is not None and preset not in presets.get(net, []):
        problem = f"preset {preset!r} is not a published preset of {net!r}"
    if problem is None:
        return entry
    log.error("dataset %s: use_in_scenario downgraded: %s", entry["id"], problem)
    quality = {
        **entry["quality"],
        "warnings": [*entry["quality"]["warnings"], f"use_in_scenario unavailable: {problem}"],
    }
    return {
        **entry,
        "quality": quality,
        "use_in_scenario": {
            **use,
            "available": False,
            "route": None,
            "rationale": f"Declared scenario mapping not available in this deployment: {problem}.",
        },
    }


@dataclass
class Merged:
    entries: list[dict[str, Any]]
    by_id: dict[str, dict[str, Any]]
    facets: dict[str, dict[str, int]]


class DataObservatory:
    """Lazy, thread-safe merged catalog (bundle + networks + experiments)."""

    def __init__(
        self,
        settings: Settings,
        networks: NetworkCatalog,
        precomputed: PrecomputedArtifacts,
    ) -> None:
        self.settings = settings
        self.root = settings.data_dir / "observatory"
        self.networks = networks
        self.precomputed = precomputed
        self._bundle_lock = threading.Lock()
        self._merged_lock = threading.Lock()
        self._bundle: BundleState | None = None
        self._merged: Merged | None = None

    def reload(self) -> None:
        with self._merged_lock, self._bundle_lock:
            self._bundle = None
            self._merged = None

    def bundle(self) -> BundleState:
        with self._bundle_lock:
            if self._bundle is None:
                self._bundle = load_bundle(self.root)
            return self._bundle

    def _preset_networks(self) -> dict[str, list[str]]:
        from .sync import load_preset_specs
        from .validation import validate_spec

        out: dict[str, list[str]] = {}
        for _name, spec in load_preset_specs(self.settings.resolved_presets_dir):
            outcome = validate_spec(spec, self.networks, for_execution=False)
            if outcome.valid and outcome.scenario is not None:
                sc = outcome.scenario
                out.setdefault(sc.dataset.network_id, []).append(sc.id)
        return {k: sorted(v) for k, v in out.items()}

    def _build(self) -> Merged:
        presets = self._preset_networks()
        nets = self.networks.entries()
        entries = [
            validate_use_in_scenario(d.entry, presets, set(nets))
            for d in self.bundle().datasets.values()
        ]
        for net_id in sorted(nets):
            live = self.settings.live_execution(net_id)
            ids = presets.get(net_id, [])
            ready = nets[net_id].network_nc.is_file() and (live or bool(ids))
            entries.append(network_entry(nets[net_id], ids, live, ready))
        index = self.precomputed.index()
        all_presets = {p for ids in presets.values() for p in ids}
        for group in STUDY_GROUPS:
            items = [i for i in index if group.matches(i)]
            if not items:
                continue
            first = next((i for i in items if i["available"]), None)
            header = (
                self.precomputed.header(first["engine"], first["artifact_id"]) if first else None
            )
            entries.append(experiment_entry(group, items, header, set(nets), all_presets))
        by_id: dict[str, dict[str, Any]] = {}
        unique: list[dict[str, Any]] = []
        for e in entries:
            if e["id"] in by_id:
                log.error("duplicate data catalog id %s; first one kept", e["id"])
                continue
            by_id[e["id"]] = e
            unique.append(e)
        return Merged(entries=unique, by_id=by_id, facets=facets(unique))

    def merged(self) -> Merged:
        with self._merged_lock:
            if self._merged is None:
                self._merged = self._build()
            return self._merged

    def get(self, dataset_id: str) -> dict[str, Any]:
        entry = self.merged().by_id.get(dataset_id)
        if entry is None:
            raise NotFound(f"unknown dataset {dataset_id!r}", details={"dataset_id": dataset_id})
        return entry

    def series_dataset(self, dataset_id: str) -> tuple[dict[str, Any], SeriesTable]:
        entry = self.get(dataset_id)
        ds = self.bundle().datasets.get(dataset_id)
        if ds is None or not entry["series"]:
            raise Conflict(
                f"dataset {dataset_id!r} has no time series",
                code="not_a_series_dataset",
                details={"dataset_id": dataset_id, "category": entry["category"]},
            )
        if ds.failure or ds.table is None:
            raise ServiceUnavailable(
                f"dataset {dataset_id!r} failed checksum verification and is not served",
                code="dataset_unverified",
                details={"dataset_id": dataset_id, "reason": ds.failure},
            )
        return entry, ds.table


def facets(entries: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    def count(key: Any) -> dict[str, int]:
        c = Counter(k for k in (key(e) for e in entries) if k)
        return dict(sorted(c.items()))

    return {
        "category": count(lambda e: e["category"]),
        "provenance": count(lambda e: e["provenance"]),
        "region": count(lambda e: (e.get("region") or {}).get("code")),
        "source": count(lambda e: e["source"]["name"]),
    }


def matches(
    entry: dict[str, Any],
    *,
    category: str | None,
    provenance: str | None,
    region: str | None,
    source: str | None,
    q: str | None,
) -> bool:
    if category and entry["category"] != category:
        return False
    if provenance and entry["provenance"] != provenance:
        return False
    if region and (entry.get("region") or {}).get("code") != region:
        return False
    if source and entry["source"]["name"] != source:
        return False
    if q:
        needle = q.strip().lower()
        src = entry["source"]
        hay = " ".join(
            str(x or "")
            for x in (
                entry["id"],
                entry["title"],
                entry["summary"],
                entry["data_nature"],
                src.get("name"),
                src.get("publisher"),
            )
        ).lower()
        if needle not in hay:
            return False
    return True


# --- series -------------------------------------------------------------------------------------
@dataclass
class Window:
    start: int
    end: int  # exclusive


def resolve_window(
    entry: dict[str, Any], table: SeriesTable, start: str | None, end: str | None
) -> Window:
    a = parse_query_utc(start, "start") if start else None
    b = parse_query_utc(end, "end") if end else None
    if a is None and b is None:
        windows = (entry.get("temporal") or {}).get("windows") or []
        if windows:
            # catalog windows (like temporal.end_utc) name their last covered timestamp
            a = parse_query_utc(windows[0]["start_utc"], "start")
            b = parse_query_utc(windows[0]["end_utc"], "end") + table.step_s
            b = max(b, a + table.step_s)
        elif table.rows:
            b = table.times[-1] + table.step_s
            a = max(table.times[0], b - DEFAULT_WINDOW_S)
        else:
            raise Unprocessable("dataset has no rows", code="empty_dataset")
    elif a is None:
        a = b - DEFAULT_WINDOW_S  # type: ignore[operator]
    elif b is None:
        b = a + DEFAULT_WINDOW_S
    assert a is not None and b is not None
    if b <= a:
        raise Unprocessable(
            "end must be after start",
            code="invalid_range",
            details={"start_utc": iso_utc(a), "end_utc": iso_utc(b)},
        )
    if b - a > MAX_RANGE_S:
        raise Unprocessable(
            "requested range exceeds 3 years",
            code="range_too_large",
            details={"start_utc": iso_utc(a), "end_utc": iso_utc(b), "max_days": 1096},
        )
    return Window(a, b)


def select_series(entry: dict[str, Any], series: str | None) -> list[dict[str, Any]]:
    declared = {s["id"]: s for s in entry["series"]}
    if not series:
        return list(entry["series"])
    wanted = [s.strip() for s in series.split(",") if s.strip()]
    unknown = [s for s in wanted if s not in declared]
    if unknown or not wanted:
        raise Unprocessable(
            "unknown series requested",
            code="unknown_series",
            details={"unknown": unknown, "available": list(declared)},
        )
    return [declared[s] for s in dict.fromkeys(wanted)]


def _raw_slots(table: SeriesTable, w: Window) -> tuple[int, int]:
    """First raw-grid timestamp ≥ start (grid anchored at the first row) and the slot count."""
    step = table.step_s
    anchor = table.times[0] if table.rows else w.start
    first = anchor - ((anchor - w.start) // step) * step  # anchor + ceil((start - anchor) / step)
    n = 0 if first >= w.end else (w.end - first + step - 1) // step
    return first, n


def _bucket_slots(w: Window, step: int, offset: int) -> tuple[int, int]:
    first = (w.start - offset) // step * step + offset
    return first, (w.end - first + step - 1) // step


def compute_series(
    entry: dict[str, Any],
    table: SeriesTable,
    *,
    bundle_version: str | None,
    series: str | None,
    start: str | None,
    end: str | None,
    resolution: str,
    agg: str,
    max_points: int,
) -> dict[str, Any]:
    chosen = select_series(entry, series)
    w = resolve_window(entry, table, start, end)
    raw_first, raw_n = _raw_slots(table, w)
    candidates: list[tuple[str, int, int]] = []
    if resolution == "auto":
        candidates = [("raw", table.step_s, 0)] + [b for b in BUCKETS if b[1] > table.step_s]
    elif resolution == "raw":
        candidates = [("raw", table.step_s, 0)]
    else:
        bucket = next(b for b in BUCKETS if b[0] == resolution)
        if bucket[1] < table.step_s:
            raise Unprocessable(
                f"resolution {resolution} is finer than the raw data",
                code="resolution_finer_than_raw",
                details={"raw_resolution": entry["temporal"]["resolution"]},
            )
        candidates = [bucket]
    pick = None
    for code, step, offset in candidates:
        n = raw_n if code == "raw" else _bucket_slots(w, step, offset)[1]
        if n <= max_points:
            pick = (code, step, offset)
            break
    if pick is None:
        code, step, offset = candidates[-1]
        n = raw_n if code == "raw" else _bucket_slots(w, step, offset)[1]
        raise Unprocessable(
            f"{n} points at {code} exceed max_points={max_points}; narrow the range or "
            "use a coarser resolution",
            code="range_too_large",
            details={"points": n, "max_points": max_points, "resolution": code},
        )
    code, step, offset = pick
    lo = bisect_left(table.times, w.start)
    hi = bisect_left(table.times, w.end)
    times = table.times
    out_series = []
    missing: dict[str, int] = {}
    if code == "raw":
        timestamps = [iso_utc(raw_first + k * step) for k in range(raw_n)]
        for s in chosen:
            col = table.columns[s["id"]]
            values: list[float | None] = [None] * raw_n
            for r in range(lo, hi):
                v = col[r]
                if not math.isnan(v):
                    values[(times[r] - raw_first) // step] = v
            missing[s["id"]] = sum(1 for v in values if v is None)
            out_series.append(
                {"id": s["id"], "label": s["label"], "unit": s["unit"], "values": values}
            )
        aggregation = None
    else:
        first, n = _bucket_slots(w, step, offset)
        timestamps = [iso_utc(first + k * step) for k in range(n)]
        for s in chosen:
            col = table.columns[s["id"]]
            acc: list[list[float]] = [[] for _ in range(n)]
            observed = 0
            for r in range(lo, hi):
                v = col[r]
                if not math.isnan(v):
                    acc[(times[r] - first) // step].append(v)
                    observed += 1
            if agg == "mean":
                values = [round(math.fsum(b) / len(b), 6) if b else None for b in acc]
            elif agg == "min":
                values = [min(b) if b else None for b in acc]
            else:
                values = [max(b) if b else None for b in acc]
            missing[s["id"]] = raw_n - observed
            out_series.append(
                {"id": s["id"], "label": s["label"], "unit": s["unit"], "values": values}
            )
        aggregation = agg
    return {
        "dataset_id": entry["id"],
        "bundle_version": bundle_version,
        "sha256": entry["artifact"]["sha256"],
        "start_utc": iso_utc(w.start),
        "end_utc": iso_utc(w.end),
        "resolution": code,
        "raw_resolution": entry["temporal"]["resolution"],
        "aggregation": aggregation,
        "points": len(timestamps),
        "series": out_series,
        "timestamps": timestamps,
        "missing": missing,
    }


def _comment(text: Any) -> str:
    return " ".join(str(text).split())


def ensure_exportable(entry: dict[str, Any]) -> None:
    if not entry["exportable"]:
        raise Forbidden(
            f"dataset {entry['id']!r} may not be exported as raw values",
            code="export_not_permitted",
            details={"redistribution": entry["source"]["license"]["redistribution"]},
        )


def export_csv(
    entry: dict[str, Any],
    table: SeriesTable,
    *,
    bundle_version: str | None,
    series: str | None,
    start: str | None,
    end: str | None,
) -> tuple[bytes, str]:
    ensure_exportable(entry)
    chosen = select_series(entry, series)
    w = resolve_window(entry, table, start, end)
    src, lic, art = entry["source"], entry["source"]["license"], entry["artifact"]
    buf = io.StringIO()
    header = [
        f"dataset: {entry['id']} - {entry['title']}",
        f"provenance: {entry['provenance']} ({entry['data_nature']})",
        f"source: {src['name']}; publisher: {src.get('publisher')}; url: {src.get('url')}; "
        f"version: {src.get('version')}; doi: {src.get('doi')}",
        f"license: {lic.get('id')} ({lic.get('name')}) {lic.get('url')}",
        f"attribution: {src.get('attribution')}",
        f"sha256: {art['sha256']} ({art['path']}, bundle {bundle_version})",
        f"window: [{iso_utc(w.start)}, {iso_utc(w.end)}) UTC; resolution "
        f"{entry['temporal']['resolution']} (raw); empty cell = missing value (never 0); "
        "timestamps absent from the source are not covered",
    ]
    for line in header:
        buf.write(f"# {_comment(line)}\n")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["utc", *(s["id"] for s in chosen)])
    cols = [table.columns[s["id"]] for s in chosen]
    for r in range(bisect_left(table.times, w.start), bisect_left(table.times, w.end)):
        writer.writerow(
            [iso_utc(table.times[r]), *("" if math.isnan(c[r]) else repr(c[r]) for c in cols)]
        )
    name = f"{entry['id']}_{iso_utc(w.start)[:10]}_{iso_utc(w.end)[:10]}.csv"
    return buf.getvalue().encode("utf-8"), name
