"""The loop's repo guards: the owner's compose hunk is never committed, and the operator login is found by its mark.

The owner keeps an uncommitted `127.0.0.1:5433:5432` database port in docker-compose.yml, and every commit that
touched the file had to be staged by hand around it - one mistake commits it. And ship-live read the operator login
as line 65 of the handover: a line added above it fed `eval` the wrong line.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = "services:\n  db:\n    image: postgres:15-alpine\n"


def _repo(tmp_path: Path) -> Path:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}
    for argv in (["git", "init", "-q"], ["git", "config", "user.email", "t@example.com"], ["git", "config", "user.name", "t"]):
        subprocess.run(argv, cwd=tmp_path, check=True, env=env)
    (tmp_path / "docker-compose.yml").write_text(COMPOSE)
    subprocess.run(["git", "add", "docker-compose.yml"], cwd=tmp_path, check=True, env=env)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=tmp_path, check=True, env=env)
    return tmp_path


def _guard(repo: Path) -> int:
    return subprocess.run(["bash", str(ROOT / "scripts/loop/guard_staged.sh")], cwd=repo, capture_output=True).returncode


def test_the_commit_guard_refuses_the_owner_port_hunk(tmp_path):
    repo = _repo(tmp_path)
    (repo / "docker-compose.yml").write_text(COMPOSE + '    ports:\n      - "127.0.0.1:5433:5432"\n')
    subprocess.run(["git", "add", "docker-compose.yml"], cwd=repo, check=True)
    assert _guard(repo) == 1


def test_the_commit_guard_lets_other_compose_changes_through(tmp_path):
    repo = _repo(tmp_path)
    (repo / "docker-compose.yml").write_text(COMPOSE.replace("15-alpine", "16-alpine"))
    subprocess.run(["git", "add", "docker-compose.yml"], cwd=repo, check=True)
    assert _guard(repo) == 0
    assert (ROOT / ".githooks/pre-commit").read_text().count("guard_staged.sh") == 1


def test_ship_live_finds_the_login_after_lines_are_inserted(tmp_path):
    handover = tmp_path / "HANDOVER.md"
    handover.write_text("\n".join(["filler"] * 70) + "\nexport LOOP_USER=u LOOP_PASSWORD=p   # operator-login\n")
    found = subprocess.run(["bash", str(ROOT / "scripts/loop/operator_login.sh")], capture_output=True, text=True,
                           env={**os.environ, "HANDOVER_FILE": str(handover)}).stdout.strip()
    assert found.startswith("export LOOP_USER=u ")
    assert 'scripts/loop/operator_login.sh' in (ROOT / "scripts/loop/ship_live.sh").read_text()
    assert "sed -n 65p" not in (ROOT / "scripts/loop/ship_live.sh").read_text()


def test_the_handover_marks_exactly_one_login_line():
    lines = [line for line in (ROOT / "docs/HANDOVER.md").read_text().splitlines() if line.endswith("# operator-login")]
    assert len(lines) == 1


def test_compose_names_no_run_id():
    import re

    assert not re.search(r"\brun-[0-9a-f]{8}\b", (ROOT / "docker-compose.yml").read_text())
