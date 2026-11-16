#!/usr/bin/env python3
# ruff: noqa: E501 — long lines are inline SQL kept on one line for copy/paste into psql
"""Read-only production data inventory for GridStorm (feeds docs/data/production-inventory.md).

Three independent sections, written to one JSON report plus a Markdown rendering (``.md``):

* ``repo`` — committed files (networks, observed data, analogue scenarios, artifacts) and what
  the API image ships (``.dockerignore`` allow-list). No network access.
* ``api``  — anonymous ``GET`` requests against the public API (jobs, networks, scenarios,
  artifacts). No credentials, no writes.
* ``db``   — Supabase Postgres + ``storage`` schema. Every statement runs inside a
  ``READ ONLY`` transaction that is rolled back; no INSERT/UPDATE/DELETE/DDL is issued.
  Credentials come from ``DATABASE_URL`` (Supabase session-pooler URI) or, if unset,
  ``SUPABASE_DB_HOST/PORT/NAME/USER/PASSWORD``; placeholders are rejected. The host and
  password are never printed or stored — only the project ref from a ``postgres.<ref>`` user.
  The connection is autocommit; each audit runs as ``BEGIN READ ONLY`` … ``ROLLBACK`` and
  asserts ``transaction_read_only = on`` first. ``SET LOCAL ROLE anon`` probes are SELECT-only.

Run from ``services/api`` (psycopg comes from its venv)::

    uv run --locked python ../../scripts/inventory/production_inventory.py \
        --sections repo,api,db --out ../../var/inventory/production-inventory.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
API = "https://gridstorm-api.onrender.com"
BUCKET = "gridstorm-artifacts"


# --------------------------------------------------------------------------------------- repo
def _dir_stats(path: Path) -> dict[str, Any]:
    files = [p for p in path.rglob("*") if p.is_file()] if path.is_dir() else []
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "exists": path.exists(),
        "files": len(files),
        "bytes": sum(p.stat().st_size for p in files),
    }


def _dockerignore_allow() -> list[str]:
    lines = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    return [ln[1:].rstrip("/") for ln in lines if ln.startswith("!")]


def section_repo() -> dict[str, Any]:
    allow = _dockerignore_allow()

    def in_image(rel: str) -> bool:
        return any(rel == a or rel.startswith(a + "/") for a in allow)

    catalog = json.loads((ROOT / "data/networks/catalog.json").read_text(encoding="utf-8"))
    networks = []
    for n in catalog["networks"]:
        d = ROOT / "data/networks" / n["path"]
        manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        canon = d / "canonical.json"
        networks.append(
            {
                "id": n["id"],
                **_dir_stats(d),
                "canonical_sha256": hashlib.sha256(canon.read_bytes()).hexdigest()
                if canon.exists()
                else None,
                "manifest_sha256": hashlib.sha256((d / "manifest.json").read_bytes()).hexdigest(),
                "provenance_class": manifest.get("provenance_class"),
                "license_spdx": (manifest.get("license") or {}).get("spdx"),
                "redistribution": (manifest.get("license") or {}).get("redistribution"),
                "in_image": in_image(d.relative_to(ROOT).as_posix()),
            }
        )
    families = {}
    for rel in [
        "data/observed/opsd-de",
        "data/observed/nasa-power-de",
        "data/observed/analogue-results.json",
        "data/scenarios/observed",
        "packages/stormspec/presets",
        *sorted(
            p.relative_to(ROOT).as_posix()
            for p in (ROOT / "data/artifacts").iterdir()
            if p.is_dir()
        ),
    ]:
        p = ROOT / rel
        st = (
            _dir_stats(p)
            if p.is_dir()
            else {
                "path": rel,
                "exists": p.exists(),
                "files": int(p.exists()),
                "bytes": p.stat().st_size if p.exists() else 0,
            }
        )
        families[rel] = {**st, "in_image": in_image(rel)}
    return {"dockerignore_allow": allow, "networks": networks, "families": families}


# ---------------------------------------------------------------------------------------- api
# Comparison ids recorded in committed docs (there is no list endpoint; see
# docs/audit/live-2026-11-15-round2.md). 9257ed4c predates Postgres (SQLite era).
KNOWN_COMPARISONS = (
    "4f5661ec-e6f1-4600-96ed-710709f10c36",
    "9257ed4c-359c-4862-9001-a32f4b031981",
    "a3ef641c-7748-40fd-867a-75b4696f6cf2",
)


def _fetch(path: str) -> dict[str, Any]:
    """Anonymous GET; returns status, parsed JSON (if any), body sha256/bytes, headers, ms."""
    t0 = time.perf_counter()
    req = Request(
        API + path, headers={"Accept": "application/json", "User-Agent": "GridStorm-Inventory/1"}
    )
    try:
        with urlopen(req, timeout=60) as r:
            body, status, headers = r.read(), r.status, dict(r.headers.items())
    except HTTPError as exc:
        body, status, headers = exc.read(), exc.code, dict(exc.headers.items())
    ms = (time.perf_counter() - t0) * 1000
    try:
        data = json.loads(body)
    except ValueError:
        data = None
    return {
        "status": status,
        "data": data,
        "ms": ms,
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "headers": {k.lower(): v for k, v in headers.items()},
    }


def _paged(path: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    offset = 0
    while True:
        sep = "&" if "?" in path else "?"
        r = _fetch(f"{path}{sep}limit=500&offset={offset}")
        if r["status"] != 200:
            raise RuntimeError(f"GET {path}: HTTP {r['status']}")
        items += r["data"]["items"]
        offset += len(r["data"]["items"])
        if not r["data"]["items"] or offset >= r["data"]["total"]:
            return items


def _error_code(r: dict[str, Any]) -> str | None:
    d = r["data"]
    return (d.get("error") or {}).get("code") if isinstance(d, dict) else None


def section_api() -> dict[str, Any]:
    health = _fetch("/health")
    ready = _fetch("/ready")
    networks = _paged("/api/v1/networks")
    scenarios = _paged("/api/v1/scenarios")
    jobs = _paged("/api/v1/simulations")
    artifacts = _paged("/api/v1/artifacts")
    job_checks = []
    for j in jobs:
        res = _fetch(f"/api/v1/simulations/{j['id']}/result")
        met = _fetch(f"/api/v1/simulations/{j['id']}/metrics")
        arts = _fetch(f"/api/v1/simulations/{j['id']}/artifacts")
        job_checks.append(
            {
                "id": j["id"],
                "result_available": j["result_available"],
                "result_http": res["status"],
                "result_error": _error_code(res),
                "result_bytes": res["bytes"] if res["status"] == 200 else None,
                "result_body_sha_matches": res["sha256"] == j["result_sha256"]
                if res["status"] == 200
                else None,
                "metrics_http": met["status"],
                "artifacts_http": arts["status"],
                "artifacts_error": _error_code(arts),
                "artifacts": arts["data"] if arts["status"] == 200 else None,
            }
        )
    comparisons = []
    for cid in KNOWN_COMPARISONS:
        c = _fetch(f"/api/v1/comparisons/{cid}")
        md = _fetch(f"/api/v1/reports/{cid}?format=md")
        d = c["data"] if c["status"] == 200 else {}
        comparisons.append(
            {
                "id": cid,
                "http": c["status"],
                "error": _error_code(c),
                "network_id": d.get("network_id"),
                "baseline_job_id": d.get("baseline_job_id"),
                "scenario_job_id": d.get("scenario_job_id"),
                "report_sha256": d.get("report_sha256"),
                "created_at": d.get("created_at"),
                "report_md_http": md["status"],
                "report_md_bytes": md["bytes"] if md["status"] == 200 else None,
            }
        )
    list_comparisons = _fetch("/api/v1/comparisons")
    timings = {}
    for label, path in [
        ("health", "/health"),
        ("list_jobs_50", "/api/v1/simulations?limit=50"),
        ("get_job", f"/api/v1/simulations/{jobs[0]['id']}" if jobs else None),
        ("job_metrics", f"/api/v1/simulations/{jobs[0]['id']}/metrics" if jobs else None),
        ("list_networks", "/api/v1/networks"),
        ("list_scenarios", "/api/v1/scenarios"),
    ]:
        if path is None:
            continue
        samples = [_fetch(path)["ms"] for _ in range(5)]
        timings[label] = {
            "median_ms": round(statistics.median(samples), 1),
            "samples_ms": [round(s, 1) for s in samples],
        }
    return {
        "health": health["data"],
        "first_request_ms": round(health["ms"], 1),
        "ready": ready["data"],
        "ready_ms": round(ready["ms"], 1),
        "networks": networks,
        "scenarios": [
            {k: s.get(k) for k in ("id", "network_id", "preset", "listed", "visibility", "hash")}
            for s in scenarios
        ],
        "jobs": jobs,
        "job_checks": job_checks,
        "artifacts": artifacts,
        "comparisons": comparisons,
        "list_comparisons_http": list_comparisons["status"],
        "timings": timings,
    }


# ----------------------------------------------------------------------------------------- db
def _placeholder(value: str) -> bool:
    return not value or value.upper().startswith("YOUR_") or "<" in value


def _connect():  # type: ignore[no-untyped-def]
    """Connect from ``DATABASE_URL`` or ``SUPABASE_DB_*``; returns (connection, project ref)."""
    import psycopg
    from psycopg.conninfo import conninfo_to_dict

    common = {
        "connect_timeout": 20,
        "prepare_threshold": None,  # pgbouncer (Supabase pooler) safe
        "application_name": "gridstorm-inventory-readonly",
    }
    url = os.environ.get("DATABASE_URL", "")
    if url and not _placeholder(url):
        url = url.replace("postgresql+psycopg://", "postgresql://", 1)
        user = str(conninfo_to_dict(url).get("user") or "")
        conn = psycopg.connect(url, **common)
    else:
        keys = ("HOST", "PORT", "NAME", "USER", "PASSWORD")
        env = {k: os.environ.get(f"SUPABASE_DB_{k}", "") for k in keys}
        if any(_placeholder(v) for v in env.values()):
            raise SystemExit(
                "BLOCKED: neither DATABASE_URL nor SUPABASE_DB_HOST/PORT/NAME/USER/PASSWORD "
                "holds real credentials"
            )
        user = env["USER"]
        conn = psycopg.connect(
            host=env["HOST"],
            port=env["PORT"],
            dbname=env["NAME"],
            user=user,
            password=env["PASSWORD"],
            sslmode="require",
            **common,
        )
    # autocommit so that _ro() owns the transaction: BEGIN READ ONLY … ROLLBACK, asserted.
    conn.autocommit = True
    ref = user.split(".", 1)[1] if "." in user else "unknown (direct connection; ref not in user)"
    return conn, ref


def _md_cell(v: Any) -> str:
    s = json.dumps(v, default=str) if isinstance(v, dict | list) else str(v)
    return s.replace("|", "\\|").replace("\n", " ")[:200]


def render_markdown(report: dict[str, Any]) -> str:
    """Generic Markdown dump of every section (lists of rows → tables)."""
    out = [f"# GridStorm production inventory — raw output ({report['measured_at']})", ""]
    for section, body in report.items():
        if not isinstance(body, dict):
            continue
        out += [f"## {section}", ""]
        for key, val in body.items():
            out += [f"### {key}", ""]
            if isinstance(val, list) and val and all(isinstance(r, dict) for r in val):
                cols = list(dict.fromkeys(c for r in val for c in r))
                out.append("| " + " | ".join(cols) + " |")
                out.append("|" + "---|" * len(cols))
                out += ["| " + " | ".join(_md_cell(r.get(c)) for c in cols) + " |" for r in val]
            elif isinstance(val, dict) and all(not isinstance(x, list) for x in val.values()):
                out += ["| key | value |", "|---|---|"]
                out += [f"| {k} | {_md_cell(x)} |" for k, x in val.items()]
            else:
                out.append(
                    f"`{_md_cell(val)}`"
                    if not isinstance(val, list | dict)
                    else "```json\n" + json.dumps(val, indent=1, default=str)[:20000] + "\n```"
                )
            out.append("")
    return "\n".join(out)


def _rows(conn, sql: str, params: Any = None) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    cur = conn.execute(sql, params)
    if cur.description is None:
        return []
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def _jsonable(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, list | tuple):
        return [_jsonable(x) for x in v]
    if isinstance(v, int | float | str | bool) or v is None:
        return v
    return str(v)


def _ro(conn, fn):  # type: ignore[no-untyped-def]
    """Run ``fn(conn)`` in a READ ONLY transaction that is always rolled back."""
    conn.execute("begin read only")
    try:
        assert conn.execute("select current_setting('transaction_read_only')").fetchone()[0] == "on"
        return fn(conn)
    finally:
        conn.execute("rollback")


Q_TABLES = """
select c.relname as table, c.relrowsecurity as rls, c.relforcerowsecurity as rls_forced,
       c.reltuples::bigint as est_rows, pg_total_relation_size(c.oid) as total_bytes,
       pg_relation_size(c.oid) as heap_bytes, pg_indexes_size(c.oid) as index_bytes
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind in ('r', 'p') order by c.relname
"""

EXPLAINS: dict[str, str] = {
    # routers/simulations.py list_simulations (anonymous: visibility = 'public')
    "list_jobs_count": "select count(*) from public.simulation_jobs where visibility = 'public'",
    "list_jobs_page": (
        "select * from public.simulation_jobs where visibility = 'public' "
        "order by created_at desc, id limit 50 offset 0"
    ),
    "list_jobs_by_network": (
        "select * from public.simulation_jobs where visibility = 'public' and network_id = %(net)s "
        "order by created_at desc, id limit 50"
    ),
    "list_jobs_mine_anon": (
        "select * from public.simulation_jobs where visibility = 'public' and owner_id is null "
        "order by created_at desc, id limit 50"
    ),
    "get_job": "select * from public.simulation_jobs where id = %(job)s",
    "job_metrics": "select * from public.simulation_metrics where job_id = %(job)s",
    "job_artifacts": (
        "select * from public.simulation_artifacts where job_id = %(job)s order by kind"
    ),
    "result_available_batch": (
        "select job_id, storage_key from public.simulation_artifacts "
        "where job_id = any(%(jobs)s) and kind = 'result'"
    ),
    # jobs/service.py reuse candidate lookup
    "reuse_candidates": (
        "select * from public.simulation_jobs where scenario_hash = %(hash)s and network_id = %(net)s "
        "and status = 'completed' and execution_mode = 'live' and outcome in ('feasible','infeasible') "
        "and result_sha256 is not null and visibility = 'public' and network_version_id = %(ver)s "
        "order by finished_at desc limit 5"
    ),
    # jobs/worker.py claim (FOR UPDATE SKIP LOCKED omitted: not allowed in a read-only txn)
    "worker_claim_candidate": (
        "select id from public.simulation_jobs where status = 'queued' order by created_at limit 1"
    ),
    "active_job_count": (
        "select count(*) from public.simulation_jobs where status in ('queued','running')"
    ),
    # routers/comparisons.py existing-report lookup
    "comparison_existing": (
        "select * from public.comparison_reports where baseline_job_id = %(job)s "
        "and scenario_job_id = %(job2)s and visibility = 'public' and owner_id is null "
        "order by created_at desc"
    ),
    "comparison_get": "select * from public.comparison_reports where id = %(cmp)s",
    # routers/scenarios.py list (anonymous)
    "list_scenarios": (
        "select * from public.scenario_definitions where is_preset order by is_preset desc, "
        "created_at desc, id limit 50"
    ),
}


def _audit(conn, ref: str) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    out: dict[str, Any] = {"project_ref": ref}
    one = lambda sql, p=None: _rows(conn, sql, p)  # noqa: E731
    out["server"] = one(
        "select current_database() as db, current_user as role, version() as version, "
        "current_setting('server_version') as server_version, now() as measured_at, "
        "current_setting('transaction_read_only') as read_only"
    )[0]
    out["schemas"] = one(
        "select n.nspname as schema, count(c.oid) as relations, "
        "coalesce(sum(pg_total_relation_size(c.oid)) filter (where c.relkind in ('r','m','p')), 0) as bytes "
        "from pg_namespace n left join pg_class c on c.relnamespace = n.oid "
        "where n.nspname not like 'pg_toast%%' and n.nspname not like 'pg_temp%%' "
        "group by 1 order by 3 desc"
    )
    out["database_bytes"] = one("select pg_database_size(current_database()) as b")[0]["b"]
    out["migrations"] = one(
        "select version, sha256, applied_at from public.schema_migrations order by 1"
    )
    tables = one(Q_TABLES)
    for t in tables:
        t["rows"] = one(f'select count(*) as n from public."{t["table"]}"')[0]["n"]
    out["tables"] = tables
    out["auth_users"] = one("select count(*) as n from auth.users")[0]["n"]

    out["network_datasets"] = one(
        "select id, name, coordinate_kind, provenance_class, license_spdx, redistribution, "
        "is_public, created_at, updated_at from public.network_datasets order by id"
    )
    out["network_versions"] = one(
        "select v.id, v.network_id, v.network_sha256, v.canonical_sha256, v.manifest_sha256, "
        "v.retrieved_at, v.created_at, s.url, s.version as source_version, s.publication_date, "
        "s.upstream_commit, s.license_spdx, s.redistribution, "
        "(select count(*) from public.simulation_jobs j where j.network_version_id = v.id) as jobs "
        "from public.network_versions v left join public.dataset_sources s on s.network_version_id = v.id "
        "order by v.network_id, v.created_at"
    )
    out["ingestion_runs"] = one(
        "select network_id, tool, status, started_at, finished_at, details from public.ingestion_runs "
        "order by started_at"
    )
    out["scenarios"] = one(
        "select network_id, is_preset, visibility, (owner_id is not null) as owned, count(*) as n "
        "from public.scenario_definitions group by 1,2,3,4 order by 1,2 desc"
    )
    out["preset_ids"] = one(
        "select id, network_id, scenario_hash, created_at, updated_at from public.scenario_definitions "
        "where is_preset order by id"
    )
    out["jobs_by"] = one(
        "select status, outcome, execution_mode, network_id, visibility, (owner_id is not null) as owned, "
        "reused, solver->>'name' as solver, count(*) as n, min(created_at) as first, max(created_at) as last "
        "from public.simulation_jobs group by 1,2,3,4,5,6,7,8 order by 1,4,3"
    )
    out["jobs_stage_status"] = one(
        "select status, stage, count(*) as n from public.simulation_jobs group by 1,2 order by 1,2"
    )
    out["jobs_not_completed"] = one(
        "select id, status, stage, network_id, execution_mode, error->>'code' as error_code, "
        "left(error->>'message', 160) as error_message, attempts, created_at "
        "from public.simulation_jobs where status <> 'completed' order by created_at"
    )
    out["jobs_wall"] = one(
        "select network_id, execution_mode, count(*) as n, "
        "percentile_cont(0.5) within group (order by extract(epoch from finished_at - started_at)) as median_run_s, "
        "percentile_cont(0.5) within group (order by (solver->>'wall_time_s')::float) as median_solver_s "
        "from public.simulation_jobs where status = 'completed' and finished_at is not null "
        "group by 1,2 order by 1,2"
    )
    out["metrics"] = one(
        "select m.network_id, count(*) as n, "
        "count(*) filter (where m.total_system_cost_eur is null) as null_cost, "
        "count(*) filter (where m.unserved_energy_mwh is null) as null_unserved, "
        "count(*) filter (where m.co2_emissions_t is null) as null_co2, "
        "count(*) filter (where m.max_line_loading_pct is null) as null_loading, "
        "count(*) filter (where m.curtailment_mwh is null) as null_curtailment, "
        "count(*) filter (where m.balance_residual_max_mw is null) as null_residual "
        "from public.simulation_metrics m group by 1 order by 1"
    )
    out["metrics_integrity"] = one(
        "select "
        "(select count(*) from public.simulation_jobs j where j.status='completed' and not exists "
        " (select 1 from public.simulation_metrics m where m.job_id=j.id)) as completed_without_metrics, "
        "(select count(*) from public.simulation_metrics m join public.simulation_jobs j on j.id=m.job_id "
        " where j.status<>'completed') as metrics_on_non_completed, "
        "(select count(*) from public.simulation_metrics m join public.simulation_jobs j on j.id=m.job_id "
        " where m.scenario_hash<>j.scenario_hash or m.network_id<>j.network_id) as metrics_job_mismatch"
    )[0]
    out["artifacts_by"] = one(
        "select kind, storage_backend, content_type, count(*) as n, count(distinct storage_key) as keys, "
        "sum(bytes) as bytes from public.simulation_artifacts group by 1,2,3 order by 1,2"
    )
    out["artifact_integrity"] = one(
        "select "
        "(select count(*) from public.simulation_jobs j where j.status='completed' and j.result_sha256 is not null "
        " and not exists (select 1 from public.simulation_artifacts a where a.job_id=j.id and a.kind='result')) "
        " as completed_without_result_row, "
        "(select count(*) from public.simulation_artifacts a join public.simulation_jobs j on j.id=a.job_id "
        " where a.kind='result' and a.sha256 <> j.result_sha256) as result_sha_mismatch, "
        "(select count(*) from public.simulation_artifacts a where a.storage_key <> "
        " 'sha256/' || a.sha256 || '.' || split_part(a.storage_key, '.', 2)) as key_not_content_addressed, "
        "(select count(*) from public.simulation_jobs where status='completed' and result_sha256 is null) "
        " as completed_without_sha"
    )[0]

    # storage schema ------------------------------------------------------------------------
    out["buckets"] = one(
        "select id, public, file_size_limit, allowed_mime_types, created_at from storage.buckets order by id"
    )
    out["objects_by"] = one(
        "select bucket_id, split_part(name, '/', 1) as prefix, metadata->>'mimetype' as mimetype, "
        "count(*) as n, sum((metadata->>'size')::bigint) as bytes, min(created_at) as first, "
        "max(created_at) as last from storage.objects group by 1,2,3 order by 1,2,3"
    )
    out["object_metadata_keys"] = one(
        "select k, count(*) as n from storage.objects, jsonb_object_keys(coalesce(metadata,'{}'::jsonb)) k "
        "group by 1 order by 1"
    )
    out["object_user_metadata_keys"] = one(
        "select k, count(*) as n from storage.objects, "
        "jsonb_object_keys(coalesce(user_metadata,'{}'::jsonb)) k group by 1 order by 1"
    )
    refs = (
        "with refs as (select a.job_id, a.kind, a.storage_backend, a.storage_key, a.sha256, a.bytes, "
        " j.status, j.network_id, j.execution_mode, j.created_at as job_created "
        " from public.simulation_artifacts a join public.simulation_jobs j on j.id = a.job_id), "
        "objs as (select name, (metadata->>'size')::bigint as size, metadata->>'mimetype' as mimetype, "
        " metadata->>'eTag' as etag from storage.objects where bucket_id = %(b)s) "
    )
    out["refs_missing_object"] = one(
        refs + "select r.* from refs r left join objs o on o.name = r.storage_key "
        "where o.name is null order by r.job_created, r.kind",
        {"b": BUCKET},
    )
    out["refs_size_mismatch"] = one(
        refs + "select r.job_id, r.kind, r.storage_key, r.bytes, o.size from refs r "
        "join objs o on o.name = r.storage_key where o.size <> r.bytes",
        {"b": BUCKET},
    )
    out["orphan_objects"] = one(
        refs + "select o.name, o.size, o.mimetype from objs o "
        "where not exists (select 1 from refs r where r.storage_key = o.name) order by o.name",
        {"b": BUCKET},
    )
    out["shared_objects"] = one(
        "select storage_key, kind, count(*) as refs from public.simulation_artifacts "
        "group by 1,2 having count(*) > 1 order by 3 desc"
    )
    out["comparisons"] = one(
        "select c.id, c.network_id, c.visibility, (c.owner_id is not null) as owned, c.report_sha256, "
        "c.report->'reproducibility'->>'git_sha' as git_sha, c.report->>'schema_version' as schema_version, "
        "c.baseline_job_id, c.scenario_job_id, c.created_at, "
        "pg_column_size(c.report) as report_bytes, "
        "bool_and(coalesce(ab.n, 0) > 0) as baseline_result_row, bool_and(coalesce(asc_.n, 0) > 0) as scenario_result_row "
        "from public.comparison_reports c "
        "left join lateral (select count(*) n from public.simulation_artifacts a where a.job_id=c.baseline_job_id and a.kind='result') ab on true "
        "left join lateral (select count(*) n from public.simulation_artifacts a where a.job_id=c.scenario_job_id and a.kind='result') asc_ on true "
        "group by c.id order by c.created_at"
    )
    out["audit_events"] = one(
        "select action, target_type, count(*) as n, min(created_at) as first, max(created_at) as last "
        "from public.audit_events group by 1,2 order by 1,2"
    )
    out["profiles"] = one("select count(*) as n from public.profiles")[0]["n"]

    # RLS / privileges ----------------------------------------------------------------------
    out["policies"] = one(
        "select schemaname, tablename, policyname, cmd, roles, permissive, qual, with_check "
        "from pg_policies where schemaname in ('public','storage') order by 1,2,3"
    )
    out["grants"] = one(
        "select grantee, table_schema, table_name, string_agg(privilege_type, ',' order by privilege_type) as privs "
        "from information_schema.role_table_grants where grantee in ('anon','authenticated') "
        "and table_schema in ('public','storage') group by 1,2,3 order by 2,3,1"
    )
    out["storage_rls"] = one(
        "select c.relname as table, c.relrowsecurity as rls from pg_class c join pg_namespace n "
        "on n.oid=c.relnamespace where n.nspname='storage' and c.relkind='r' order by 1"
    )
    out["functions_executable_by_anon"] = one(
        "select p.proname, p.prosecdef as security_definer from pg_proc p join pg_namespace n on n.oid=p.pronamespace "
        "where n.nspname='public' and has_function_privilege('anon', p.oid, 'execute') order by 1"
    )
    out["anon_select_probe"] = {}
    for t in [r["table"] for r in tables] + ["storage.objects", "storage.buckets"]:
        name = t if "." in t else f'public."{t}"'
        conn.execute("savepoint p")
        try:
            conn.execute("set local role anon")
            n = conn.execute(f"select count(*) from {name}").fetchone()[0]
            out["anon_select_probe"][t] = n
        except Exception as exc:  # noqa: BLE001 — record the denial, keep auditing
            out["anon_select_probe"][t] = (
                f"denied: {type(exc).__name__}: {str(exc).splitlines()[0][:120]}"
            )
        finally:
            conn.execute("rollback to savepoint p")
            conn.execute("reset role")

    # index usage / query plans -------------------------------------------------------------
    out["stats_reset"] = one(
        "select stats_reset from pg_stat_database where datname = current_database()"
    )[0]["stats_reset"]
    out["table_stats"] = one(
        "select relname as table, seq_scan, seq_tup_read, idx_scan, idx_tup_fetch, n_live_tup, n_dead_tup, "
        "last_autovacuum, last_autoanalyze, last_analyze from pg_stat_user_tables "
        "where schemaname='public' order by relname"
    )
    out["index_stats"] = one(
        "select s.relname as table, s.indexrelname as index, s.idx_scan, s.idx_tup_read, "
        "pg_relation_size(s.indexrelid) as bytes, i.indisunique as unique "
        "from pg_stat_user_indexes s join pg_index i on i.indexrelid = s.indexrelid "
        "where s.schemaname='public' order by s.relname, s.indexrelname"
    )
    try:
        conn.execute("savepoint pss")
        out["pg_stat_statements"] = one(
            "select calls, round(mean_exec_time::numeric, 3) as mean_ms, round(total_exec_time::numeric, 1) as total_ms, "
            "rows, left(regexp_replace(query, '\\s+', ' ', 'g'), 220) as query "
            "from pg_stat_statements where query ilike any(array['%%simulation_jobs%%','%%simulation_metrics%%',"
            "'%%simulation_artifacts%%','%%comparison_reports%%','%%scenario_definitions%%']) "
            "order by total_exec_time desc limit 15"
        )
    except Exception as exc:  # noqa: BLE001
        conn.execute("rollback to savepoint pss")
        out["pg_stat_statements"] = f"unavailable: {type(exc).__name__}"

    sample = one(
        "select j.id as job, j.network_id as net, j.scenario_hash as hash, j.network_version_id as ver "
        "from public.simulation_jobs j join public.simulation_metrics m on m.job_id=j.id "
        "where j.status='completed' and j.network_version_id is not null order by j.created_at desc limit 1"
    )
    cmp_row = one(
        "select id, baseline_job_id, scenario_job_id from public.comparison_reports limit 1"
    )
    params: dict[str, Any] = dict(sample[0]) if sample else {}
    params["jobs"] = [
        r["id"]
        for r in one("select id from public.simulation_jobs order by created_at desc limit 50")
    ]
    if cmp_row:
        params["cmp"] = cmp_row[0]["id"]
        params["job"], params["job2"] = cmp_row[0]["baseline_job_id"], cmp_row[0]["scenario_job_id"]
        params.setdefault("net", None)
    rtt = []
    for _ in range(10):
        t0 = time.perf_counter()
        conn.execute("select 1").fetchone()
        rtt.append((time.perf_counter() - t0) * 1000)
    out["select1_rtt_ms"] = {
        "median": round(statistics.median(rtt), 2),
        "min": round(min(rtt), 2),
        "max": round(max(rtt), 2),
    }
    plans = {}
    for name, sql in EXPLAINS.items():
        missing = [k for k in re.findall(r"%\((\w+)\)s", sql) if params.get(k) is None]
        if missing:
            plans[name] = f"skipped: no sample row for {', '.join(missing)}"
            continue
        plan = conn.execute("explain (analyze, buffers, format json) " + sql, params).fetchone()[0][
            0
        ]
        wall = []
        for _ in range(5):
            t0 = time.perf_counter()
            conn.execute(sql, params).fetchall()
            wall.append((time.perf_counter() - t0) * 1000)

        def nodes(p: dict[str, Any]) -> list[str]:
            label = p["Node Type"] + (f" on {p['Relation Name']}" if "Relation Name" in p else "")
            label += f" using {p['Index Name']}" if "Index Name" in p else ""
            return [label] + [x for c in p.get("Plans", []) for x in nodes(c)]

        plans[name] = {
            "nodes": nodes(plan["Plan"]),
            "server_exec_ms": plan["Execution Time"],
            "planning_ms": plan["Planning Time"],
            "client_wall_median_ms": round(statistics.median(wall), 2),
            "rows": plan["Plan"].get("Actual Rows"),
        }
    out["plans"] = plans
    return out


def section_db() -> dict[str, Any]:
    conn, ref = _connect()
    try:
        return _ro(conn, lambda c: _audit(c, ref))
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sections", default="repo,api,db")
    ap.add_argument("--out", type=Path, default=ROOT / "var/inventory/production-inventory.json")
    args = ap.parse_args(argv)
    report: dict[str, Any] = {"measured_at": datetime.now(UTC).isoformat(timespec="seconds")}
    for name in args.sections.split(","):
        fn = {"repo": section_repo, "api": section_api, "db": section_db}[name]
        t0 = time.perf_counter()
        try:
            report[name] = fn()
        except SystemExit as exc:
            report[name] = {"error": str(exc)}
        report[name + "_elapsed_s"] = round(time.perf_counter() - t0, 1)
        print(f"{name}: done in {report[name + '_elapsed_s']} s", file=sys.stderr)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    data = _jsonable(report)
    args.out.write_text(json.dumps(data, indent=1, default=str), encoding="utf-8")
    args.out.with_suffix(".md").write_text(render_markdown(data), encoding="utf-8")
    print(f"wrote {args.out} and {args.out.with_suffix('.md')}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
