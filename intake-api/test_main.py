import os
import pytest
from fastapi.testclient import TestClient
from main import app, INTAKE_DIR

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_and_teardown():
    os.makedirs(INTAKE_DIR, exist_ok=True)
    yield
    # Cleanup files created during tests
    for file in os.listdir(INTAKE_DIR):
        os.remove(os.path.join(INTAKE_DIR, file))


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_intake_missing_fields():
    response = client.post("/intakes", json={"title": "Missing ID and Content"})
    assert response.status_code == 422


def test_create_intake_success():
    payload = {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "title": "Test Intake",
        "content": "This is a test intake.",
        "metadata": {"source": "test"}
    }
    response = client.post("/intakes", json=payload)
    assert response.status_code == 201
    assert response.json() == {"id": payload["id"], "message": "Intake created successfully"}
    
    # Verify file exists
    assert os.path.exists(os.path.join(INTAKE_DIR, f"{payload['id']}.md"))
    assert os.path.exists(os.path.join(INTAKE_DIR, f"{payload['id']}_meta.json"))


def test_create_intake_idempotency():
    payload = {
        "id": "223e4567-e89b-12d3-a456-426614174001",
        "title": "Idempotent Intake",
        "content": "Testing idempotency."
    }
    # First request
    response1 = client.post("/intakes", json=payload)
    assert response1.status_code == 201
    
    # Second request
    response2 = client.post("/intakes", json=payload)
    assert response2.status_code == 200
    assert response2.json() == {"id": payload["id"], "message": "Intake already exists"}


def test_get_intake_markdown():
    payload = {
        "id": "323e4567-e89b-12d3-a456-426614174002",
        "title": "Markdown Intake",
        "content": "Markdown content here."
    }
    client.post("/intakes", json=payload)
    
    response = client.get(f"/intakes/{payload['id']}", headers={"Accept": "text/markdown"})
    assert response.status_code == 200
    assert response.text == f"# {payload['title']}\n\n{payload['content']}"


def test_get_intake_json():
    payload = {
        "id": "423e4567-e89b-12d3-a456-426614174003",
        "title": "JSON Intake",
        "content": "JSON content here.",
        "metadata": {"key": "value"}
    }
    client.post("/intakes", json=payload)
    
    response = client.get(f"/intakes/{payload['id']}", headers={"Accept": "application/json"})
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == payload["id"]
    assert data["title"] == payload["title"]
    assert data["content"] == payload["content"]
    assert data["metadata"] == payload["metadata"]


def test_auth_rejection(monkeypatch):
    monkeypatch.setenv("INTAKE_API_KEY", "supersecret")
    
    payload = {
        "id": "523e4567-e89b-12d3-a456-426614174004",
        "title": "Auth Intake",
        "content": "Auth content."
    }
    # No auth header
    response = client.post("/intakes", json=payload)
    assert response.status_code == 401
    
    # Bad auth header
    response = client.post("/intakes", json=payload, headers={"X-API-KEY": "wrong"})
    assert response.status_code == 401
    
    # Good auth header
    response = client.post("/intakes", json=payload, headers={"X-API-KEY": "supersecret"})
    assert response.status_code == 201
