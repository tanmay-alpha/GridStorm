"""ArtifactStore: immutable, content-addressed blobs (``sha256/<hash>.<ext>``).

Backends: local filesystem (default) and S3-compatible object storage via boto3 (AWS S3,
Cloudflare R2 with ``GRIDSTORM_S3_ENDPOINT_URL``, MinIO, ...). Credentials come from the standard
boto3 environment (``AWS_ACCESS_KEY_ID`` / ``AWS_SECRET_ACCESS_KEY``), never from code.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import APIError


class ArtifactIntegrityError(APIError):
    status_code = 500
    code = "artifact_integrity_error"


@dataclass(frozen=True)
class StoredBlob:
    backend: str
    key: str
    sha256: str
    bytes: int
    content_type: str


def content_key(sha256: str, ext: str) -> str:
    return f"sha256/{sha256}.{ext}"


class ArtifactStore(ABC):
    backend: str

    def put(self, data: bytes, *, ext: str = "json", content_type: str = "application/json") -> StoredBlob:
        digest = hashlib.sha256(data).hexdigest()
        key = content_key(digest, ext)
        if not self._exists(key):
            self._write(key, data, content_type)
        return StoredBlob(self.backend, key, digest, len(data), content_type)

    def get(self, key: str, *, expected_sha256: str | None = None) -> bytes:
        data = self._read(key)
        if expected_sha256 is not None:
            actual = hashlib.sha256(data).hexdigest()
            if actual != expected_sha256:
                raise ArtifactIntegrityError(
                    "stored artifact does not match its recorded sha256",
                    details={"key": key, "expected_sha256": expected_sha256, "actual_sha256": actual},
                )
        return data

    @abstractmethod
    def _exists(self, key: str) -> bool: ...

    @abstractmethod
    def _write(self, key: str, data: bytes, content_type: str) -> None: ...

    @abstractmethod
    def _read(self, key: str) -> bytes: ...

    @abstractmethod
    def check_writable(self) -> str:
        """Raise on failure; return a short human-readable detail on success."""


class LocalArtifactStore(ArtifactStore):
    backend = "local"

    def __init__(self, root: Path) -> None:
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
        # write-then-rename so readers never observe a partial blob
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def _read(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError as exc:
            raise ArtifactIntegrityError(
                "stored artifact is missing", code="artifact_missing", details={"key": key}
            ) from exc

    def check_writable(self) -> str:
        self.root.mkdir(parents=True, exist_ok=True)
        probe = self.root / f".ready-{uuid.uuid4().hex}"
        probe.write_bytes(b"ok")
        probe.unlink()
        return f"local:{self.root}"


class S3ArtifactStore(ArtifactStore):
    backend = "s3"

    def __init__(
        self,
        bucket: str,
        *,
        endpoint_url: str | None = None,
        region: str | None = None,
        prefix: str = "",
        client: Any = None,
    ) -> None:
        if client is None:
            import boto3

            client = boto3.client("s3", endpoint_url=endpoint_url, region_name=region)
        self.client = client
        self.bucket = bucket
        self.prefix = prefix.strip("/")

    def _k(self, key: str) -> str:
        return f"{self.prefix}/{key}" if self.prefix else key

    def _exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=self.bucket, Key=self._k(key))
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def _write(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(
            Bucket=self.bucket, Key=self._k(key), Body=data, ContentType=content_type
        )

    def _read(self, key: str) -> bytes:
        from botocore.exceptions import ClientError

        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=self._k(key))
        except ClientError as exc:
            raise ArtifactIntegrityError(
                "stored artifact is missing", code="artifact_missing", details={"key": key}
            ) from exc
        return obj["Body"].read()

    def check_writable(self) -> str:
        probe = self._k(f"_ready/{uuid.uuid4().hex}")
        self.client.put_object(Bucket=self.bucket, Key=probe, Body=b"ok")
        self.client.delete_object(Bucket=self.bucket, Key=probe)
        return f"s3:{self.bucket}"


def make_store(settings: Any) -> ArtifactStore:
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
