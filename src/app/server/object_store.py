"""Durable object storage for uploads and run artifacts.

Why this exists
---------------
Uploads and artifacts live on the ``appdata`` volume, shared between the API and
the worker by Docker. That works on one host and breaks in two ways as soon as
there is more than one:

*   **Durability.** Losing the volume loses every artifact from every run. There
    is no second copy anywhere.
*   **Reach.** The API serves artifact downloads by reading the workspace. A
    worker on another node writes to a different disk, so the API serves a 404
    for work that definitely happened.

An S3-compatible store (MinIO in compose, or any cloud provider) fixes both. The
filesystem stays the *working* surface - agents run ``ls``, ``cat`` and
``pytest``, and object storage cannot back a working tree - so this is a durable
side copy, not a replacement:

    put_file(key, path)      after a file is written, push a durable copy
    ensure_local(key, path)  before a file is read, fetch it if this node lacks it

That pairing is what makes a second worker node work: whichever node wrote the
file, any node can read it back.

Backends
--------
``LocalObjectStore`` is the default and needs no infrastructure - it copies under
``DATA_DIR/objects``. It gives the same interface so nothing has to branch on
whether object storage is configured, and it is what the tests and a
single-node deployment use.

``S3ObjectStore`` is used when ``OBJECT_STORE_ENDPOINT`` (MinIO) or
``OBJECT_STORE_BUCKET`` with AWS credentials is set.
"""

from __future__ import annotations

import logging
import os
import shutil
import threading
from pathlib import Path
from typing import Iterator, Protocol

logger = logging.getLogger(__name__)


class ObjectStoreError(RuntimeError):
    """An object could not be stored or retrieved."""


def _safe_key(key: str) -> str:
    """Normalise a key and refuse one that would escape the store's root.

    Keys are derived from filenames that were themselves derived from uploads,
    so they are not free of caller influence. For the local backend a key is
    joined onto a directory, which makes ``../`` a path traversal; for S3 it
    would silently create a confusing layout.
    """
    cleaned = (key or "").strip().lstrip("/")
    if not cleaned:
        raise ObjectStoreError("An object key is required.")
    parts = [p for p in Path(cleaned).parts if p not in (".", "")]
    if any(p == ".." for p in parts):
        raise ObjectStoreError(f"Invalid object key: {key}")
    return "/".join(parts)


class ObjectStore(Protocol):
    """The storage operations the application needs. Both backends satisfy it."""

    def put_file(self, key: str, source: str | Path) -> str: ...
    def get_file(self, key: str, destination: str | Path) -> Path: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...
    def list_prefix(self, prefix: str) -> list[str]: ...


# ---------------------------------------------------------------------------
# Local filesystem backend
# ---------------------------------------------------------------------------


class LocalObjectStore:
    """Keeps objects under a directory. The default when nothing is configured.

    Deliberately not a no-op: keeping the same read/write path exercised in
    development and tests means the S3 backend is not the only place the
    ``put``/``ensure_local`` pairing is ever run.
    """

    def __init__(self, root: str | Path | None = None) -> None:
        base = root or os.environ.get("OBJECT_STORE_PATH") or (
            Path(os.environ.get("DATA_DIR", ".")) / "objects"
        )
        self.root = Path(base).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.root / _safe_key(key)

    def put_file(self, key: str, source: str | Path) -> str:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return key

    def get_file(self, key: str, destination: str | Path) -> Path:
        source = self._path(key)
        if not source.is_file():
            raise ObjectStoreError(f"No stored object for key '{key}'.")
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return target

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def list_prefix(self, prefix: str) -> list[str]:
        base = self.root / _safe_key(prefix) if prefix else self.root
        if not base.exists():
            return []
        return sorted(
            str(p.relative_to(self.root)) for p in base.rglob("*") if p.is_file()
        )

    def __repr__(self) -> str:
        return f"LocalObjectStore(root={self.root})"


# ---------------------------------------------------------------------------
# S3-compatible backend (MinIO, AWS S3, and friends)
# ---------------------------------------------------------------------------


class S3ObjectStore:
    """Stores objects in any S3-compatible service.

    ``boto3`` is imported lazily so a deployment that never configures object
    storage does not need it installed.
    """

    def __init__(
        self,
        bucket: str,
        *,
        endpoint_url: str | None = None,
        region: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        secure: bool = True,
    ) -> None:
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover - depends on the install
            raise ObjectStoreError(
                "Object storage is configured but boto3 is not installed. "
                "Install the 's3' extra, or unset OBJECT_STORE_BUCKET."
            ) from exc

        self.bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region or "us-east-1",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            use_ssl=secure,
            # Path addressing, because MinIO and most self-hosted S3 services do
            # not serve virtual-host style buckets.
            config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 3}),
        )
        self._ensured = False
        self._lock = threading.Lock()

    def _ensure_bucket(self) -> None:
        """Create the bucket on first use if it is not already there."""
        if self._ensured:
            return
        with self._lock:
            if self._ensured:
                return
            from botocore.exceptions import ClientError

            try:
                self._client.head_bucket(Bucket=self.bucket)
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code", "")
                if code not in ("404", "NoSuchBucket", "NotFound"):
                    raise ObjectStoreError(
                        f"Cannot reach bucket '{self.bucket}': {exc}"
                    ) from exc
                try:
                    self._client.create_bucket(Bucket=self.bucket)
                except ClientError as create_exc:
                    # A concurrent worker may have won the race; that is fine.
                    if create_exc.response.get("Error", {}).get("Code") not in (
                        "BucketAlreadyOwnedByYou", "BucketAlreadyExists",
                    ):
                        raise ObjectStoreError(
                            f"Could not create bucket '{self.bucket}': {create_exc}"
                        ) from create_exc
            except Exception as exc:  # noqa: BLE001
                # Missing credentials and an unreachable endpoint are
                # BotoCoreError, not ClientError. They used to escape from here
                # through every method that calls this first, so a storage
                # misconfiguration surfaced as a 500 on an upload rather than as
                # a skipped archive.
                raise ObjectStoreError(
                    f"Cannot reach bucket '{self.bucket}': {exc}"
                ) from exc
            self._ensured = True

    def put_file(self, key: str, source: str | Path) -> str:
        self._ensure_bucket()
        safe = _safe_key(key)
        try:
            self._client.upload_file(str(source), self.bucket, safe)
        except Exception as exc:  # noqa: BLE001 - boto3 raises a wide family
            raise ObjectStoreError(f"Could not store '{safe}': {exc}") from exc
        return safe

    def get_file(self, key: str, destination: str | Path) -> Path:
        self._ensure_bucket()
        safe = _safe_key(key)
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._client.download_file(self.bucket, safe, str(target))
        except Exception as exc:  # noqa: BLE001
            raise ObjectStoreError(f"Could not fetch '{safe}': {exc}") from exc
        return target

    def exists(self, key: str) -> bool:
        self._ensure_bucket()
        try:
            self._client.head_object(Bucket=self.bucket, Key=_safe_key(key))
            return True
        except Exception:  # noqa: BLE001 - absent and unreachable both mean "no"
            return False

    def delete(self, key: str) -> None:
        self._ensure_bucket()
        try:
            self._client.delete_object(Bucket=self.bucket, Key=_safe_key(key))
        except Exception as exc:  # noqa: BLE001
            raise ObjectStoreError(f"Could not delete '{key}': {exc}") from exc

    def list_prefix(self, prefix: str) -> list[str]:
        self._ensure_bucket()
        keys: list[str] = []
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=_safe_key(prefix) if prefix else ""):
            keys.extend(item["Key"] for item in page.get("Contents", []))
        return sorted(keys)

    def __repr__(self) -> str:
        return f"S3ObjectStore(bucket={self.bucket})"


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

_store: ObjectStore | None = None
_store_lock = threading.Lock()


def object_storage_configured() -> bool:
    """Whether an S3-compatible store has been configured."""
    return bool(os.environ.get("OBJECT_STORE_BUCKET", "").strip())


def build_object_store() -> ObjectStore:
    """Build the configured store, falling back to the local filesystem."""
    if not object_storage_configured():
        return LocalObjectStore()

    return S3ObjectStore(
        bucket=os.environ["OBJECT_STORE_BUCKET"].strip(),
        endpoint_url=os.environ.get("OBJECT_STORE_ENDPOINT") or None,
        region=os.environ.get("OBJECT_STORE_REGION") or None,
        access_key=os.environ.get("OBJECT_STORE_ACCESS_KEY") or None,
        secret_key=os.environ.get("OBJECT_STORE_SECRET_KEY") or None,
        secure=os.environ.get("OBJECT_STORE_SECURE", "true").strip().lower()
        in {"1", "true", "yes", "on"},
    )


def get_object_store() -> ObjectStore:
    """The process-wide store. Built once, like the run store's shared pool."""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = build_object_store()
                logger.info("Object storage: %r", _store)
    return _store


def reset_object_store() -> None:
    """Drop the cached store. For tests that change the configuration."""
    global _store
    with _store_lock:
        _store = None


# ---------------------------------------------------------------------------
# The two operations callers actually use
# ---------------------------------------------------------------------------


def archive_file(key: str, path: str | Path, *, store: ObjectStore | None = None) -> bool:
    """Push a durable copy of `path`. Returns whether it was stored.

    Never raises. A failed archive must not fail the run that produced the
    artifact - the file is still on disk, and the copy can be retried. Losing a
    finished milestone because a storage service was briefly unreachable would
    be a far worse outcome than a missing second copy.
    """
    try:
        (store or get_object_store()).put_file(key, path)
        return True
    except Exception:  # noqa: BLE001 - the contract is "never raises"
        logger.warning("Could not archive %s to object storage", key, exc_info=True)
        return False


def ensure_local(key: str, path: str | Path, *, store: ObjectStore | None = None) -> bool:
    """Make sure `path` exists locally, fetching it from the store if not.

    Returns whether the file is present afterwards. This is what lets a worker
    on a second node read an upload the API received on the first.
    """
    target = Path(path)
    if target.is_file():
        return True
    try:
        (store or get_object_store()).get_file(key, target)
        return True
    except Exception:  # noqa: BLE001 - the contract is "never raises"
        logger.warning("Could not fetch %s from object storage", key, exc_info=True)
        return False


# Directories that are rebuildable input, not produced work. Archiving them
# would upload tens of thousands of objects per run to store a `node_modules`
# that `npm install` reproduces exactly.
_UNARCHIVED_DIRECTORIES = frozenset({
    ".git", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "dist", "build", "target", ".next", ".tox",
})


def archive_directory(
    prefix: str,
    directory: str | Path,
    *,
    relative_paths: list[str] | None = None,
    store: ObjectStore | None = None,
) -> int:
    """Archive the produced files under `directory`. Returns how many were stored.

    `relative_paths` lets a caller supply an already-pruned listing (the API
    uses the same one it shows on the status page, so what gets archived is
    exactly what the run reports as artifacts). Without it, the tree is walked
    and the rebuildable directories above are skipped.
    """
    root = Path(directory)
    if not root.is_dir():
        return 0
    target_store = store or get_object_store()

    if relative_paths is not None:
        candidates = [root / relative for relative in relative_paths]
    else:
        candidates = sorted(root.rglob("*"))

    stored = 0
    for path in candidates:
        if not path.is_file() or path.is_symlink():
            continue
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if _UNARCHIVED_DIRECTORIES & set(relative.parts):
            continue
        if archive_file(f"{prefix}/{relative}", path, store=target_store):
            stored += 1
    return stored


def iter_missing(keys: Iterator[str], store: ObjectStore | None = None) -> list[str]:
    """Which of `keys` the store does not hold. Useful for a consistency check."""
    target_store = store or get_object_store()
    return [key for key in keys if not target_store.exists(key)]


__all__ = [
    "LocalObjectStore",
    "ObjectStore",
    "ObjectStoreError",
    "S3ObjectStore",
    "archive_directory",
    "archive_file",
    "build_object_store",
    "ensure_local",
    "get_object_store",
    "iter_missing",
    "object_storage_configured",
    "reset_object_store",
]
