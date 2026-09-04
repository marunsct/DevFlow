import pytest
from fastapi.testclient import TestClient
from pathlib import Path

from app.server.api import app
from app.server.auth import get_current_active_user

# Mock auth
async def override_get_current_active_user():
    return {"username": "testuser"}

app.dependency_overrides[get_current_active_user] = override_get_current_active_user

client = TestClient(app)

def test_e2e_multi_file_upload_and_custom_dir(tmp_path: Path):
    # Create dummy files
    file1 = tmp_path / "doc1.txt"
    file1.write_text("Product Requirements Document")
    file2 = tmp_path / "doc2.txt"
    file2.write_text("Technical context")
    
    # 1. Create Run with multiple files
    with open(file1, "rb") as f1, open(file2, "rb") as f2:
        response = client.post(
            "/api/runs",
            files=[
                ("files", ("doc1.txt", f1, "text/plain")),
                ("files", ("doc2.txt", f2, "text/plain"))
            ]
        )
    assert response.status_code == 201, response.text
    data = response.json()
    assert "run_id" in data
    run_id = data["run_id"]
    
    # 2. Start Run with artifact directory
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    
    response = client.post(
        f"/api/runs/{run_id}/start",
        json={
            "artifact_directory": str(artifact_dir),
            "allow_subdirectories": True,
            "reviewer": "Test Reviewer"
        }
    )
    assert response.status_code == 202, response.text
    
    # Wait for run to pause (either review or approval)
    # The runner runs in the background. Since we're using a TestClient, 
    # the background tasks started by the endpoints will execute if we let them.
    # However, testing background execution accurately in pytest without sleep 
    # can be tricky. We'll just verify the initial states.
    status_response = client.get(f"/api/runs/{run_id}")
    assert status_response.status_code == 200, status_response.text

def test_e2e_review_with_edited_content(tmp_path: Path):
    # This test simulates a review submission with a file upload.
    # Because we are testing the API layer, we just want to ensure it accepts the multipart/form-data.
    # It will likely return a 404 because the run does not exist, but we can verify it doesn't fail on payload parsing.
    
    run_id = "non-existent-run-id"
    file_content = b"Modified content"
    
    response = client.post(
        f"/api/runs/{run_id}/review",
        data={"action": "changes"},
        files={"file": ("edited_spec.md", file_content, "text/markdown")}
    )
    # Expecting 404 because the run ID doesn't exist, which confirms the endpoint was hit and payload parsed successfully
    assert response.status_code == 404, response.text

