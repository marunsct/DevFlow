import pytest
from pathlib import Path

# `client` comes from conftest: a real app with a real user object.

def test_health_contract(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "ok"

def test_runs_contract(client, tmp_path: Path):
    file1 = tmp_path / "doc1.txt"
    file1.write_text("Product Requirements Document")
    
    with open(file1, "rb") as f1:
        response = client.post(
            "/api/runs",
            files=[("files", ("doc1.txt", f1, "text/plain"))]
        )
    assert response.status_code == 201
    data = response.json()
    assert "run_id" in data
    assert "status" in data
    assert data["status"] == "created"
    
    run_id = data["run_id"]
    
    # Get run
    response = client.get(f"/api/runs/{run_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == run_id

    # List runs
    response = client.get("/api/runs")
    assert response.status_code == 200
    data = response.json()
    assert "runs" in data
    assert isinstance(data["runs"], list)
    assert len(data["runs"]) >= 1
    
    # Start run (mock artifact dir)
    response = client.post(
        f"/api/runs/{run_id}/start",
        json={"workspace_label": "contract-test"}
    )
    assert response.status_code == 202

    # Cancel run
    response = client.post(f"/api/runs/{run_id}/cancel")
    assert response.status_code in (200, 400) # Depends on state

    # Resume run
    response = client.post(f"/api/runs/{run_id}/resume", json={"action": "approve"})
    assert response.status_code in (202, 400, 409)
    
    # Review run
    response = client.post(f"/api/runs/{run_id}/review", data={"action": "approve"})
    assert response.status_code in (202, 400, 409)
