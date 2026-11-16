"""Production runs behind a TLS proxy in production mode, from a file of its own beside the development one (LR.11).

Found in the launch review: the app was published over plain HTTP on every interface and the deployed stack ran with
ENV=development, which relaxes the secret checks and serves the API pages.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_the_production_file_sets_production_mode_and_publishes_only_the_proxy():
    prod = (ROOT / "docker-compose.prod.yml").read_text()
    assert "ENV: production" in prod and "ports: !reset []" in prod
    assert '"443:443"' in prod and "./deploy/Caddyfile:/etc/caddy/Caddyfile:ro" in prod
    caddy = (ROOT / "deploy" / "Caddyfile").read_text()
    assert "reverse_proxy app:8000" in caddy and "Strict-Transport-Security" in caddy


@pytest.mark.skipif(shutil.which("docker") is None, reason="needs docker compose to read the files")
def test_compose_reads_the_two_files_together(tmp_path):
    done = subprocess.run(["docker", "compose", "-f", "docker-compose.yml", "-f", "docker-compose.prod.yml", "config"],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if done.returncode != 0 and "env file" in done.stderr:
        pytest.skip("no .env here")
    assert done.returncode == 0, done.stderr[-500:]
    assert 'published: "8000"' not in done.stdout and 'published: "443"' in done.stdout


def test_this_machine_s_additions_stay_out_of_git():
    assert "docker-compose.override.yml" in (ROOT / ".gitignore").read_text()
