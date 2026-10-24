"""A proven setup is found by language, framework and unit runner, not by the selector's exact wording.

Measured: the library held three Python entries and a Hono one, each keyed by the words one run's stack selector
happened to use, and the next run's different wording matched none of them - a Hono and Vitest setup proven on
2026-10-19 sat unused while a later run spent ninety minutes setting the same stack up from nothing.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.stacks import custom_setup


@pytest.fixture(autouse=True)
def _library(tmp_path, monkeypatch):
    monkeypatch.setenv("PROVEN_SETUP_LIBRARY", str(tmp_path / "library"))
    (tmp_path / "library").mkdir()
    return tmp_path


def _stack(language, framework, testing):
    return SimpleNamespace(language=language, framework=framework, frontend_framework="", testing_framework=testing)


def _keep(directory: Path, name: str, marker: str) -> Path:
    path = directory / "library" / f"{name}.json"
    path.write_text(json.dumps({"declaration": '{"kind": "http_api"}', "files": {"package.json": marker}}))
    return path


def test_the_key_names_what_the_stack_is():
    assert custom_setup.canonical_key(_stack("TypeScript", "Hono", "Vitest")) == "typescript|hono|vitest"
    assert custom_setup.canonical_key(_stack("TypeScript 5", "Hono (web framework)", "Vitest for unit tests, Playwright for acceptance")) \
        == "typescript|hono|vitest"
    assert custom_setup.canonical_key(_stack("Python 3", "Python standard library http.server", "unittest")) == "python|stdlib|unittest"
    assert custom_setup.canonical_key(_stack("Brainfuck", "none", "none")) == ""


def test_a_differently_worded_stack_finds_the_entry_an_earlier_run_proved(_library, tmp_path):
    # An entry written by an earlier run, under that run's own wording.
    _keep(_library, "language-typescript-framework-hono-testing-vitest-for-unit-tests-playwright-request-fixture", "earlier")
    project = tmp_path / "project"
    project.mkdir()

    written = custom_setup.replay(project, _stack("TypeScript", "Hono", "Vitest"))

    assert "package.json" in written and (project / "package.json").read_text() == "earlier"


def test_another_runner_or_framework_is_not_a_match(_library, tmp_path):
    _keep(_library, "language-typescript-framework-hono-testing-jest", "jest")
    project = tmp_path / "project"
    project.mkdir()

    assert custom_setup.replay(project, _stack("TypeScript", "Hono", "Vitest")) == []
    assert custom_setup.replay(project, _stack("TypeScript", "Express", "Jest")) == []


def test_the_exact_wording_still_wins_and_the_newest_of_equals_is_used(_library, tmp_path):
    import os, time

    older = _keep(_library, "language-typescript-framework-hono-testing-vitest-old", "old")
    time.sleep(0.01)
    _keep(_library, "language-typescript-framework-hono-testing-vitest-new", "new")
    os.utime(older, (1, 1))
    project = tmp_path / "project"
    project.mkdir()

    custom_setup.replay(project, _stack("TypeScript", "Hono", "Vitest"))

    assert (project / "package.json").read_text() == "new"


def test_an_old_entry_whose_name_lost_its_runner_still_matches_on_language_and_framework(_library, tmp_path):
    _keep(_library, "language-python-framework-python-standard-library-http-server-threadinghttpserver-basehttprequesthandler-zero-third-part", "stdlib")
    project = tmp_path / "project"
    project.mkdir()

    written = custom_setup.replay(project, _stack("Python 3", "Python standard library http.server", "unittest"))

    assert "package.json" in written


class _Picks:
    """A model that answers with a number; counts its calls."""

    def __init__(self, answer):
        self.answer, self.asked = answer, []

    def invoke(self, messages, **kwargs):
        self.asked.append(messages[-1].content)
        return SimpleNamespace(content=self.answer)

    openai_api_base = None


def test_a_stack_no_rule_matches_is_given_to_the_model_to_pick_from_and_the_pick_is_replayed(_library, tmp_path):
    _keep(_library, "language-typescript-framework-sveltekit-testing-vitest", "svelte")
    _keep(_library, "language-typescript-framework-hono-testing-vitest", "hono")
    project = tmp_path / "project"
    project.mkdir()
    model = _Picks("2")

    written = custom_setup.replay(project, _stack("TypeScript", "Nuxt (Vue)", "Vitest"), model)

    assert "package.json" in written and len(model.asked) == 1
    assert "Nuxt" in model.asked[0] and "sveltekit" in model.asked[0] and "hono" in model.asked[0]


def test_the_model_is_not_asked_when_a_rule_already_matches(_library, tmp_path):
    _keep(_library, "language-typescript-framework-hono-testing-vitest", "hono")
    project = tmp_path / "project"
    project.mkdir()
    model = _Picks("1")

    custom_setup.replay(project, _stack("TypeScript", "Hono", "Vitest"), model)

    assert model.asked == []


def test_a_model_that_says_none_or_fails_replays_nothing(_library, tmp_path):
    _keep(_library, "language-typescript-framework-hono-testing-vitest", "hono")
    project = tmp_path / "project"
    project.mkdir()

    assert custom_setup.replay(project, _stack("Go", "Gin", "go test"), _Picks("0")) == []

    class _Broken:
        def invoke(self, messages, **kwargs):
            raise RuntimeError("the server is down")

    assert custom_setup.replay(project, _stack("Go", "Gin", "go test"), _Broken()) == []
