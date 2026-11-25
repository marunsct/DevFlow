"""The stack block a builder reads follows the specification's choices and the installed versions (deep review
2026-11-25, item 3).

Measured on one medium run: every builder's and fixer's request said "Other tools: ... python-jose (JWT), passlib
(password hashing) ... Build on exactly this" after the specification had decided PyJWT and bcrypt; a builder installed
python-jose and a later one removed it. The same requests gave "Library: PyJWT 1.4.0" beside "Versions here: pyjwt
2.15.1". The fixture is that run's stack, specification and stack facts
(`tests/captured/medium_stack_specification_and_installed.json`).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agents.specialists import describe_stack, specification_for_the_work_order

CAPTURED = json.loads((Path(__file__).parent / "captured" / "medium_stack_specification_and_installed.json").read_text())
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "technical_specification.md").write_text(
        "## Library Usage\n" + "".join(f"- {entry}\n" for entry in CAPTURED["library_usage"])
        + "\n## Decisions (ADR)" + CAPTURED["decisions_section"], encoding="utf-8")
    (tmp_path / ".harness").mkdir()
    (tmp_path / ".harness" / "stack-facts.json").write_text(
        json.dumps({"dependencies": CAPTURED["dependencies"]}), encoding="utf-8")
    return tmp_path


STACK = SimpleNamespace(language="Python", framework="FastAPI", frontend_framework="React on Vite",
                        database="PostgreSQL", testing_framework="pytest",
                        additional_tools=CAPTURED["additional_tools"])


def _other_tools_line(block: str) -> str:
    return next(line for line in block.splitlines() if line.startswith("- Other tools"))


def test_a_tool_the_specification_replaced_is_not_handed_on_as_decided(workspace):
    line = _other_tools_line(describe_stack(STACK, str(workspace)))

    kept, _, replaced = line.partition("Not used")
    assert "python-jose" not in kept and "passlib" not in kept
    assert "python-jose" in replaced and "passlib" in replaced
    assert "SQLAlchemy" in kept and "Alembic" in kept and "httpx" in kept
    assert "the specification decides the libraries" in line
    assert not BANNED.search(line)


def test_before_the_specification_every_tool_is_named_and_said_to_be_the_specification_s_to_decide(tmp_path):
    line = _other_tools_line(describe_stack(STACK, str(tmp_path)))

    assert all(tool in line for tool in CAPTURED["additional_tools"])
    assert "the specification decides the libraries" in line


def test_a_library_call_s_version_is_the_installed_one(workspace):
    specification = SimpleNamespace(library_usage=CAPTURED["library_usage"])

    detail = specification_for_the_work_order(
        specification, SimpleNamespace(files=["task-management-dashboard/app/auth.py"], interfaces=[]), workspace)

    assert "PyJWT 2.15.1" in detail and "PyJWT 1.4.0" not in detail
    assert "the specification wrote 1.4.0" in detail
    assert "fastapi 0.165.0." in detail
    assert "as their documentation gives them" not in detail
    assert not BANNED.search(detail[detail.index("Library calls"):detail.index("Library calls") + 120])
