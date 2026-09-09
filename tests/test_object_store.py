"""Durable storage for uploads and run artifacts.

The filesystem stays the working surface; this is the second copy that survives
a lost volume and that lets a worker on another node read a file the API
received. Both halves of that pairing - archive on write, fetch on read - are
exercised here against the local backend, which is the default and has the same
interface as the S3 one.
"""

from pathlib import Path

import pytest

from app.server.object_store import (
    LocalObjectStore,
    ObjectStoreError,
    archive_directory,
    archive_file,
    build_object_store,
    ensure_local,
    get_object_store,
    iter_missing,
    object_storage_configured,
    reset_object_store,
)


@pytest.fixture
def store(tmp_path):
    return LocalObjectStore(tmp_path / "objects")


@pytest.fixture
def a_file(tmp_path):
    path = tmp_path / "source" / "brief.md"
    path.parent.mkdir(parents=True)
    path.write_text("# a product brief")
    return path


# ---------------------------------------------------------------------------
# Round trip
# ---------------------------------------------------------------------------


def test_a_stored_file_comes_back_intact(store, a_file, tmp_path):
    store.put_file("uploads/brief.md", a_file)

    restored = store.get_file("uploads/brief.md", tmp_path / "restored.md")

    assert restored.read_text() == "# a product brief"


def test_a_missing_key_is_an_error(store, tmp_path):
    with pytest.raises(ObjectStoreError, match="No stored object"):
        store.get_file("nope.md", tmp_path / "out.md")


def test_existence_is_reported(store, a_file):
    assert store.exists("uploads/brief.md") is False

    store.put_file("uploads/brief.md", a_file)

    assert store.exists("uploads/brief.md") is True


def test_deleting_is_idempotent(store, a_file):
    store.put_file("k", a_file)
    store.delete("k")
    store.delete("k")

    assert store.exists("k") is False


def test_a_prefix_lists_only_its_own_keys(store, a_file):
    store.put_file("runs/r1/a.md", a_file)
    store.put_file("runs/r1/nested/b.md", a_file)
    store.put_file("runs/r2/c.md", a_file)

    listed = store.list_prefix("runs/r1")

    assert listed == ["runs/r1/a.md", "runs/r1/nested/b.md"]


# ---------------------------------------------------------------------------
# Key containment
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["../escaped", "runs/../../etc/passwd", "a/../../b"])
def test_a_key_cannot_escape_the_store_root(store, a_file, key):
    """Keys derive from upload filenames, so they are not free of caller influence."""
    with pytest.raises(ObjectStoreError, match="Invalid object key"):
        store.put_file(key, a_file)


def test_an_empty_key_is_refused(store, a_file):
    with pytest.raises(ObjectStoreError, match="key is required"):
        store.put_file("", a_file)


def test_a_leading_slash_is_normalised_not_treated_as_absolute(store, a_file):
    store.put_file("/uploads/brief.md", a_file)

    assert store.exists("uploads/brief.md")


# ---------------------------------------------------------------------------
# The archive / fetch pairing
# ---------------------------------------------------------------------------


def test_archiving_reports_success(store, a_file):
    assert archive_file("uploads/brief.md", a_file, store=store) is True


def test_archiving_a_missing_file_does_not_raise(store, tmp_path):
    """A storage failure must never fail the run that produced the artifact."""
    assert archive_file("k", tmp_path / "gone.md", store=store) is False


def test_archiving_a_bad_key_does_not_raise(store, a_file):
    assert archive_file("../escape", a_file, store=store) is False


def test_a_file_already_present_locally_is_not_fetched(store, a_file):
    """The single-node case: nothing to do, and no store call to fail."""
    assert ensure_local("never-stored", a_file, store=store) is True


def test_a_file_missing_locally_is_fetched(store, a_file, tmp_path):
    """The multi-node case: the upload landed on another replica's disk."""
    archive_file("uploads/brief.md", a_file, store=store)
    elsewhere = tmp_path / "other-node" / "brief.md"

    assert ensure_local("uploads/brief.md", elsewhere, store=store) is True
    assert elsewhere.read_text() == "# a product brief"


def test_a_file_that_is_nowhere_reports_failure(store, tmp_path):
    assert ensure_local("uploads/gone.md", tmp_path / "x.md", store=store) is False


def test_iter_missing_names_what_the_store_lacks(store, a_file):
    archive_file("have.md", a_file, store=store)

    assert iter_missing(iter(["have.md", "lack.md"]), store=store) == ["lack.md"]


# ---------------------------------------------------------------------------
# Archiving a workspace
# ---------------------------------------------------------------------------


def _workspace(root: Path) -> Path:
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "spec.md").write_text("spec")
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("run()")
    (root / "node_modules" / "left-pad").mkdir(parents=True)
    (root / "node_modules" / "left-pad" / "index.js").write_text("module.exports=1")
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("[core]")
    return root


def test_a_workspace_is_archived_without_its_rebuildable_directories(store, tmp_path):
    """`node_modules` is reproduced exactly by `npm install`; archiving it would
    upload tens of thousands of objects per run to store nothing."""
    workspace = _workspace(tmp_path / "ws")

    stored = archive_directory("runs/r1", workspace, store=store)

    assert stored == 2
    assert sorted(store.list_prefix("runs/r1")) == [
        "runs/r1/docs/spec.md",
        "runs/r1/src/app.py",
    ]


def test_an_explicit_listing_is_honoured(store, tmp_path):
    """The API passes the same pruned listing it shows on the status page."""
    workspace = _workspace(tmp_path / "ws")

    stored = archive_directory(
        "runs/r2", workspace, relative_paths=["docs/spec.md"], store=store
    )

    assert stored == 1
    assert store.list_prefix("runs/r2") == ["runs/r2/docs/spec.md"]


def test_a_listing_entry_outside_the_workspace_is_skipped(store, tmp_path):
    workspace = _workspace(tmp_path / "ws")
    (tmp_path / "outside.md").write_text("secret")

    stored = archive_directory(
        "runs/r3", workspace, relative_paths=["../outside.md"], store=store
    )

    assert stored == 0


def test_archiving_a_directory_that_is_not_there_is_zero(store, tmp_path):
    assert archive_directory("runs/r4", tmp_path / "gone", store=store) == 0


def test_symlinks_are_not_archived(store, tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "real.md").write_text("x")
    (workspace / "link.md").symlink_to(workspace / "real.md")

    assert archive_directory("runs/r5", workspace, store=store) == 1


# ---------------------------------------------------------------------------
# Backend selection
# ---------------------------------------------------------------------------


def test_the_default_backend_needs_no_infrastructure(monkeypatch, tmp_path):
    monkeypatch.delenv("OBJECT_STORE_BUCKET", raising=False)
    monkeypatch.setenv("OBJECT_STORE_PATH", str(tmp_path / "objects"))

    assert object_storage_configured() is False
    assert isinstance(build_object_store(), LocalObjectStore)


def test_a_configured_bucket_selects_the_s3_backend(monkeypatch):
    monkeypatch.setenv("OBJECT_STORE_BUCKET", "artifacts")
    monkeypatch.setenv("OBJECT_STORE_ENDPOINT", "http://minio:9000")
    monkeypatch.setenv("OBJECT_STORE_ACCESS_KEY", "key")
    monkeypatch.setenv("OBJECT_STORE_SECRET_KEY", "secret")
    monkeypatch.setenv("OBJECT_STORE_SECURE", "false")

    assert object_storage_configured() is True

    store = build_object_store()
    assert store.bucket == "artifacts"
    # Constructed but never contacted: no bucket call happens until first use,
    # so building the store cannot block startup on a slow storage service.
    assert store._ensured is False


def test_the_shared_store_is_built_once(monkeypatch, tmp_path):
    monkeypatch.delenv("OBJECT_STORE_BUCKET", raising=False)
    monkeypatch.setenv("OBJECT_STORE_PATH", str(tmp_path / "objects"))
    reset_object_store()

    try:
        assert get_object_store() is get_object_store()
    finally:
        reset_object_store()


# ---------------------------------------------------------------------------
# Storage failures must stay contained
# ---------------------------------------------------------------------------
#
# Archiving is a second copy of something already on disk. A storage outage must
# degrade to "no second copy", never to a failed upload or a failed run. The
# first version caught only ObjectStoreError and OSError, so botocore's
# NoCredentialsError - which is neither - escaped and turned a misconfigured
# bucket into a 500 on every document upload.


class _BrokenStore:
    """A store whose every operation fails the way a real outage does."""

    def __init__(self, exception: Exception) -> None:
        self.exception = exception

    def put_file(self, key, source):
        raise self.exception

    def get_file(self, key, destination):
        raise self.exception

    def exists(self, key):
        raise self.exception

    def delete(self, key):
        raise self.exception

    def list_prefix(self, prefix):
        raise self.exception


@pytest.fixture(params=["credentials", "connection", "generic"])
def broken_store(request):
    from botocore.exceptions import EndpointConnectionError, NoCredentialsError

    return _BrokenStore({
        "credentials": NoCredentialsError(),
        "connection": EndpointConnectionError(endpoint_url="http://minio:9000"),
        "generic": RuntimeError("storage is on fire"),
    }[request.param])


def test_an_outage_does_not_break_archiving(broken_store, a_file):
    assert archive_file("uploads/brief.md", a_file, store=broken_store) is False


def test_an_outage_does_not_break_fetching(broken_store, tmp_path):
    assert ensure_local("uploads/brief.md", tmp_path / "x.md", store=broken_store) is False


def test_an_outage_does_not_break_archiving_a_workspace(broken_store, tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "spec.md").write_text("spec")

    assert archive_directory("runs/r", workspace, store=broken_store) == 0


def test_a_present_local_file_is_unaffected_by_an_outage(broken_store, a_file):
    """The single-node path never touches the store, so it cannot fail."""
    assert ensure_local("anything", a_file, store=broken_store) is True
