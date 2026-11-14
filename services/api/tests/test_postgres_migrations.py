"""Apply database/migrations/*.sql to a real postgres:16 (Docker) and exercise ORM + API on it.

Skipped with an explicit reason when Docker is unavailable. Port: first free one in 8055-8059.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select, text

from conftest import NETWORK_ID, auth, run_job, scenario
from gridstorm_api.config import REPO_ROOT
from gridstorm_api.db.migrate import apply_migrations
from gridstorm_api.db.models import Base, NetworkDataset, Profile, SimulationJob
from gridstorm_api.db.session import Database
from gridstorm_api.main import create_app

pytestmark = pytest.mark.docker

MIGRATIONS = REPO_ROOT / "database" / "migrations"
USER = uuid.UUID("33333333-3333-4333-8333-333333333333")


def _docker_ok() -> str | None:
    if shutil.which("docker") is None:
        return "docker CLI not found"
    try:
        out = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"docker unavailable: {exc}"
    if out.returncode != 0:
        return f"docker daemon unavailable: {out.stderr.strip()[:200]}"
    return None


def _free_port() -> int:
    for port in range(8055, 8060):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    pytest.skip("no free port in 8055-8059 for the postgres test container")


@pytest.fixture(scope="module")
def pg_url():
    reason = _docker_ok()
    if reason:
        pytest.skip(f"postgres migration test needs Docker: {reason}")
    port = _free_port()
    name = f"gridstorm-api-test-pg-{uuid.uuid4().hex[:8]}"
    run = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--rm",
            "--name",
            name,
            "-e",
            "POSTGRES_PASSWORD=test",
            "-e",
            "POSTGRES_DB=gridstorm",
            "-p",
            f"127.0.0.1:{port}:5432",
            "postgres:16",
        ],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if run.returncode != 0:
        pytest.skip(f"could not start postgres:16: {run.stderr.strip()[:300]}")
    url = f"postgresql://postgres:test@127.0.0.1:{port}/gridstorm"
    try:
        deadline = time.monotonic() + 90
        while True:
            try:
                db = Database(url)
                db.ping()
                db.dispose()
                break
            except Exception:
                if time.monotonic() > deadline:
                    raise
                time.sleep(1)
        yield url
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=60, check=False)


@pytest.fixture(scope="module")
def migrated(pg_url):
    db = Database(pg_url)
    applied = apply_migrations(db.engine, MIGRATIONS, supabase_stub=True)
    assert applied == sorted(p.name for p in MIGRATIONS.glob("*.sql"))
    assert apply_migrations(db.engine, MIGRATIONS, supabase_stub=True) == []  # idempotent
    yield db
    db.dispose()


def test_orm_matches_sql_schema(migrated):
    insp = inspect(migrated.engine)
    for table in Base.metadata.sorted_tables:
        cols = {c["name"]: c for c in insp.get_columns(table.name, schema="public")}
        assert set(cols) == {c.name for c in table.columns}, table.name
        for c in table.columns:
            assert cols[c.name]["nullable"] == c.nullable, f"{table.name}.{c.name}"
        pk = insp.get_pk_constraint(table.name, schema="public")["constrained_columns"]
        assert set(pk) == {c.name for c in table.primary_key.columns}, table.name
        fks = {
            (tuple(f["constrained_columns"]), f["referred_table"])
            for f in insp.get_foreign_keys(table.name, schema="public")
            if f["referred_schema"] in (None, "public")
        }
        orm_fks = {((fk.parent.name,), fk.column.table.name) for fk in table.foreign_keys}
        assert fks == orm_fks, table.name
    with migrated.engine.connect() as conn:
        rls = dict(
            conn.execute(
                text(
                    "select relname, relrowsecurity from pg_class c join pg_namespace n "
                    "on n.oid = c.relnamespace where n.nspname = 'public' and relkind = 'r'"
                )
            ).all()
        )
    for table in Base.metadata.sorted_tables:
        assert rls[table.name] is True, f"RLS disabled on {table.name}"


def test_rls_policies_enforce_owner_visibility(migrated):
    other = uuid.uuid4()
    with migrated.engine.begin() as conn:
        conn.execute(text("insert into auth.users (id) values (:a), (:b)"), {"a": USER, "b": other})
        conn.execute(text("insert into profiles (id) values (:a), (:b)"), {"a": USER, "b": other})
        conn.execute(
            text(
                "insert into network_datasets (id, name, coordinate_kind) "
                "values ('rls-net', 'RLS', 'schematic')"
            )
        )
        for sid, owner, vis in (
            ("pub", None, "public"),
            ("mine", USER, "private"),
            ("theirs", other, "private"),
        ):
            conn.execute(
                text(
                    "insert into scenario_definitions "
                    "(id, spec_id, name, network_id, scenario_hash, "
                    "spec, is_preset, visibility, owner_id) values (:id, :id, :id, 'rls-net', 'h', "
                    "'{}'::jsonb, false, :vis, :owner)"
                ),
                {"id": sid, "vis": vis, "owner": owner},
            )
    with migrated.engine.begin() as conn:
        conn.execute(text("set local role authenticated"))
        conn.execute(text(f"set local request.jwt.claim.sub = '{USER}'"))
        seen = {r[0] for r in conn.execute(text("select id from scenario_definitions"))}
        assert seen == {"pub", "mine"}
        assert conn.execute(text("select count(*) from ingestion_runs")).scalar() == 0
    with migrated.engine.begin() as conn:
        conn.execute(text("set local role anon"))
        seen = {r[0] for r in conn.execute(text("select id from scenario_definitions"))}
        assert seen == {"pub"}
        assert {r[0] for r in conn.execute(text("select id from network_datasets"))} >= {"rls-net"}


def test_api_on_postgres(pg_url, migrated, settings_factory):
    with migrated.engine.begin() as conn:
        conn.execute(
            text("insert into auth.users (id) values (:u) on conflict do nothing"),
            {"u": uuid.UUID("11111111-1111-4111-8111-111111111111")},
        )
    settings = settings_factory(database_url=pg_url, db_auto_migrate=True, db_supabase_stub=True)
    with TestClient(create_app(settings)) as client:
        ready = client.get("/ready").json()
        assert ready["checks"]["database"]["kind"] == "postgres"
        presets = client.get("/api/v1/scenarios?preset=true").json()
        assert {s["id"] for s in presets["items"]} == {"preset-base", "preset-stress"}
        job = run_job(client, scenario("pg-run", demand=1.2))  # claim uses FOR UPDATE SKIP LOCKED
        assert job["status"] == "completed", job
        private = run_job(
            client,
            scenario("pg-private"),
            headers=auth(uuid.UUID("11111111-1111-4111-8111-111111111111")),
        )
        assert private["visibility"] == "private"
        assert client.get(f"/api/v1/simulations/{private['id']}").status_code == 404
        r = client.post(
            "/api/v1/comparisons", json={"baseline_job_id": job["id"], "scenario_job_id": job["id"]}
        )
        assert r.status_code == 201
    with migrated.session() as s:
        assert s.get(NetworkDataset, NETWORK_ID) is not None
        assert s.scalar(select(SimulationJob).where(SimulationJob.scenario_id == "pg-run"))
        assert s.get(Profile, uuid.UUID("11111111-1111-4111-8111-111111111111")) is not None
