import pytest
from pathlib import Path

# `client` comes from conftest.

def test_e2e_multi_file_upload_and_custom_dir(client, tmp_path: Path):
    file1 = tmp_path / "doc1.txt"
    file1.write_text("Product Requirements Document")
    file2 = tmp_path / "doc2.txt"
    file2.write_text("Technical context")
    
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
    
    # The workspace is server-allocated now; the request may only label it.
    response = client.post(
        f"/api/runs/{run_id}/start",
        json={
            "workspace_label": "e2e-artifacts",
            "allow_subdirectories": True,
            "reviewer": "Test Reviewer",
        },
    )
    assert response.status_code == 202, response.text
    
    status_response = client.get(f"/api/runs/{run_id}")
    assert status_response.status_code == 200, status_response.text

def test_e2e_review_with_edited_content(client, tmp_path: Path):
    run_id = "non-existent-run-id"
    file_content = b"Modified content"
    
    response = client.post(
        f"/api/runs/{run_id}/review",
        data={"action": "changes"},
        files={"file": ("edited_spec.md", file_content, "text/markdown")}
    )
    assert response.status_code == 404, response.text
