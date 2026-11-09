"""The harness's own Redis needs a password, and the setup script generates one.

Product commands run in the worker, on the network that reaches `redis:6379` by name, and that Redis - the queue
every run's stages are dispatched through - answered anyone with no password at all.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _compose() -> dict:
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text())


def test_compose_redis_needs_a_password():
    compose = _compose()
    redis = compose["services"]["redis"]
    command = " ".join(redis["command"])
    assert "--requirepass ${REDIS_PASSWORD:?" in command, "fails closed when unset"
    assert redis["environment"]["REDISCLI_AUTH"].startswith("${REDIS_PASSWORD:?"), "the healthcheck authenticates"
    url = compose["x-app-env"]["REDIS_URL"]
    assert url.startswith("redis://:${REDIS_PASSWORD:?") and url.endswith("@redis:6379/0")
    for name in ("app", "worker"):
        environment = compose["services"][name]["environment"]
        assert environment["REDIS_URL"] == url, name


def test_setup_env_generates_a_redis_password(tmp_path):
    env = tmp_path / ".env"
    subprocess.run(["bash", str(ROOT / "scripts" / "setup-env.sh"), str(env)], check=True, capture_output=True)
    value = next(line.split("=", 1)[1] for line in env.read_text().splitlines() if line.startswith("REDIS_PASSWORD="))
    assert len(value) >= 24 and all(c.isalnum() or c in "-_" for c in value), "URL-safe, so it sits in REDIS_URL as is"
    subprocess.run(["bash", str(ROOT / "scripts" / "setup-env.sh"), str(env)], check=True, capture_output=True)
    again = next(line.split("=", 1)[1] for line in env.read_text().splitlines() if line.startswith("REDIS_PASSWORD="))
    assert again == value, "a second run keeps it"


def test_the_password_never_reaches_a_product_command(monkeypatch, tmp_path):
    from app.tools.sandbox import product_environment

    monkeypatch.setenv("REDIS_URL", "redis://:sentinel-pass@redis:6379/0")
    monkeypatch.setenv("REDIS_PASSWORD", "sentinel-pass")
    assert "sentinel-pass" not in " ".join(product_environment(str(tmp_path)).values())


# Found while adding the Redis password to a live `.env`: on an existing deployment with no
# SETTINGS_ENCRYPTION_KEY, the "safe to re-run" setup script minted one, and every stored provider credential -
# encrypted with the key derived from JWT_SECRET_KEY - would have been unreadable at the next restart.
def test_setup_env_never_mints_an_encryption_key_for_an_existing_deployment(tmp_path):
    env = tmp_path / ".env"
    env.write_text("JWT_SECRET_KEY=existing-secret\n")
    subprocess.run(["bash", str(ROOT / "scripts" / "setup-env.sh"), str(env)], check=True, capture_output=True)
    keys = {line.split("=", 1)[0] for line in env.read_text().splitlines() if "=" in line}
    assert "SETTINGS_ENCRYPTION_KEY" not in keys and "REDIS_PASSWORD" in keys
    assert "JWT_SECRET_KEY=existing-secret" in env.read_text()


def test_setup_env_mints_one_on_a_fresh_file(tmp_path):
    env = tmp_path / ".env"
    subprocess.run(["bash", str(ROOT / "scripts" / "setup-env.sh"), str(env)], check=True, capture_output=True)
    assert any(line.startswith("SETTINGS_ENCRYPTION_KEY=") and len(line) > 40 for line in env.read_text().splitlines())
