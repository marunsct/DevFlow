"""A viewer reads runs; it never steers one or reads the model settings.

Found in the launch review: the steering route took any signed-in user, so a read-only account could give a run a
direction its next model calls carried, and nothing recorded who did; the settings view (model addresses, the last
characters of keys) was open to viewers too.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def as_viewer(setup_db):
    from app.server.api import create_app
    from app.server.auth import UserInDB, get_current_active_user

    app = create_app()

    async def viewer():
        return UserInDB(username="reader", hashed_password="x", disabled=False, role="viewer", tenant_id="default")

    app.dependency_overrides[get_current_active_user] = viewer
    with TestClient(app) as client:
        yield client


def test_a_viewer_cannot_steer_a_run(as_viewer):
    answer = as_viewer.post("/api/runs/run-x/steering", json={"text": "use another database"})
    assert answer.status_code == 403


def test_a_viewer_cannot_read_the_model_settings(as_viewer):
    assert as_viewer.get("/api/settings").status_code == 403
