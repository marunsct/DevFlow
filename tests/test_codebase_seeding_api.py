"""The API surface for seeding a run from an existing codebase.

Greenfield runs (no existing code) and brownfield runs (adding features to an
MVP) go through the same endpoints; the difference is whether `source` is set
when the run starts.
"""

import io
import os
import subprocess
import zipfile
from pathlib import Path

import pytest


def _zip_bytes(entries: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return buffer.getvalue()


def _create_run(client) -> str:
    response = client.post(
        "/api/runs",
        files=[("files", ("brief.md", b"# Add billing to the MVP", "text/markdown"))],
    )
    assert response.status_code == 201, response.text
    return response.json()["run_id"]


@pytest.fixture
def run_id(client):
    return _create_run(client)


# ---------------------------------------------------------------------------
# Uploading a codebase archive
# ---------------------------------------------------------------------------


def test_an_archive_can_be_uploaded_for_a_run(client, run_id):
    response = client.post(
        f"/api/runs/{run_id}/codebase",
        files=[("file", ("mvp.zip", _zip_bytes({"app/main.py": "run()"}), "application/zip"))],
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["original_name"] == "mvp.zip"
    assert body["upload_id"].endswith(".zip")
    assert body["file_size_bytes"] > 0


def test_a_compound_suffix_archive_is_accepted(client, run_id):
    """`Path.suffix` sees only `.gz`, which would reject every `.tar.gz`."""
    response = client.post(
        f"/api/runs/{run_id}/codebase",
        files=[("file", ("mvp.tar.gz", b"\x1f\x8b\x08\x00" + b"0" * 32, "application/gzip"))],
    )

    assert response.status_code == 201, response.text


def test_a_document_is_not_a_codebase(client, run_id):
    response = client.post(
        f"/api/runs/{run_id}/codebase",
        files=[("file", ("notes.md", b"# not a codebase", "text/markdown"))],
    )

    assert response.status_code == 415
    assert "not a supported file type" in response.json()["detail"].lower()


def test_an_oversized_archive_is_refused(client, run_id, monkeypatch):
    monkeypatch.setattr("app.server.runs.DEFAULT_MAX_ARCHIVE_BYTES", 64)

    response = client.post(
        f"/api/runs/{run_id}/codebase",
        files=[("file", ("big.zip", _zip_bytes({"f": "x" * 5000}), "application/zip"))],
    )

    assert response.status_code == 413


def test_uploading_a_codebase_requires_authentication(authed_app, run_id):
    from fastapi.testclient import TestClient

    from app.server.auth import get_current_active_user, require_admin, require_operator

    authed_app.dependency_overrides.clear()
    with TestClient(authed_app) as anonymous:
        response = anonymous.post(
            f"/api/runs/{run_id}/codebase",
            files=[("file", ("mvp.zip", _zip_bytes({"a": "b"}), "application/zip"))],
        )

    assert response.status_code == 401


def test_a_codebase_cannot_be_swapped_after_the_run_starts(client, run_id):
    client.post(f"/api/runs/{run_id}/start", json={})

    response = client.post(
        f"/api/runs/{run_id}/codebase",
        files=[("file", ("late.zip", _zip_bytes({"a": "b"}), "application/zip"))],
    )

    assert response.status_code == 409
    assert "workspace is fixed" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Starting a run from a source
# ---------------------------------------------------------------------------


def _workspace_for(run_id: str) -> Path:
    root = Path(os.environ["WORKFLOW_WORKSPACE_ROOT"])
    matches = list(root.glob(f"*{run_id}"))
    assert matches, f"no workspace allocated for {run_id}"
    return matches[0]


def test_a_greenfield_run_starts_with_an_empty_workspace(client, run_id):
    """Scenario 1: no existing code, the agents create it."""
    response = client.post(f"/api/runs/{run_id}/start", json={})

    assert response.status_code == 202, response.text
    assert not any(_workspace_for(run_id).iterdir())


def test_an_explicit_empty_source_is_also_greenfield(client, run_id):
    response = client.post(f"/api/runs/{run_id}/start", json={"source": {"type": "empty"}})

    assert response.status_code == 202, response.text


def test_a_run_starts_from_an_uploaded_codebase(client, run_id):
    """Scenario 2: adding features to an existing MVP."""
    upload = client.post(
        f"/api/runs/{run_id}/codebase",
        files=[(
            "file",
            ("mvp.zip", _zip_bytes({"mvp/app/main.py": "run()", "mvp/README.md": "# MVP"}), "application/zip"),
        )],
    ).json()

    response = client.post(
        f"/api/runs/{run_id}/start",
        json={"source": {"type": "archive", "upload_id": upload["upload_id"]}},
    )

    assert response.status_code == 202, response.text
    workspace = _workspace_for(run_id)
    assert (workspace / "app" / "main.py").read_text() == "run()"
    assert (workspace / "README.md").read_text() == "# MVP"


def test_an_unknown_upload_id_is_a_client_error(client, run_id):
    response = client.post(
        f"/api/runs/{run_id}/start",
        json={"source": {"type": "archive", "upload_id": "no-such-upload.zip"}},
    )

    assert response.status_code == 400
    assert "could not be found" in response.json()["detail"]


def test_an_upload_id_cannot_escape_the_upload_directory(client, run_id):
    """The id is a server-generated filename, but it arrives from a request."""
    response = client.post(
        f"/api/runs/{run_id}/start",
        json={"source": {"type": "archive", "upload_id": "../../../etc/passwd"}},
    )

    assert response.status_code == 400
    assert "could not be found" in response.json()["detail"]


def test_a_disallowed_git_transport_is_refused_before_any_clone(client, run_id):
    response = client.post(
        f"/api/runs/{run_id}/start",
        json={"source": {"type": "git", "url": "ext::sh -c 'id > /tmp/pwned'"}},
    )

    assert response.status_code == 400
    assert "transport is not allowed" in response.json()["detail"]


def test_cloning_an_internal_address_is_refused(client, run_id):
    response = client.post(
        f"/api/runs/{run_id}/start",
        json={"source": {"type": "git", "url": "https://169.254.169.254/latest/meta-data/"}},
    )

    assert response.status_code == 400
    assert "private or loopback" in response.json()["detail"]


def test_a_run_starts_from_a_git_repository(client, run_id, tmp_path, monkeypatch):
    monkeypatch.setenv("SEED_ALLOWED_SCHEMES", "file")
    origin = tmp_path / "origin"
    origin.mkdir()
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@e.x",
        "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@e.x",
    }
    subprocess.run(["git", "init", "-q", "-b", "main", str(origin)], check=True, env=env)
    (origin / "service.py").write_text("serve()")
    subprocess.run(["git", "-C", str(origin), "add", "-A"], check=True, env=env)
    subprocess.run(["git", "-C", str(origin), "commit", "-qm", "mvp"], check=True, env=env)

    response = client.post(
        f"/api/runs/{run_id}/start",
        json={"source": {"type": "git", "url": f"file://{origin}", "depth": 0}},
    )

    assert response.status_code == 202, response.text
    workspace = _workspace_for(run_id)
    assert (workspace / "service.py").read_text() == "serve()"
    assert (workspace / ".git").is_dir()


def test_a_clone_token_never_reaches_the_audit_log(client, run_id, tmp_path, monkeypatch):
    """The token is request-scoped. The audit row outlives the run."""
    monkeypatch.setenv("SEED_ALLOWED_SCHEMES", "file")
    origin = tmp_path / "origin"
    origin.mkdir()
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@e.x",
        "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@e.x",
    }
    subprocess.run(["git", "init", "-q", "-b", "main", str(origin)], check=True, env=env)
    (origin / "a.py").write_text("x")
    subprocess.run(["git", "-C", str(origin), "add", "-A"], check=True, env=env)
    subprocess.run(["git", "-C", str(origin), "commit", "-qm", "c"], check=True, env=env)

    client.post(
        f"/api/runs/{run_id}/start",
        json={
            "source": {
                "type": "git", "url": f"file://{origin}",
                "token": "ghp_supersecrettoken", "depth": 0,
            }
        },
    )

    from app.server.auth import get_db_connection

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT detail FROM audit_log WHERE subject = %s", (run_id,))
            rows = cur.fetchall()

    assert rows, "the start should have been audited"
    assert not any("ghp_supersecrettoken" in str(row[0]) for row in rows)


def test_an_unknown_source_type_is_rejected_by_the_schema(client, run_id):
    response = client.post(
        f"/api/runs/{run_id}/start", json={"source": {"type": "ftp", "url": "ftp://x/y"}}
    )

    assert response.status_code == 422
