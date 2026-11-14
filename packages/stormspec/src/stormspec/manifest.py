"""Execution manifest (``execution-manifest/1.0``) recording how a result was produced."""

from __future__ import annotations

import os
import platform as _platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def python_version() -> str:
    return _platform.python_version()


def platform_string() -> str:
    return f"{_platform.system()}-{_platform.release()}-{_platform.machine()}"


def detect_git_sha(start: str | Path | None = None) -> str | None:
    """Return ``GRIDSTORM_GIT_SHA`` if set, else ``git rev-parse HEAD`` near ``start``, else None."""
    env = os.environ.get("GRIDSTORM_GIT_SHA")
    if env:
        return env.strip() or None
    cwd = Path(start) if start is not None else Path(__file__).resolve().parent
    if cwd.is_file():
        cwd = cwd.parent
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    sha = out.stdout.strip()
    return sha if out.returncode == 0 and len(sha) == 40 else None


class ExecutionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["execution-manifest/1.0"] = "execution-manifest/1.0"
    scenario_hash: str
    dataset_sha256: str | None = Field(description="sha256 of the network file actually loaded.")
    engine_name: str
    engine_version: str
    solver_name: str | None
    solver_version: str | None
    solver_options: dict[str, Any] = Field(default_factory=dict)
    package_versions: dict[str, str] = Field(
        default_factory=dict, description="Versions of relevant libraries (e.g. linopy, highspy)."
    )
    python_version: str = Field(default_factory=python_version)
    platform: str = Field(default_factory=platform_string)
    started_at: str
    finished_at: str
    result_sha256: str | None = Field(
        default=None,
        description="sha256 of canonical JSON of the result object excluding its `manifest` key.",
    )
    git_sha: str | None = None
    command: str | None = Field(default=None, description="Command line when run via a CLI.")
