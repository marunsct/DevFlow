"""Outside development the server serves no API pages or unguarded metrics, and refuses published secrets (LR.11).

Found in the launch review: `/docs`, `/openapi.json` and `/metrics` (with no scrape token) were served to anyone who
could reach the server, and the repository's development overlay holds a literal signing key and first password,
which a deployment started with it would have used.
"""
from __future__ import annotations

import pytest


def _routes(monkeypatch, env, token=""):
    monkeypatch.setenv("ENV", env)
    monkeypatch.setenv("METRICS_SCRAPE_TOKEN", token)
    from app.server.api import create_app

    return {getattr(route, "path", "") for route in create_app().routes}


def test_production_serves_no_api_pages_and_no_unguarded_metrics(monkeypatch, setup_db):
    routes = _routes(monkeypatch, "production")
    assert not {"/docs", "/openapi.json", "/redoc", "/metrics"} & routes
    assert "/metrics" in _routes(monkeypatch, "production", token="t" * 32)


def test_development_keeps_them(monkeypatch, setup_db):
    routes = _routes(monkeypatch, "development")
    assert {"/docs", "/openapi.json", "/metrics"} <= routes


def test_a_published_signing_key_is_refused_outside_development(monkeypatch):
    from app.server import auth

    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "dev-only-secret-not-for-production-use-32")
    with pytest.raises(ValueError, match="published development value"):
        auth._load_secret_key()
    monkeypatch.setenv("ENV", "development")
    assert auth._load_secret_key() == "dev-only-secret-not-for-production-use-32"
