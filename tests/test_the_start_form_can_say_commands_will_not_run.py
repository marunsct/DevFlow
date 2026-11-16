"""The start form can say, before a run is refused for it, that the workers cannot run commands (LR.32).

Found in the launch review: command execution is off by default, and a new user learned it only from a refusal at
start that named environment variables.
"""
from __future__ import annotations

import json
from unittest import mock


class _Redis:
    def __init__(self, value):
        self.value = value

    async def get(self, key):
        return self.value


def test_the_workers_readiness_is_said(client):
    refusal = json.dumps({"ready": False, "detail": "ALLOW_COMMAND_EXECUTION is off"})
    with mock.patch("app.server.redis_client.get_async_redis_client", return_value=_Redis(refusal)):
        assert client.get("/api/health/commands").json() == {"ready": False, "reason": "ALLOW_COMMAND_EXECUTION is off"}
    with mock.patch("app.server.redis_client.get_async_redis_client", return_value=_Redis(json.dumps({"ready": True}))):
        assert client.get("/api/health/commands").json() == {"ready": True, "reason": ""}
