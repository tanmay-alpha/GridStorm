"""Runtime configuration, read once from environment variables.

Every variable is documented in ``services/api/.env.example`` and ``docs/deployment/backend.md``.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

# services/api/src/gridstorm_api/config.py -> parents[4] == repository root (source checkout).
REPO_ROOT = Path(__file__).resolve().parents[4]

DEFAULT_ENGINE_CMD = (
    "{python} -m gridstorm_pypsa run --scenario {scenario} --network-dir {network_dir} --out {out}"
)

DEFAULT_LIVE_NETWORKS = "ac-dc-meshed,pglib-case14-ieee,pglib-case118-ieee,pypsa-eur-be"


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"environment variable {name} must be an integer, got {raw!r}") from exc


def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"environment variable {name} must be a number, got {raw!r}") from exc


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    lowered = raw.lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"environment variable {name} must be a boolean, got {raw!r}")


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: REPO_ROOT / "data")
    state_dir: Path = field(default_factory=lambda: REPO_ROOT / "var")
    presets_dir: Path | None = None
    database_url: str | None = None
    db_auto_migrate: bool = False
    migrations_dir: Path = field(default_factory=lambda: REPO_ROOT / "database" / "migrations")
    db_supabase_stub: bool = False

    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:5173"])
    max_body_bytes: int = 256 * 1024
    trust_proxy: bool = False
    rate_limit_post_per_min: float = 60.0
    rate_limit_post_burst: int = 20
    rate_limit_sim_per_min: float = 6.0
    rate_limit_sim_burst: int = 3

    execution_mode: Literal["live", "precomputed"] = "live"
    live_networks: set[str] = field(default_factory=lambda: set(DEFAULT_LIVE_NETWORKS.split(",")))
    run_workers: bool = True
    max_concurrent_jobs: int = 1
    engine_cmd: str = DEFAULT_ENGINE_CMD
    job_timeout_s: float = 600.0
    job_memory_mb: int = 2048
    job_max_attempts: int = 2
    job_heartbeat_s: float = 5.0
    job_stale_after_s: float = 60.0
    job_poll_s: float = 2.0
    max_queued_jobs: int = 50

    artifact_store: Literal["local", "s3", "supabase"] = "local"
    artifact_dir: Path | None = None
    s3_bucket: str | None = None
    s3_endpoint_url: str | None = None
    s3_region: str | None = None
    s3_prefix: str = ""

    supabase_url: str | None = None
    supabase_jwt_secret: str | None = field(default=None, repr=False)
    supabase_jwt_audience: str = "authenticated"
    # Server-only secret for GRIDSTORM_ARTIFACT_STORE=supabase; never sent to clients or engines.
    supabase_service_role_key: str | None = field(default=None, repr=False)
    supabase_bucket: str = "gridstorm-artifacts"
    supabase_storage_timeout_s: float = 30.0

    solver_check_ttl_s: float = 600.0
    storage_check_ttl_s: float = 300.0

    git_sha: str | None = None
    python_executable: str = field(default_factory=lambda: sys.executable)

    @property
    def networks_dir(self) -> Path:
        return self.data_dir / "networks"

    @property
    def artifacts_dir(self) -> Path:
        """Precomputed engine artifacts (contract §5), read-only."""
        return self.data_dir / "artifacts"

    @property
    def resolved_presets_dir(self) -> Path:
        return self.presets_dir or (REPO_ROOT / "packages" / "stormspec" / "presets")

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.state_dir / 'gridstorm.db').as_posix()}"

    @property
    def resolved_artifact_dir(self) -> Path:
        return self.artifact_dir or (self.state_dir / "artifacts")

    def live_execution(self, network_id: str) -> bool:
        return self.execution_mode == "live" and network_id in self.live_networks

    @property
    def auth_enabled(self) -> bool:
        return bool(self.supabase_jwt_secret or self.supabase_url)

    @classmethod
    def from_env(cls) -> Settings:
        data_dir = Path(_env("GRIDSTORM_DATA_DIR", str(REPO_ROOT / "data")))
        state_dir = Path(_env("GRIDSTORM_STATE_DIR", str(REPO_ROOT / "var")))
        presets = _env("GRIDSTORM_PRESETS_DIR")
        migrations = _env("GRIDSTORM_MIGRATIONS_DIR")
        artifact_dir = _env("GRIDSTORM_ARTIFACT_DIR")
        origins = [o.strip() for o in (_env("GRIDSTORM_CORS_ORIGINS", "") or "").split(",")]
        mode = _env("GRIDSTORM_EXECUTION_MODE", "live")
        if mode not in ("live", "precomputed"):
            raise ValueError("GRIDSTORM_EXECUTION_MODE must be 'live' or 'precomputed'")
        store = _env("GRIDSTORM_ARTIFACT_STORE", "local")
        if store not in ("local", "s3", "supabase"):
            raise ValueError("GRIDSTORM_ARTIFACT_STORE must be 'local', 's3' or 'supabase'")
        return cls(
            data_dir=data_dir,
            state_dir=state_dir,
            presets_dir=Path(presets) if presets else None,
            database_url=_env("DATABASE_URL"),
            db_auto_migrate=_env_bool("GRIDSTORM_DB_AUTO_MIGRATE", False),
            migrations_dir=(
                Path(migrations) if migrations else REPO_ROOT / "database" / "migrations"
            ),
            db_supabase_stub=_env_bool("GRIDSTORM_DB_SUPABASE_STUB", False),
            cors_origins=[o for o in origins if o] or ["http://localhost:5173"],
            max_body_bytes=_env_int("GRIDSTORM_MAX_BODY_BYTES", 256 * 1024),
            trust_proxy=_env_bool("GRIDSTORM_TRUST_PROXY", False),
            rate_limit_post_per_min=_env_float("GRIDSTORM_RATE_LIMIT_POST_PER_MIN", 60.0),
            rate_limit_post_burst=_env_int("GRIDSTORM_RATE_LIMIT_POST_BURST", 20),
            rate_limit_sim_per_min=_env_float("GRIDSTORM_RATE_LIMIT_SIM_PER_MIN", 6.0),
            rate_limit_sim_burst=_env_int("GRIDSTORM_RATE_LIMIT_SIM_BURST", 3),
            execution_mode=mode,  # type: ignore[arg-type]
            live_networks={
                n.strip()
                for n in os.environ.get("GRIDSTORM_LIVE_NETWORKS", DEFAULT_LIVE_NETWORKS).split(",")
                if n.strip()
            },
            run_workers=_env_bool("GRIDSTORM_RUN_WORKERS", True),
            max_concurrent_jobs=max(0, _env_int("GRIDSTORM_MAX_CONCURRENT_JOBS", 1)),
            engine_cmd=_env("GRIDSTORM_ENGINE_CMD", DEFAULT_ENGINE_CMD) or DEFAULT_ENGINE_CMD,
            job_timeout_s=_env_float("GRIDSTORM_JOB_TIMEOUT_S", 600.0),
            job_memory_mb=_env_int("GRIDSTORM_JOB_MEMORY_MB", 2048),
            job_max_attempts=max(1, _env_int("GRIDSTORM_JOB_MAX_ATTEMPTS", 2)),
            job_stale_after_s=_env_float("GRIDSTORM_JOB_STALE_AFTER_S", 60.0),
            max_queued_jobs=_env_int("GRIDSTORM_MAX_QUEUED_JOBS", 50),
            artifact_store=store,  # type: ignore[arg-type]
            artifact_dir=Path(artifact_dir) if artifact_dir else None,
            s3_bucket=_env("GRIDSTORM_S3_BUCKET"),
            s3_endpoint_url=_env("GRIDSTORM_S3_ENDPOINT_URL"),
            s3_region=_env("GRIDSTORM_S3_REGION"),
            s3_prefix=_env("GRIDSTORM_S3_PREFIX", "") or "",
            supabase_url=_env("SUPABASE_URL"),
            supabase_jwt_secret=_env("SUPABASE_JWT_SECRET"),
            supabase_jwt_audience=_env("SUPABASE_JWT_AUDIENCE", "authenticated") or "authenticated",
            supabase_service_role_key=_env("SUPABASE_SERVICE_ROLE_KEY"),
            supabase_bucket=_env("GRIDSTORM_SUPABASE_BUCKET", "gridstorm-artifacts")
            or "gridstorm-artifacts",
            supabase_storage_timeout_s=_env_float("GRIDSTORM_SUPABASE_STORAGE_TIMEOUT_S", 30.0),
            storage_check_ttl_s=_env_float("GRIDSTORM_STORAGE_CHECK_TTL_S", 300.0),
            git_sha=_env("GRIDSTORM_GIT_SHA") or _env("RENDER_GIT_COMMIT"),
        )
