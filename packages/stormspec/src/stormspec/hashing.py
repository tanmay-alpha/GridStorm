"""Canonical JSON and content hashes.

* ``canonical_json(scenario)``: UTF-8 JSON of the fully-defaulted scenario with sorted keys and
  compact separators, excluding the human-readable ``name`` and ``description``. Two scenarios that
  differ only in wording or in whether defaults were spelled out hash identically.
* ``scenario_hash(scenario)``: sha256 hex digest of ``canonical_json``.
* ``payload_sha256(obj)``: sha256 of canonical JSON of any JSON-compatible object (artifact
  ``payload_sha256`` per contract §5).
* ``result_sha256(result)``: sha256 of a gridstorm-result with its volatile parts removed: the
  ``manifest`` key (it embeds this hash and timestamps) and ``solver.wall_time_s`` (machine
  dependent). Identical scenario + dataset + software therefore gives an identical hash.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .models import Scenario

_HASH_EXCLUDE = {"name", "description"}


def canonical_dumps(obj: Any) -> bytes:
    """Canonical JSON bytes: sorted keys, compact separators, UTF-8, NaN rejected."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _as_scenario(scenario: Scenario | dict) -> Scenario:
    return scenario if isinstance(scenario, Scenario) else Scenario.model_validate(scenario)


def canonical_json(scenario: Scenario | dict) -> bytes:
    data = _as_scenario(scenario).model_dump(mode="json", exclude=_HASH_EXCLUDE)
    return canonical_dumps(data)


def scenario_hash(scenario: Scenario | dict) -> str:
    return hashlib.sha256(canonical_json(scenario)).hexdigest()


def payload_sha256(obj: Any) -> str:
    return hashlib.sha256(canonical_dumps(obj)).hexdigest()


def result_sha256(result: dict) -> str:
    content = {k: v for k, v in result.items() if k != "manifest"}
    solver = content.get("solver")
    if isinstance(solver, dict) and "wall_time_s" in solver:
        content["solver"] = {k: v for k, v in solver.items() if k != "wall_time_s"}
    return payload_sha256(content)


def file_sha256(path: str | Path, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()
