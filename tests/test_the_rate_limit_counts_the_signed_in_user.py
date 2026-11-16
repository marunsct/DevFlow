"""The request budget counts the signed-in user, and a made-up token counts as its address (LR.39).

Found in the launch review: the bucket was a per-process `hash()` of the unverified header, so a fresh random bearer
string per request got a fresh bucket each time, and each worker process counted apart.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from app.server import rate_limit


def _request(auth="", host="203.0.113.9"):
    return SimpleNamespace(headers={"Authorization": auth} if auth else {}, client=SimpleNamespace(host=host))


def test_a_verified_token_is_its_user_and_made_up_ones_share_the_address():
    with mock.patch("app.server.auth._decode", side_effect=lambda token: "alice" if token == "good" else None):
        assert rate_limit.client_identity(_request("Bearer good")) == "user:alice"
        assert rate_limit.client_identity(_request("Bearer random-1")) == "ip:203.0.113.9"
        assert rate_limit.client_identity(_request("Bearer random-2")) == "ip:203.0.113.9"
