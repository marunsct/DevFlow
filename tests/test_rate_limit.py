"""Rate limiting: caller identity, the request budget, and login throttling."""

import pytest
from starlette.datastructures import Headers


class _FakeRequest:
    """Minimal stand-in with the attributes the limiter reads."""

    def __init__(self, path="/api/runs", headers=None, peer="10.0.0.5"):
        self.headers = Headers(headers or {})
        self.client = type("C", (), {"host": peer})()
        self.url = type("U", (), {"path": path})()


@pytest.fixture(autouse=True)
def fresh_redis(redis_container):
    from app.server.redis_client import reset_clients

    reset_clients()
    client = None
    try:
        from app.server.redis_client import get_redis_client

        client = get_redis_client()
        client.flushdb()
    except Exception:
        pass
    yield
    if client is not None:
        client.flushdb()


# ---------------------------------------------------------------------------
# Caller identity
# ---------------------------------------------------------------------------


def test_an_authenticated_caller_is_keyed_by_token(monkeypatch):
    """Keying on IP alone puts everyone behind a NAT in one shared bucket."""
    from app.server.rate_limit import client_identity

    identity = client_identity(_FakeRequest(headers={"Authorization": "Bearer abc.def.ghi"}))
    assert identity.startswith("tok:")


def test_forwarded_headers_are_ignored_from_an_untrusted_peer(monkeypatch):
    """Otherwise any client could forge X-Forwarded-For and evade the limit."""
    monkeypatch.setattr("app.server.rate_limit._TRUSTED", [])
    from app.server.rate_limit import client_identity

    identity = client_identity(
        _FakeRequest(headers={"X-Forwarded-For": "1.2.3.4"}, peer="10.0.0.5")
    )
    assert identity == "ip:10.0.0.5"


def test_forwarded_headers_are_honoured_from_a_trusted_proxy(monkeypatch):
    import ipaddress

    monkeypatch.setattr(
        "app.server.rate_limit._TRUSTED", [ipaddress.ip_network("10.0.0.0/8")]
    )
    from app.server.rate_limit import client_identity

    identity = client_identity(
        _FakeRequest(headers={"X-Forwarded-For": "1.2.3.4, 10.0.0.1"}, peer="10.0.0.5")
    )
    assert identity == "ip:1.2.3.4"


# ---------------------------------------------------------------------------
# Request budget
# ---------------------------------------------------------------------------


async def test_requests_are_allowed_under_the_budget():
    from app.server.rate_limit import enforce_request_budget

    assert await enforce_request_budget(_FakeRequest()) is True


async def test_the_budget_is_enforced(monkeypatch):
    monkeypatch.setattr("app.server.rate_limit.RATE_LIMIT_MAX_REQUESTS", 3)
    from app.server import rate_limit

    monkeypatch.setattr(rate_limit, "RATE_LIMIT_MAX_REQUESTS", 3)

    request = _FakeRequest(peer="203.0.113.9")
    results = [await rate_limit.enforce_request_budget(request) for _ in range(5)]
    assert results[:3] == [True, True, True]
    assert results[-1] is False


async def test_health_and_metrics_are_exempt(monkeypatch):
    """Probes fire far more often than user traffic and must not consume it."""
    from app.server import rate_limit

    monkeypatch.setattr(rate_limit, "RATE_LIMIT_MAX_REQUESTS", 1)
    request = _FakeRequest(path="/api/health/ready")
    for _ in range(10):
        assert await rate_limit.enforce_request_budget(request) is True


async def test_the_budget_fails_open_when_redis_is_unreachable(monkeypatch):
    """Losing Redis must not lock every user out of a working system."""
    from app.server import rate_limit

    def _boom():
        raise ConnectionError("redis down")

    monkeypatch.setattr("app.server.redis_client.get_async_redis_client", _boom)
    assert await rate_limit.enforce_request_budget(_FakeRequest()) is True


# ---------------------------------------------------------------------------
# Login throttling
# ---------------------------------------------------------------------------


def test_login_attempts_are_allowed_initially():
    from app.server.rate_limit import check_login_attempt

    assert check_login_attempt("alice", "203.0.113.1") is True


def test_repeated_failures_lock_the_account_out(monkeypatch):
    from app.server import rate_limit

    monkeypatch.setattr(rate_limit, "LOGIN_MAX_ATTEMPTS", 3)
    for _ in range(3):
        rate_limit.register_failed_login("mallory", "203.0.113.2")

    assert rate_limit.check_login_attempt("mallory", "203.0.113.2") is False


def test_a_successful_login_clears_the_counter(monkeypatch):
    from app.server import rate_limit

    monkeypatch.setattr(rate_limit, "LOGIN_MAX_ATTEMPTS", 2)
    rate_limit.register_failed_login("bob", "203.0.113.3")
    rate_limit.register_failed_login("bob", "203.0.113.3")
    assert rate_limit.check_login_attempt("bob", "203.0.113.3") is False

    rate_limit.clear_login_attempts("bob", "203.0.113.3")
    assert rate_limit.check_login_attempt("bob", "203.0.113.3") is True


def test_login_throttling_falls_back_to_in_process_counters(monkeypatch):
    """Unlike the request budget, this must not fail open - losing Redis would
    otherwise switch brute-force protection off entirely."""
    from app.server import rate_limit

    monkeypatch.setattr(rate_limit, "LOGIN_MAX_ATTEMPTS", 2)

    def _boom():
        raise ConnectionError("redis down")

    monkeypatch.setattr("app.server.redis_client.get_redis_client", _boom)

    rate_limit.register_failed_login("carol", "203.0.113.4")
    rate_limit.register_failed_login("carol", "203.0.113.4")
    assert rate_limit.check_login_attempt("carol", "203.0.113.4") is False
