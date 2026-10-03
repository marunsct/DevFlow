"""API-level security behaviour: authentication, tenancy and path containment.

These are regression tests for the findings that made the artifact endpoint an
unauthenticated arbitrary file read, and for the absence of any authorisation
model behind authentication.
"""

import io

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def unauthenticated_client(setup_db):
    """A client with no auth overrides, so real dependencies apply."""
    from app.server.api import create_app

    with TestClient(create_app()) as client:
        yield client


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/runs"),
        ("get", "/api/runs/run-1"),
        ("get", "/api/runs/run-1/artifacts"),
        ("get", "/api/runs/run-1/artifacts/download?path=x"),
        ("get", "/api/runs/run-1/logs"),
        ("get", "/api/runs/run-1/decisions"),
        ("get", "/api/runs/run-1/evidence"),
        ("post", "/api/runs/run-1/cancel"),
        ("delete", "/api/runs/run-1"),
        ("get", "/api/settings"),
    ],
)
def test_every_run_endpoint_requires_authentication(unauthenticated_client, method, path):
    """The download route in particular used to be mounted with no auth at all."""
    response = getattr(unauthenticated_client, method)(path)
    assert response.status_code == 401, f"{method.upper()} {path} returned {response.status_code}"


def test_liveness_is_public(unauthenticated_client):
    assert unauthenticated_client.get("/api/health").status_code == 200


def test_model_health_requires_admin(unauthenticated_client):
    """It triggers billable model calls, so it is not public."""
    assert unauthenticated_client.get("/api/health/models").status_code == 401


# ---------------------------------------------------------------------------
# Path containment on artifact download
# ---------------------------------------------------------------------------


def _create_run(client) -> str:
    response = client.post(
        "/api/runs",
        files=[("files", ("brief.md", io.BytesIO(b"# Product brief"), "text/markdown"))],
    )
    assert response.status_code == 201, response.text
    return response.json()["run_id"]


@pytest.mark.parametrize(
    "attack",
    [
        "/etc/passwd",
        "/app/.env",
        "../../../../etc/passwd",
        "docs/../../../../etc/hosts",
    ],
)
def test_artifact_download_refuses_to_escape_the_workspace(client, attack):
    run_id = _create_run(client)
    client.post(f"/api/runs/{run_id}/start", json={"workspace_label": "sec"})

    response = client.get(f"/api/runs/{run_id}/artifacts/download", params={"path": attack})
    assert response.status_code in (400, 404)
    assert b"root:" not in response.content


def test_artifact_download_serves_a_file_inside_the_workspace(client):
    from pathlib import Path

    run_id = _create_run(client)
    client.post(f"/api/runs/{run_id}/start", json={"workspace_label": "sec"})

    detail = client.get(f"/api/runs/{run_id}").json()
    assert detail["run_id"] == run_id

    from app.server.run_store import RunStore

    record = RunStore.shared().load(run_id)
    workspace = Path(record.repo_root)
    (workspace / "docs").mkdir(parents=True, exist_ok=True)
    (workspace / "docs" / "spec.md").write_text("the specification")

    response = client.get(f"/api/runs/{run_id}/artifacts/download", params={"path": "docs/spec.md"})
    assert response.status_code == 200
    assert response.content == b"the specification"


# ---------------------------------------------------------------------------
# Tenancy
# ---------------------------------------------------------------------------


def test_a_run_in_another_tenant_is_not_visible(authed_app, test_user):
    """Cross-tenant access returns 404, not 403: confirming a run exists is
    itself a disclosure."""
    from app.server.auth import UserInDB, get_current_active_user, require_operator
    from app.server.run_store import RunStore
    from app.server.runner import RunRecord

    store = RunStore.shared()
    store.save(
        RunRecord(
            run_id="run-other-tenant",
            thread_id="thread-x",
            document_names=[],
            document_paths=[],
            owner="mallory",
            tenant_id="some-other-tenant",
        )
    )

    outsider = UserInDB(
        username="bob", hashed_password="x", disabled=False, role="operator", tenant_id="acme"
    )

    async def _as_outsider():
        return outsider

    for dependency in (get_current_active_user, require_operator):
        authed_app.dependency_overrides[dependency] = _as_outsider

    with TestClient(authed_app) as client:
        assert client.get("/api/runs/run-other-tenant").status_code == 404
        assert client.post("/api/runs/run-other-tenant/cancel").status_code == 404
        assert client.delete("/api/runs/run-other-tenant").status_code == 404

        listed = client.get("/api/runs").json()["runs"]
        assert all(r["run_id"] != "run-other-tenant" for r in listed)


# ---------------------------------------------------------------------------
# Upload validation
# ---------------------------------------------------------------------------


def test_an_unsupported_file_type_is_rejected(client):
    response = client.post(
        "/api/runs",
        files=[("files", ("payload.exe", io.BytesIO(b"MZ"), "application/octet-stream"))],
    )
    assert response.status_code == 415


def test_too_many_documents_are_rejected(client):
    files = [
        ("files", (f"doc{i}.md", io.BytesIO(b"content"), "text/markdown")) for i in range(20)
    ]
    assert client.post("/api/runs", files=files).status_code == 400


def test_starting_an_already_started_run_conflicts(client):
    run_id = _create_run(client)
    assert client.post(f"/api/runs/{run_id}/start", json={}).status_code == 202
    assert client.post(f"/api/runs/{run_id}/start", json={}).status_code == 409


def test_a_run_start_cannot_choose_a_server_path(client):
    """artifact_directory is gone from the contract; extra fields are rejected."""
    run_id = _create_run(client)
    response = client.post(f"/api/runs/{run_id}/start", json={"artifact_directory": "/"})
    assert response.status_code == 422


def test_deleting_a_non_terminal_run_conflicts(client):
    run_id = _create_run(client)
    client.post(f"/api/runs/{run_id}/start", json={})
    assert client.delete(f"/api/runs/{run_id}").status_code == 409


def test_security_headers_are_present(client):
    response = client.get("/api/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "X-Correlation-ID" in response.headers


def test_a_forged_correlation_id_is_replaced(client):
    """An arbitrary client string ends up in structured logs."""
    response = client.get("/api/health", headers={"X-Correlation-ID": 'bad"\ninjected'})
    assert response.headers["X-Correlation-ID"] != 'bad"\ninjected'
