"""ArtifactStore: immutable, content-addressed blobs (``sha256/<hash>.<ext>``).

Backends:

* ``local`` — local filesystem (default; development). NOT durable on hosts with ephemeral disks
  (Render free): every restart/redeploy loses the blobs while the database rows survive.
* ``supabase`` — a private Supabase Storage bucket over its REST API with the service-role key
  (server-side only). Durable; the production backend.
* ``s3`` — S3-compatible object storage via boto3 (AWS S3, Cloudflare R2 with
  ``GRIDSTORM_S3_ENDPOINT_URL``, MinIO, ...). Credentials come from the standard boto3 environment.

Every ``put`` re-reads the stored object and verifies its sha256 before returning. Every ``get``
verifies either its recorded sha256 or the digest in its content address. A ``StoredBlob`` means
the stored bytes were verified. Missing blobs raise ``ArtifactUnavailable`` (HTTP 410),
corrupt blobs ``ArtifactIntegrityError`` (500), storage outages ``ArtifactStoreUnavailable`` (503).
Error messages never contain credentials, URLs or filesystem paths.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import tempfile
import threading
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import APIError

log = logging.getLogger("gridstorm_api.storage")


class ArtifactIntegrityError(APIError):
    status_code = 500
    code = "artifact_integrity_error"


class ArtifactUnavailable(APIError):
    """The blob is gone from the store (e.g. lost with an ephemeral disk)."""

    status_code = 410
    code = "artifact_unavailable"


class ArtifactStoreUnavailable(APIError):
    """The store could not be reached or rejected the request (transient or misconfigured)."""

    status_code = 503
    code = "artifact_store_unavailable"

    def __init__(self, message: str, **kw: Any) -> None:
        kw.setdefault("headers", {"Retry-After": "30"})
        super().__init__(message, **kw)


@dataclass(frozen=True)
class StoredBlob:
    backend: str
    key: str
    sha256: str
    bytes: int
    content_type: str


def content_key(sha256: str, ext: str) -> str:
    return f"sha256/{sha256}.{ext}"


# Existence cache: blobs are immutable, so a positive answer stays true for a long time; a negative
# one is re-checked soon (a recompute may re-create the same content address).
_POSITIVE_TTL_S = 600.0
_NEGATIVE_TTL_S = 30.0
_CACHE_MAX = 4096


class ArtifactStore(ABC):
    backend: str
    durable: bool = False

    def __init__(self) -> None:
        self._exists_cache: dict[str, tuple[float, bool]] = {}
        self._cache_lock = threading.Lock()

    # -- public API --------------------------------------------------------------------------
    def put(
        self, data: bytes, *, ext: str = "json", content_type: str = "application/json"
    ) -> StoredBlob:
        """Store ``data`` under its content address; returns only once the stored bytes verify."""
        digest = hashlib.sha256(data).hexdigest()
        key = content_key(digest, ext)
        if not self._exists(key):
            self._write(key, data, content_type)
        self.get(key, expected_sha256=digest)
        return StoredBlob(self.backend, key, digest, len(data), content_type)

    def get(self, key: str, *, expected_sha256: str | None = None) -> bytes:
        try:
            data = self._read(key)
        except ArtifactUnavailable:
            self._remember(key, False)
            raise
        self._remember(key, True)
        expected_sha256 = expected_sha256 or key.rsplit("/", 1)[-1].split(".", 1)[0]
        if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
            raise ValueError("a sha256 is required to read an artifact")
        actual = hashlib.sha256(data).hexdigest()
        if actual != expected_sha256:
            raise ArtifactIntegrityError(
                "stored artifact does not match its recorded sha256",
                details={"expected_sha256": expected_sha256, "actual_sha256": actual},
            )
        return data

    def exists(self, key: str, *, fresh: bool = False) -> bool:
        """Cheap presence check (no integrity verification), cached unless ``fresh``."""
        if not fresh:
            cached = self._cached(key)
            if cached is not None:
                return cached
        present = self._exists(key)
        self._remember(key, present)
        return present

    def exists_many(self, keys: Iterable[str]) -> dict[str, bool]:
        """Presence of several keys; uncached keys are checked concurrently. A key whose check
        fails (store unreachable) is reported absent and not cached."""
        out: dict[str, bool] = {}
        todo: list[str] = []
        for key in dict.fromkeys(keys):
            cached = self._cached(key)
            if cached is None:
                todo.append(key)
            else:
                out[key] = cached
        if len(todo) == 1:
            out[todo[0]] = self._safe_exists(todo[0])
        elif todo:
            with ThreadPoolExecutor(max_workers=min(8, len(todo))) as pool:
                out.update(zip(todo, pool.map(self._safe_exists, todo), strict=True))
        return out

    @abstractmethod
    def check_writable(self) -> str:
        """Raise on failure; return a short human-readable detail on success."""

    def close(self) -> None:  # noqa: B027 - optional hook; most backends hold no resources
        """Release backend resources, if any."""

    # -- backend primitives ------------------------------------------------------------------
    @abstractmethod
    def _exists(self, key: str) -> bool: ...

    @abstractmethod
    def _write(self, key: str, data: bytes, content_type: str) -> None:
        """Create an immutable object; leave an already existing object unchanged."""

    @abstractmethod
    def _read(self, key: str) -> bytes:
        """Return the object's bytes; raise ``ArtifactUnavailable`` if it does not exist."""

    # -- existence cache ---------------------------------------------------------------------
    def _safe_exists(self, key: str) -> bool:
        try:
            return self.exists(key, fresh=True)
        except Exception as exc:
            log.warning("artifact existence check failed: %s", type(exc).__name__)
            return False

    def _cached(self, key: str) -> bool | None:
        with self._cache_lock:
            hit = self._exists_cache.get(key)
        if hit is None or time.monotonic() >= hit[0]:
            return None
        return hit[1]

    def _remember(self, key: str, present: bool) -> None:
        ttl = _POSITIVE_TTL_S if present else _NEGATIVE_TTL_S
        with self._cache_lock:
            if len(self._exists_cache) >= _CACHE_MAX:
                self._exists_cache.clear()
            self._exists_cache[key] = (time.monotonic() + ttl, present)


def _missing(key: str) -> ArtifactUnavailable:
    del key  # never echo storage keys or paths to clients
    return ArtifactUnavailable("stored artifact is missing")


class LocalArtifactStore(ArtifactStore):
    backend = "local"
    durable = False

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = root

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError(f"artifact key escapes store root: {key!r}")
        return path

    def _exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def _write(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Publish the complete file atomically without replacing an existing content address.
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            try:
                os.link(tmp, path)
            except FileExistsError:
                pass  # put() verifies the winner's bytes
        finally:
            Path(tmp).unlink(missing_ok=True)

    def _read(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError as exc:
            raise _missing(key) from exc

    def check_writable(self) -> str:
        self.root.mkdir(parents=True, exist_ok=True)
        probe = self.root / f".ready-{uuid.uuid4().hex}"
        probe.write_bytes(b"ok")
        probe.unlink()
        return (
            "local: filesystem store, NOT durable on hosts with ephemeral disks (e.g. Render): "
            "stored results are lost on every restart/redeploy"
        )


class S3ArtifactStore(ArtifactStore):
    backend = "s3"
    durable = True

    def __init__(
        self,
        bucket: str,
        *,
        endpoint_url: str | None = None,
        region: str | None = None,
        prefix: str = "",
        client: Any = None,
    ) -> None:
        super().__init__()
        if client is None:
            import boto3

            client = boto3.client("s3", endpoint_url=endpoint_url, region_name=region)
        self.client = client
        self.bucket = bucket
        self.prefix = prefix.strip("/")

    def _k(self, key: str) -> str:
        return f"{self.prefix}/{key}" if self.prefix else key

    @staticmethod
    def _is_not_found(exc: Any) -> bool:
        return exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound")

    def _exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=self.bucket, Key=self._k(key))
            return True
        except ClientError as exc:
            if self._is_not_found(exc):
                return False
            raise

    def _write(self, key: str, data: bytes, content_type: str) -> None:
        from botocore.exceptions import ClientError

        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=self._k(key),
                Body=data,
                ContentType=content_type,
                IfNoneMatch="*",
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") not in ("PreconditionFailed", "412"):
                raise

    def _read(self, key: str) -> bytes:
        from botocore.exceptions import ClientError

        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=self._k(key))
        except ClientError as exc:
            if self._is_not_found(exc):
                raise _missing(key) from exc
            raise
        return obj["Body"].read()

    def check_writable(self) -> str:
        probe = self._k(f"_ready/{uuid.uuid4().hex}")
        self.client.put_object(Bucket=self.bucket, Key=probe, Body=b"ok")
        try:
            if self.client.get_object(Bucket=self.bucket, Key=probe)["Body"].read() != b"ok":
                raise ArtifactIntegrityError("readiness probe read back different bytes")
        finally:
            self.client.delete_object(Bucket=self.bucket, Key=probe)
        return f"s3:{self.bucket}"


_SAFE_KEY = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._/-]*$")


class SupabaseArtifactStore(ArtifactStore):
    """Private Supabase Storage bucket via the Storage REST API (service-role key, server-side).

    Endpoints: ``POST /storage/v1/object/{bucket}/{key}`` (``x-upsert: false``; an existing key
    answers ``Duplicate``/``KeyAlreadyExists``), ``GET`` for reads, ``GET .../object/info/...`` for
    existence (unlike HEAD it returns a JSON error body, so a missing object ``NoSuchKey`` can be
    told apart from a wrong key/bucket ``NoSuchBucket``), ``DELETE`` for the readiness probe and
    tests. Transport errors and 408/429/5xx are retried with exponential backoff.
    """

    backend = "supabase"
    durable = True
    _RETRY_STATUS = frozenset({408, 429, *range(500, 600)})

    def __init__(
        self,
        url: str,
        service_role_key: str,
        bucket: str,
        *,
        prefix: str = "",
        timeout_s: float = 30.0,
        max_attempts: int = 3,
        backoff_s: float = 0.5,
        transport: Any = None,
    ) -> None:
        import httpx

        super().__init__()
        # httpx's INFO request logging includes private object keys in URLs.
        logging.getLogger("httpx").setLevel(logging.WARNING)
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.max_attempts = max(1, max_attempts)
        self.backoff_s = backoff_s
        self._base = f"{url.rstrip('/')}/storage/v1/object"
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout_s, connect=min(timeout_s, 10.0)),
            headers={"Authorization": f"Bearer {service_role_key}", "apikey": service_role_key},
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    # -- helpers -----------------------------------------------------------------------------
    def _object(self, key: str) -> str:
        if not _SAFE_KEY.match(key) or ".." in key.split("/"):
            raise ValueError(f"invalid artifact key: {key!r}")
        return f"{self.prefix}/{key}" if self.prefix else key

    def _request(self, method: str, path: str, **kw: Any) -> Any:
        import httpx

        what = ""
        for attempt in range(1, self.max_attempts + 1):
            try:
                resp = self._client.request(method, f"{self._base}/{path}", **kw)
            except httpx.TransportError as exc:
                what = type(exc).__name__
            else:
                if resp.status_code not in self._RETRY_STATUS:
                    return resp
                what = f"HTTP {resp.status_code}"
            if attempt < self.max_attempts:
                time.sleep(self.backoff_s * 2 ** (attempt - 1))
        raise ArtifactStoreUnavailable(
            f"artifact storage is unreachable ({what} after {self.max_attempts} attempts)"
        )

    @staticmethod
    def _error(resp: Any) -> tuple[str, str]:
        """``(statusCode, code)`` from a Storage API JSON error body (both may be '')."""
        try:
            body = resp.json()
        except ValueError:
            return str(resp.status_code), ""
        if not isinstance(body, dict):
            return str(resp.status_code), ""
        return str(body.get("statusCode") or resp.status_code), str(
            body.get("code") or body.get("error") or ""
        )

    def _is_missing(self, resp: Any) -> bool:
        if resp.status_code not in (400, 404):
            return False
        status, code = self._error(resp)
        return status == "404" and code in ("NoSuchKey", "not_found")

    def _is_duplicate(self, resp: Any) -> bool:
        if resp.status_code == 409:
            return True
        if resp.status_code != 400:
            return False
        status, code = self._error(resp)
        return status == "409" or code in ("Duplicate", "KeyAlreadyExists")

    def _fail(self, resp: Any, action: str) -> ArtifactStoreUnavailable:
        status, code = self._error(resp)
        detail = f"HTTP {resp.status_code}" + (f" {code}" if code else "")
        return ArtifactStoreUnavailable(f"artifact storage rejected the {action} ({detail})")

    # -- primitives --------------------------------------------------------------------------
    def _exists(self, key: str) -> bool:
        resp = self._request("GET", f"info/{self.bucket}/{self._object(key)}")
        if resp.status_code == 200:
            return True
        if self._is_missing(resp):
            return False
        raise self._fail(resp, "existence check")

    def _write(self, key: str, data: bytes, content_type: str) -> None:
        resp = self._request(
            "POST",
            f"{self.bucket}/{self._object(key)}",
            content=data,
            headers={"Content-Type": content_type, "x-upsert": "false"},
        )
        if resp.status_code in (200, 201) or self._is_duplicate(resp):
            return  # duplicate: same content address, verified by put()
        raise self._fail(resp, "upload")

    def _read(self, key: str) -> bytes:
        resp = self._request("GET", f"{self.bucket}/{self._object(key)}")
        if resp.status_code == 200:
            return resp.content
        if self._is_missing(resp):
            raise _missing(key)
        raise self._fail(resp, "download")

    def delete(self, key: str) -> None:
        """Remove an object (readiness probe and tests only; artifacts are never deleted)."""
        resp = self._request("DELETE", f"{self.bucket}/{self._object(key)}")
        if resp.status_code != 200 and not self._is_missing(resp):
            raise self._fail(resp, "delete")
        self._remember(key, False)

    def check_writable(self) -> str:
        """Round trip: write, read back and delete a tiny probe object under ``_ready/``."""
        token = uuid.uuid4().hex
        key = f"_ready/{token}.txt"
        payload = f"gridstorm readiness probe {token}".encode()
        self._write(key, payload, "text/plain")
        try:
            if self._read(key) != payload:
                raise ArtifactIntegrityError("readiness probe read back different bytes")
        finally:
            self.delete(key)
        return f"supabase:{self.bucket} write/read/delete round-trip ok"


def make_store(settings: Any) -> ArtifactStore:
    if settings.artifact_store == "supabase":
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise ValueError(
                "GRIDSTORM_ARTIFACT_STORE=supabase requires SUPABASE_URL and "
                "SUPABASE_SERVICE_ROLE_KEY"
            )
        return SupabaseArtifactStore(
            settings.supabase_url,
            settings.supabase_service_role_key,
            settings.supabase_bucket,
            timeout_s=settings.supabase_storage_timeout_s,
        )
    if settings.artifact_store == "s3":
        if not settings.s3_bucket:
            raise ValueError("GRIDSTORM_ARTIFACT_STORE=s3 requires GRIDSTORM_S3_BUCKET")
        return S3ArtifactStore(
            settings.s3_bucket,
            endpoint_url=settings.s3_endpoint_url,
            region=settings.s3_region,
            prefix=settings.s3_prefix,
        )
    return LocalArtifactStore(settings.resolved_artifact_dir)
