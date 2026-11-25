"""`read_docs` reads a package from the registry of the run's own stack, and the architect is told to use it only
where it is offered (deep review of silent mechanisms, 2026-11-25).

Measured: `read_docs` was called three times in 30 runs, all by the architect of a Java Spring Boot run, and twice
answered from the README of an unrelated Rust crate named `spring-boot`, labelled as the project's own documentation:
with no ecosystem given it tried npm, PyPI and crates.io in turn. And 62 of 68 architect requests told the model to read
with `read_docs` while offering no such tool.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

from app.tools import docs

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
JAVA_STACK = Path(__file__).parent / "captured" / "technology-stack-java-spring.md"


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setattr(docs, "_CACHE", {})
    monkeypatch.setenv("DOCS_LOOKUP_ENABLED", "true")


def _a_java_run(root: Path) -> Path:
    (root / "docs").mkdir()
    shutil.copy(JAVA_STACK, root / "docs" / "technology_stack.md")
    return root


def _registries(asked: list[str]):
    """Every registry, at the edge: records each address asked and answers a README for any package."""
    def fetch(url):
        asked.append(url)
        if "crates.io/api/v1/crates/spring-boot" in url and url.endswith("/readme"):
            return 200, "# spring-boot\nA Rust crate that boots a spring.\n", "text/markdown"
        if "crates.io/api/v1/crates/spring-boot" in url:
            return 200, json.dumps({"crate": {"max_stable_version": "0.1.0"}}), "application/json"
        return 404, "", "text/html"

    return fetch


def test_the_java_run_s_question_is_not_answered_from_another_registry(tmp_path, monkeypatch):
    """The architect's own call, as it was made: no ecosystem, a Maven library's name."""
    asked: list[str] = []
    monkeypatch.setattr(docs, "_fetch", _registries(asked))
    tool = docs.build_docs_tool(_a_java_run(tmp_path))

    answer = tool.invoke({"name": "spring-boot", "topic": "JdbcTemplate query update methods"})

    assert asked == [], "no registry of another stack is asked"
    assert "maven" in answer["error"] and "spring-boot" in answer["error"]
    assert not BANNED.search(answer["error"])


def test_a_package_of_the_run_s_own_registry_is_read_from_it_alone(tmp_path):
    asked: list[str] = []
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "technology_stack.md").write_text(
        JAVA_STACK.read_text(encoding="utf-8").replace("- **Language:** Java", "- **Language:** TypeScript"))

    docs.read("spring-boot", "routes", fetch=_registries(asked), run_ecosystem=docs.the_run_s_ecosystem(tmp_path))

    assert asked and all("npm" in url or "jsdelivr" in url for url in asked), asked


def test_an_ecosystem_named_in_the_call_is_read_as_asked(tmp_path, monkeypatch):
    asked: list[str] = []
    monkeypatch.setattr(docs, "_fetch", _registries(asked))

    answer = docs.build_docs_tool(_a_java_run(tmp_path)).invoke(
        {"name": "spring-boot", "topic": "boot", "ecosystem": "crates"})

    assert "A Rust crate" in answer["excerpt"]


def test_before_a_stack_is_chosen_every_registry_is_tried_as_before(tmp_path):
    assert docs.the_run_s_ecosystem(tmp_path) == ""


def _first_request(researched: bool, root: Path):
    from app.agents.principal_architect import create_principal_architect_agent
    from tests.a_role_agent import Scripted, Stopped

    model = Scripted(replies=[], requests=[], offered=[])
    agent = create_principal_architect_agent(model=model, repo_root=str(root), researched=researched)
    try:
        agent.invoke({"messages": [{"role": "user", "content": "go"}]}, {"configurable": {"thread_id": "t"}})
    except Stopped:
        pass
    system = next(str(m.content) for m in model.requests[0] if getattr(m, "type", "") == "system")
    return system, model.offered[0]


def test_the_architect_offered_read_docs_is_told_to_read_with_it(tmp_path, monkeypatch):
    monkeypatch.setattr("app.plugins.middleware.get_plugin_instructions", lambda keys, role: "")

    system, offered = _first_request(False, tmp_path)

    assert "read_docs" in offered and "`read_docs`" in system


def test_the_architect_whose_reading_was_done_is_told_of_no_tool_it_lacks(tmp_path, monkeypatch):
    from app.agents.principal_architect import READ_FROM_THE_NOTES

    monkeypatch.setattr("app.plugins.middleware.get_plugin_instructions", lambda keys, role: "")
    from app.tools.research import researched

    with researched(True):
        system, offered = _first_request(True, tmp_path)

    assert "read_docs" not in offered and "read_docs" not in system
    assert READ_FROM_THE_NOTES in system and not BANNED.search(READ_FROM_THE_NOTES)


def test_the_specification_s_schema_names_no_tool():
    """Its field descriptions are sent with every request that writes it, the parts written with no tools at all."""
    from app.agents.principal_architect import TechnicalSpecificationOutput

    assert "read_docs" not in json.dumps(TechnicalSpecificationOutput.model_json_schema())
