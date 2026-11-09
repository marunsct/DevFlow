"""What the product or its suites wrote never runs with the worker's secrets.

Every sandbox command gets a few names (`sandbox._child_environment`), but the start probe ran the product's
`start.sh`, and the suite's dry run its spec files, with the worker's whole environment: its database password,
signing key and model credentials, readable by model-written code.
"""
from __future__ import annotations

import shutil

import pytest

SENTINEL = "worker-secret-sentinel-0x5eed"


@pytest.fixture
def secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", SENTINEL)
    monkeypatch.setenv("POSTGRES_PASSWORD", SENTINEL)
    return SENTINEL


@pytest.mark.skipif(shutil.which("node") is None, reason="no Node here")
def test_the_start_probe_runs_the_product_without_them(tmp_path, monkeypatch, secret):
    from app.acceptance import start_probe
    from app.stacks import contract, pack_named

    pack = pack_named("node-hono-native-api")
    contract.write(tmp_path, pack, "notes", "Notes")
    project = tmp_path / "notes"
    project.mkdir()
    (project / "playwright.config.js").write_text(pack.render("notes", "Notes", None)["playwright.config.js"])
    (project / "start.sh").write_text('#!/bin/sh\ncd "$(dirname "$0")" && exec node server.cjs\n')

    monkeypatch.setenv("START_PROBE", "on")
    tells = ("console.log('saw:' + process.env.JWT_SECRET_KEY + ' ' + process.env.POSTGRES_PASSWORD); "
             "console.log('port:' + process.env.PORT + ' data:' + (process.env.DATA_DIR ? 'set' : 'unset')); process.exit(1);\n")
    (project / "server.cjs").write_text(tells)
    text = start_probe.what_the_start_shows(tmp_path)
    assert "exited with code 1" in text and "data:set" in text
    assert secret not in text and "saw:undefined undefined" in text


@pytest.mark.skipif(shutil.which("node") is None, reason="no Node here")
def test_the_spec_dry_run_runs_the_suite_without_them(tmp_path, monkeypatch, secret):
    import subprocess

    from app.acceptance import spec_dry_run

    seen: list = []
    real = subprocess.run

    def capture(*args, **kwargs):
        seen.append(kwargs.get("env"))
        return real(*args, **kwargs)

    monkeypatch.setattr(spec_dry_run.subprocess, "run", capture)
    (tmp_path / "a.spec.js").write_text("const { test } = require('@playwright/test');\ntest('x', async () => {});\n")
    spec_dry_run.run(tmp_path)
    assert seen, "the dry run ran"
    assert all(env is not None and secret not in env.values() for env in seen)
    assert all("JWT_SECRET_KEY" not in env and "POSTGRES_PASSWORD" not in env for env in seen)
