"""Object storage (MinIO / S3) for raw HTML, screenshots, render snapshots and reports.

Key layout: `raw/{post_id}.html`, `shots/{post_id}/{viewport}.png`,
`render/{post_id}.json`, `media/{post_id}/*`, `reports/{finding_id}.pdf`.
"""

from __future__ import annotations

import hashlib
import io
import logging
import threading
from datetime import timedelta
from functools import cache
from typing import Protocol

from minio import Minio
from minio.error import S3Error

from investwatch.config import get_settings

log = logging.getLogger(__name__)

SHA_META = "sha256"
"""User metadata key holding the SHA-256 of every object written by `MinioStore`."""


class ObjectStore(Protocol):
    """Minimal blob store interface used by the pipeline and the API."""

    def put_bytes(self, key: str, data: bytes, content_type: str) -> str:
        """Store `data` under `key` and return the key."""
        ...

    def get_bytes(self, key: str) -> bytes | None:
        """Return the object, or None when it does not exist."""
        ...

    def presigned_url(self, key: str, expires_s: int = 3600) -> str:
        """Return a time-limited download URL."""
        ...

    def describe(self, key: str) -> tuple[int, str] | None:
        """Size and SHA-256 of a stored object, or None when it does not exist."""
        ...


class MinioStore:
    """MinIO-backed store; creates the bucket on first use."""

    def __init__(
        self, endpoint: str, access_key: str, secret_key: str, bucket: str, secure: bool
    ) -> None:
        """Create a client (no network I/O until first use)."""
        self._client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
        self._bucket = bucket
        self._ready = False
        self._lock = threading.Lock()

    def ensure_bucket(self) -> None:
        """Create the bucket if it is missing."""
        with self._lock:
            if self._ready:
                return
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)
                log.info("created bucket %s", self._bucket)
            self._ready = True

    def put_bytes(self, key: str, data: bytes, content_type: str) -> str:
        """Store `data` under `key` and return the key."""
        self.ensure_bucket()
        self._client.put_object(
            self._bucket,
            key,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type,
            # Evidence hash kept with the object: the provenance view reads it without a download.
            metadata={SHA_META: hashlib.sha256(data).hexdigest()},
        )
        return key

    def describe(self, key: str) -> tuple[int, str] | None:
        """Size and SHA-256 from the object's metadata (older objects: hashed once read)."""
        self.ensure_bucket()
        try:
            stat = self._client.stat_object(self._bucket, key)
        except S3Error as exc:
            if exc.code in {"NoSuchKey", "NoSuchObject"}:
                return None
            raise
        meta = {k.lower(): v for k, v in (stat.metadata or {}).items()}
        sha = meta.get(f"x-amz-meta-{SHA_META}")
        if sha:
            return int(stat.size or 0), str(sha)
        data = self.get_bytes(key)
        return (len(data), hashlib.sha256(data).hexdigest()) if data is not None else None

    def get_bytes(self, key: str) -> bytes | None:
        """Return the object, or None when it does not exist."""
        self.ensure_bucket()
        try:
            response = self._client.get_object(self._bucket, key)
        except S3Error as exc:
            if exc.code in {"NoSuchKey", "NoSuchObject"}:
                return None
            raise
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def ping(self) -> bool:
        """True when the server answers and the bucket exists (status page)."""
        return bool(self._client.bucket_exists(self._bucket))

    def presigned_url(self, key: str, expires_s: int = 3600) -> str:
        """Return a time-limited download URL (host as seen from inside Compose)."""
        return self._client.presigned_get_object(
            self._bucket, key, expires=timedelta(seconds=expires_s)
        )


class MemoryStore:
    """In-process store for tests and local runs without MinIO."""

    def __init__(self) -> None:
        """Start empty."""
        self.objects: dict[str, tuple[bytes, str]] = {}

    def put_bytes(self, key: str, data: bytes, content_type: str) -> str:
        """Store `data` under `key` and return the key."""
        self.objects[key] = (data, content_type)
        return key

    def get_bytes(self, key: str) -> bytes | None:
        """Return the object, or None when it does not exist."""
        item = self.objects.get(key)
        return item[0] if item else None

    def presigned_url(self, key: str, expires_s: int = 3600) -> str:
        """Return the API proxy path (there is nothing to sign in memory)."""
        return f"/api/objects/{key}"

    def describe(self, key: str) -> tuple[int, str] | None:
        """Size and SHA-256 of a stored object, or None when it does not exist."""
        data = self.get_bytes(key)
        return (len(data), hashlib.sha256(data).hexdigest()) if data is not None else None


@cache
def get_store() -> ObjectStore:
    """Return the configured object store."""
    settings = get_settings()
    if settings.storage_backend == "memory":
        return MemoryStore()
    return MinioStore(
        settings.minio_endpoint,
        settings.minio_root_user,
        settings.minio_root_password,
        settings.minio_bucket,
        settings.minio_secure,
    )


def put_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """Store bytes in the configured store."""
    return get_store().put_bytes(key, data, content_type)


def presigned_url(key: str, expires_s: int = 3600) -> str:
    """Return a download URL from the configured store."""
    return get_store().presigned_url(key, expires_s)
