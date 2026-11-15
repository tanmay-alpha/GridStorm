"""Comparison of two completed simulation results on the same network, and reproducible reports.

All deltas are ``scenario - baseline``; ``delta_pct`` is relative to |baseline| and null when the
baseline is 0 or a value is missing. Missing values stay null — they are never treated as 0.
Branch loading is the maximum over snapshots of |loading_pct| (lines, transformers) and, for
links, of |flow_mw| / p_nom_mw · 100 (calculated here).
"""

from __future__ import annotations

import math
from typing import Any

from sqlalchemy.orm import Session

from . import __version__
from .db.models import NetworkVersion, SimulationJob, utcnow
from .jobs.service import iso

COMPARISON_SCHEMA = "gridstorm-comparison/1.0"
JOB_REPORT_SCHEMA = "gridstorm-run-report/1.0"

COMPARISON_ASSUMPTIONS = [
    "Deltas are scenario minus baseline, computed from the stored gridstorm-result documents.",
    "Both runs use the same network dataset; differences reflect the scenario specification only "
    "within the stated model assumptions of each run.",
    "Results are model outputs (provenance: modeled); deltas are provenance: calculated. They are "
    "not observations or predictions of real grid behaviour.",
]

_UNITS = (
    ("_mwh", "MWh"),
    ("_mw", "MW"),
    ("_pct", "%"),
    ("_hours", "h"),
    ("_h", "h"),
    ("_t", "t"),
    ("_count", "count"),
)


def unit_of(name: str, cost_basis: dict[str, Any] | None = None) -> str | None:
    basis = cost_basis or {}
    if name.endswith("_eur_per_mwh"):
        return basis.get("price_unit") or "cost units (basis unknown)/MWh"
    if name.endswith("_eur"):
        return basis.get("money_unit") or "cost units (basis unknown)"
    for suffix, unit in _UNITS:
        if name.endswith(suffix):
            return unit
    return None


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, int | float):
        return None
    f = float(v)
    return f if math.isfinite(f) else None


def delta_row(base: Any, scen: Any) -> dict[str, float | None]:
    b, s = _num(base), _num(scen)
    delta = s - b if b is not None and s is not None else None
    pct = delta / abs(b) * 100.0 if delta is not None and b not in (None, 0.0) else None
    return {"baseline": b, "scenario": s, "delta": delta, "delta_pct": pct}


def _max_abs(values: Any) -> float | None:
    nums = [abs(x) for x in (_num(v) for v in values or []) if x is not None]
    return max(nums) if nums else None


def branch_max_loading(result: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    assets = result.get("assets") or {}
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for key, component in (("lines", "line"), ("transformers", "transformer")):
        for row in assets.get(key) or []:
            out[(component, str(row.get("id")))] = {
                "max_loading_pct": _max_abs(row.get("loading_pct")),
                "outaged": row.get("outaged"),
            }
    for row in assets.get("links") or []:
        p_nom = _num(row.get("p_nom_mw"))
        peak = _max_abs(row.get("flow_mw"))
        loading = peak / p_nom * 100.0 if peak is not None and p_nom else None
        out[("link", str(row.get("id")))] = {
            "max_loading_pct": loading,
            "outaged": row.get("outaged"),
        }
    return out


def legacy_report_cost_basis(
    report: dict[str, Any], basis: dict[str, Any] | None
) -> dict[str, Any]:
    """Hydrate old stored comparisons without rewriting their durable database document."""
    if report.get("cost_basis"):
        return report
    from copy import deepcopy

    resolved = deepcopy(report)
    resolved["cost_basis"] = basis
    resolved["costs_comparable"] = bool(basis and basis.get("comparability_key"))
    for label in ("baseline", "scenario"):
        if label in resolved:
            resolved[label]["cost_basis"] = basis
    for metric in resolved.get("metrics") or []:
        name = metric["metric"]
        if name.endswith(("_eur", "_eur_per_mwh")):
            metric["unit"] = unit_of(name, basis)
            metric["delta_unit"] = metric["unit"]
            if not resolved["costs_comparable"]:
                metric.update(delta=None, delta_pct=None)
        # Reports stored before percentage points existed (POST-11) have no delta_unit.
        metric.setdefault("delta_unit", "pp" if metric.get("unit") == "%" else metric.get("unit"))
    for field in ("assumptions", "warnings"):
        resolved[field] = [
            text.replace(" EUR/MWh", f" {unit_of('price_eur_per_mwh', basis)}")
            for text in resolved.get(field) or []
        ]
    return resolved


def compare_results(baseline: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    warnings: list[str] = []
    for label, res in (("baseline", baseline), ("scenario", scenario)):
        if res.get("outcome") != "feasible":
            warnings.append(
                f"{label} run outcome is {res.get('outcome')!r}: its metrics/series may be empty; "
                "affected deltas are null"
            )
    bm, sm = baseline.get("metrics") or {}, scenario.get("metrics") or {}
    bb, sb = baseline.get("cost_basis"), scenario.get("cost_basis")
    comparable = bool(
        bb
        and sb
        and bb.get("comparability_key")
        and bb.get("comparability_key") == sb.get("comparability_key")
    )
    if not comparable and any(n.endswith(("_eur", "_eur_per_mwh")) for n in set(bm) | set(sm)):
        warnings.append("Cost bases differ or are unknown: monetary deltas are withheld.")
    metrics = []
    for name in sorted(set(bm) | set(sm)):
        if isinstance(bm.get(name), dict) or isinstance(sm.get(name), dict):
            continue
        monetary = name.endswith(("_eur", "_eur_per_mwh"))
        unit = unit_of(name, bb) if comparable or not monetary else None
        row = delta_row(bm.get(name), sm.get(name))
        if monetary and not comparable:
            row.update(delta=None, delta_pct=None)
        metrics.append(
            {
                "metric": name,
                "unit": unit,
                # An absolute change of a percentage is in percentage points, not percent.
                "delta_unit": "pp" if unit == "%" else unit,
                **row,
            }
        )

    carriers: dict[str, list[dict[str, Any]]] = {}
    for name in ("generation_by_carrier_mwh", "curtailment_by_carrier_mwh"):
        b, s = bm.get(name) or {}, sm.get(name) or {}
        carriers[name] = [
            {"carrier": c, **delta_row(b.get(c), s.get(c))} for c in sorted(set(b) | set(s))
        ]

    bl, sl = branch_max_loading(baseline), branch_max_loading(scenario)
    branches = []
    for key in set(bl) | set(sl):
        b, s = bl.get(key, {}), sl.get(key, {})
        row = delta_row(b.get("max_loading_pct"), s.get("max_loading_pct"))
        branches.append(
            {
                "component": key[0],
                "id": key[1],
                "baseline_max_loading_pct": row["baseline"],
                "scenario_max_loading_pct": row["scenario"],
                "delta_pct_points": row["delta"],
                "baseline_outaged": b.get("outaged"),
                "scenario_outaged": s.get("outaged"),
            }
        )
    branches.sort(
        key=lambda r: (
            r["delta_pct_points"] is None,
            -abs(r["delta_pct_points"] or 0.0),
            r["component"],
            r["id"],
        )
    )
    return {
        "costs_comparable": comparable,
        "metrics": metrics,
        "carriers": carriers,
        "branch_loading": branches,
        "warnings": warnings,
    }


def run_manifest(session: Session, job: SimulationJob, result: dict[str, Any]) -> dict[str, Any]:
    version = (
        session.get(NetworkVersion, job.network_version_id) if job.network_version_id else None
    )
    execution = (job.spec or {}).get("execution") or {}
    return {
        "job_id": str(job.id),
        "scenario_id": job.scenario_id,
        "scenario_hash": job.scenario_hash,
        "scenario_spec": job.spec,
        "execution_mode": job.execution_mode,
        "reused": job.reused,
        "reused_from_job_id": str(job.reused_from_job_id) if job.reused_from_job_id else None,
        "result_sha256": job.result_sha256,
        "dataset": {
            "network_id": job.network_id,
            "network_sha256": version.network_sha256 if version else None,
            "canonical_sha256": version.canonical_sha256 if version else None,
            "manifest_sha256": version.manifest_sha256 if version else None,
            "source": (version.manifest or {}).get("source") if version else None,
            "license": (version.manifest or {}).get("license") if version else None,
        },
        "engine": result.get("engine"),
        "solver": {**(result.get("solver") or {}), "options": execution.get("solver_options")},
        "execution_manifest": result.get("manifest"),
        "finished_at": iso(job.finished_at),
    }


def _generated(git_sha: str | None) -> dict[str, Any]:
    return {"generated_at": iso(utcnow()), "api_version": __version__, "git_sha": git_sha}


def build_comparison_report(
    session: Session,
    baseline_job: SimulationJob,
    scenario_job: SimulationJob,
    baseline: dict[str, Any],
    scenario: dict[str, Any],
    git_sha: str | None,
) -> dict[str, Any]:
    body = compare_results(baseline, scenario)
    assumptions = list(COMPARISON_ASSUMPTIONS)
    for res in (baseline, scenario):
        for a in res.get("assumptions") or []:
            if a not in assumptions:
                assumptions.append(a)
    return {
        "schema_version": COMPARISON_SCHEMA,
        "provenance": "calculated",
        "network_id": baseline_job.network_id,
        "cost_basis": baseline.get("cost_basis"),
        "costs_comparable": body["costs_comparable"],
        "baseline": _run_ref(baseline_job, baseline),
        "scenario": _run_ref(scenario_job, scenario),
        **body,
        "assumptions": assumptions,
        "reproducibility": {
            **_generated(git_sha),
            "baseline": run_manifest(session, baseline_job, baseline),
            "scenario": run_manifest(session, scenario_job, scenario),
        },
    }


def _run_ref(job: SimulationJob, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_id": str(job.id),
        "scenario_id": job.scenario_id,
        "scenario_name": (job.spec or {}).get("name"),
        "scenario_hash": job.scenario_hash,
        "outcome": result.get("outcome"),
        "cost_basis": result.get("cost_basis"),
    }


def build_job_report(
    session: Session, job: SimulationJob, result: dict[str, Any], git_sha: str | None
) -> dict[str, Any]:
    metrics = result.get("metrics") or {}
    return {
        "schema_version": JOB_REPORT_SCHEMA,
        "provenance": "modeled",
        "network_id": job.network_id,
        "cost_basis": result.get("cost_basis"),
        "run": _run_ref(job, result),
        "metrics": [
            {"metric": k, "unit": unit_of(k, result.get("cost_basis")), "value": _num(v)}
            for k, v in sorted(metrics.items())
            if not isinstance(v, dict)
        ],
        "carriers": {
            k: metrics.get(k) or {}
            for k in ("generation_by_carrier_mwh", "curtailment_by_carrier_mwh")
        },
        "warnings": list(result.get("warnings") or []),
        "assumptions": list(result.get("assumptions") or []),
        "reproducibility": {**_generated(git_sha), "run": run_manifest(session, job, result)},
    }


# --------------------------------------------------------------------------------------------
# Markdown rendering


def _fmt(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:,.4g}" if abs(v) < 1e5 else f"{v:,.0f}"
    return str(v)


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(_fmt(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def _repro_md(title: str, m: dict[str, Any]) -> str:
    ds, eng, sol = m["dataset"], m.get("engine") or {}, m.get("solver") or {}
    return "\n".join(
        [
            f"### {title}",
            f"- job: `{m['job_id']}` ({m['execution_mode']}{', reused' if m['reused'] else ''})",
            f"- scenario: `{m['scenario_id']}` hash `{m['scenario_hash']}`",
            f"- dataset: `{ds['network_id']}` network.nc sha256 `{ds['network_sha256']}`",
            f"- engine: {eng.get('name')} {eng.get('version')} ({eng.get('formulation')})",
            f"- solver: {sol.get('name')} {sol.get('version')} — "
            f"{sol.get('termination_condition')}",
            f"- result sha256: `{m['result_sha256']}`",
            "",
            "<details><summary>Scenario specification (stormspec/1.0)</summary>",
            "",
            "```json",
            _json(m["scenario_spec"]),
            "```",
            "</details>",
        ]
    )


def _json(obj: Any) -> str:
    import json

    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False)


def comparison_markdown(report: dict[str, Any], comparison_id: str) -> str:
    b, s = report["baseline"], report["scenario"]
    parts = [
        f"# GridStorm comparison `{comparison_id}`",
        "",
        f"Network `{report['network_id']}` — baseline **{b['scenario_name']}** "
        f"(`{b['job_id']}`, outcome {b['outcome']}) vs scenario **{s['scenario_name']}** "
        f"(`{s['job_id']}`, outcome {s['outcome']}).",
        "",
        "Values are model outputs (provenance: modeled); deltas are calculated (scenario − "
        "baseline). This is not a prediction of real grid behaviour.",
        "",
        f"Cost basis: {(report.get('cost_basis') or {}).get('money_unit', 'unknown')}. "
        f"Costs comparable: {report.get('costs_comparable', False)}.",
        "",
    ]
    if report["warnings"]:
        parts += ["**Warnings**", ""] + [f"- {w}" for w in report["warnings"]] + [""]
    parts += [
        "## Metrics",
        "",
        _table(
            ["metric", "unit", "baseline", "scenario", "delta", "delta unit", "relative delta %"],
            [
                [
                    m["metric"],
                    m["unit"],
                    m["baseline"],
                    m["scenario"],
                    m["delta"],
                    m["delta_unit"],
                    m["delta_pct"],
                ]
                for m in report["metrics"]
            ],
        ),
        "",
    ]
    for name, rows in report["carriers"].items():
        parts += [
            f"## {name}",
            "",
            _table(
                ["carrier", "baseline", "scenario", "delta", "delta %"],
                [
                    [r["carrier"], r["baseline"], r["scenario"], r["delta"], r["delta_pct"]]
                    for r in rows
                ],
            )
            if rows
            else "_no data_",
            "",
        ]
    top = report["branch_loading"][:20]
    parts += [
        f"## Branch loading (max over time; top {len(top)} of {len(report['branch_loading'])} "
        "by |delta|)",
        "",
        _table(
            ["component", "id", "baseline %", "scenario %", "delta (pp)", "outaged (b/s)"],
            [
                [
                    r["component"],
                    r["id"],
                    r["baseline_max_loading_pct"],
                    r["scenario_max_loading_pct"],
                    r["delta_pct_points"],
                    f"{r['baseline_outaged']}/{r['scenario_outaged']}",
                ]
                for r in top
            ],
        )
        if top
        else "_no branch data_",
        "",
        "## Assumptions",
        "",
        *[f"- {a}" for a in report["assumptions"]],
        "",
        "## Reproducibility",
        "",
        f"Generated {report['reproducibility']['generated_at']} by gridstorm-api "
        f"{report['reproducibility']['api_version']} (git {report['reproducibility']['git_sha']}).",
        "",
        _repro_md("Baseline", report["reproducibility"]["baseline"]),
        "",
        _repro_md("Scenario", report["reproducibility"]["scenario"]),
        "",
    ]
    return "\n".join(parts)


def job_markdown(report: dict[str, Any]) -> str:
    run = report["run"]
    parts = [
        f"# GridStorm run `{run['job_id']}`",
        "",
        f"Scenario **{run['scenario_name']}** (`{run['scenario_id']}`) on network "
        f"`{report['network_id']}` — outcome **{run['outcome']}**.",
        "",
        "Values are model outputs (provenance: modeled), not observations or predictions.",
        "",
        f"Cost basis: {(report.get('cost_basis') or {}).get('money_unit', 'unknown')}.",
        "",
    ]
    if report["warnings"]:
        parts += ["**Warnings**", ""] + [f"- {w}" for w in report["warnings"]] + [""]
    parts += [
        "## Metrics",
        "",
        _table(
            ["metric", "unit", "value"],
            [[m["metric"], m["unit"], m["value"]] for m in report["metrics"]],
        ),
        "",
    ]
    for name, values in report["carriers"].items():
        parts += [
            f"## {name}",
            "",
            _table(["carrier", "value"], [[k, values[k]] for k in sorted(values)])
            if values
            else "_no data_",
            "",
        ]
    parts += [
        "## Assumptions",
        "",
        *[f"- {a}" for a in report["assumptions"]],
        "",
        "## Reproducibility",
        "",
        f"Generated {report['reproducibility']['generated_at']} by gridstorm-api "
        f"{report['reproducibility']['api_version']} (git {report['reproducibility']['git_sha']}).",
        "",
        _repro_md("Run", report["reproducibility"]["run"]),
        "",
    ]
    return "\n".join(parts)
