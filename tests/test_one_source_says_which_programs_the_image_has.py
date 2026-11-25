"""Every text that says which programs exist reads the image the commands run in (deep review 2026-11-25, item 5).

Measured on one request of a Python pack run: the environment contract listed pnpm, poetry, ruff and uv as available
(none is in the image), the stack note said make and yarn were not installed (both are), and a refusal said cargo and
go were installed (neither is) - the first was the allowlist, the other two were measured on the worker. The image's
answer below is the real `which` output of that pack's image (`tests/captured/python_pack_image_which.txt`); the pack
record is that run's.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agents.environment_contract import the_environment_contract
from app.agents.specialists import describe_stack
from app.tools import image_programs, sandbox
from app.tools.sandbox import CommandNotAllowed, validate_command

CAPTURED = Path(__file__).parent / "captured"
WHICH = (CAPTURED / "python_pack_image_which.txt").read_text()
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
STACK = SimpleNamespace(language="Python", framework="FastAPI", frontend_framework="React on Vite",
                        database="PostgreSQL", testing_framework="pytest", additional_tools=())


class _Docker:
    """The container runtime: answers `which` as the image did, and records each container started."""

    def __init__(self):
        self.started: list[list[str]] = []

    def __call__(self, argv, **_):
        self.started.append(list(argv))
        return subprocess.CompletedProcess(argv, 1, WHICH, "")


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    (tmp_path / ".harness").mkdir()
    shutil.copy(CAPTURED / "fullstack_fastapi_stack_pack.json", tmp_path / ".harness" / "stack-pack.json")
    (tmp_path / ".project-stack").write_text("javascript\npython\ntypescript\n", encoding="utf-8")
    (tmp_path / ".project-directory").write_text("task-management-dashboard\n", encoding="utf-8")
    (tmp_path / "task-management-dashboard").mkdir()
    monkeypatch.setenv("SANDBOX_EXECUTION_MODE", "container")
    monkeypatch.setenv("ALLOW_COMMAND_EXECUTION", "true")
    monkeypatch.setattr(sandbox, "_docker_binary", lambda: "docker")
    docker = _Docker()
    monkeypatch.setattr(image_programs.subprocess, "run", docker)
    return tmp_path, docker


def _refusal(command: list[str], root: Path) -> str:
    with pytest.raises(CommandNotAllowed) as refused:
        validate_command(command, "backend_specialist", root)
    return str(refused.value)


def test_the_contract_the_stack_note_and_a_refusal_agree_with_the_image(workspace):
    root, docker = workspace

    contract = the_environment_contract(root)
    note = describe_stack(STACK, str(root))
    refusal = _refusal(["sh", "build.sh"], root)

    available = contract[contract.index("- Available commands:"):].split("\n", 1)[0]
    assert re.search(r"\byarn\b", available) and re.search(r"\bnode\b", available)
    for absent in ("pnpm", "poetry", "ruff", "uv"):
        assert not re.search(rf"\b{absent}\b", available)
    assert "`make`" not in note and "`yarn`" not in note and "`pnpm` is not installed" in note
    installed = refusal[refusal.index("Allowed and installed:"):refusal.index("Also allowed but NOT installed")]
    assert not re.search(r"\b(?:cargo|go)\b", installed)
    assert not BANNED.search(contract[contract.index("- Allowed, but not in the image"):].split("\n", 1)[0])
    # One container asked the image, for all three.
    assert len(docker.started) == 1
    assert "harness-sandbox-python:pw1.64.0" in docker.started[0] and "which" in docker.started[0]


def test_the_image_is_asked_once_and_kept(workspace):
    root, docker = workspace

    image_programs.ensure(root)
    image_programs.ensure(root)

    kept = json.loads((root / image_programs.RECORD).read_text())
    assert kept["image"] == "harness-sandbox-python:pw1.64.0"
    assert {"make", "yarn", "node", "python3"} <= set(kept["present"])
    assert not {"pnpm", "poetry", "uv", "ruff", "cargo", "go"} & set(kept["present"])
    assert len(docker.started) == 1


def test_without_command_execution_nothing_is_started_and_the_worker_is_asked(workspace, monkeypatch):
    root, docker = workspace
    monkeypatch.setenv("ALLOW_COMMAND_EXECUTION", "false")

    assert image_programs.split(root, ["make"]) is None
    assert docker.started == []
