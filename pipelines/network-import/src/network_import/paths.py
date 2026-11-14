"""Paths, hashing, downloads and the retrieval record shared by all importers."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]


def data_dir() -> Path:
    return Path(os.environ.get("GRIDSTORM_DATA_DIR") or REPO_ROOT / "data")


def networks_dir() -> Path:
    return data_dir() / "networks"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_text(path: Path, text: str) -> bool:
    """Write ``text`` with LF line endings only if content changed. Returns True if written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8")
    if path.exists() and path.read_bytes() == data:
        return False
    path.write_bytes(data)
    return True


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def fetch(url: str, dest: Path, *, record: Path, expected_sha256: str | None = None) -> dict:
    """Download ``url`` to ``dest`` once and keep a retrieval record (url, sha256, time, headers).

    Idempotent: if ``record`` exists, the existing ``dest`` (or a fresh download, when ``dest`` is
    missing) must match the recorded sha256, otherwise the upstream changed and we fail loudly
    instead of silently importing different data. Delete the record to re-baseline.
    """
    rec = json.loads(record.read_text("utf-8")) if record.exists() else None
    if rec is not None:
        if rec["url"] != url:
            raise RuntimeError(f"{record}: recorded url {rec['url']} != requested {url}")
        expected_sha256 = rec["sha256"]
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        req = urllib.request.Request(url, headers={"User-Agent": "gridstorm-network-import/1.0"})
        with urllib.request.urlopen(req, timeout=120) as resp, tmp.open("wb") as f:  # noqa: S310
            headers = {k.lower(): v for k, v in resp.headers.items()}
            shutil.copyfileobj(resp, f)
        tmp.replace(dest)
    else:
        headers = None
    digest = sha256_file(dest)
    if expected_sha256 and digest != expected_sha256:
        raise RuntimeError(
            f"sha256 mismatch for {url}: got {digest}, expected {expected_sha256}. Upstream changed "
            f"or download corrupted; delete {record} to re-baseline deliberately."
        )
    if rec is None:
        rec = {
            "url": url,
            "sha256": digest,
            "bytes": dest.stat().st_size,
            "retrieved_at": _now(),
            "http_last_modified": (headers or {}).get("last-modified"),
            "http_etag": (headers or {}).get("etag"),
        }
        write_text(record, json.dumps(rec, indent=2) + "\n")
    return rec
