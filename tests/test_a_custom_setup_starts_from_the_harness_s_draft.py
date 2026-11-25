"""A stack no pack covers is set up from the harness's own draft of `stack-setup.json`, told the sandbox's facts (PA.11).

Measured on one medium run: the custom setup stage took 96 minutes and 193 calls and proved nothing. The declaration was
never written though the request asked for it first, three commands installed a browser (which needs root), and twenty
were probes. The packs of the stack's language and kind already say most of the declaration, and the harness already
knows the browser is installed, that nothing runs as root and that a command is one program.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.stacks import custom_setup, pack_named
from app.stacks.custom_setup import DECLARATION_FILE, PROVEN_SETUP

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

#: A full-stack product in a language with packs, on a framework none of them is.
STACK = SimpleNamespace(language="TypeScript", framework="Nuxt", frontend_framework="Vue", database="",
                        testing_framework="Vitest and Playwright", product_kind="")


class TestTheDraft:
    def test_a_stack_with_a_pack_of_its_language_and_kind_takes_that_pack_s_runners(self):
        draft = custom_setup.draft_declaration(STACK, "fullstack", "notes")
        model = pack_named("fullstack-react-express")

        assert draft["kind"] == "fullstack"
        assert draft["unit_test"] == list(model.unit_test) and draft["unit_dir"] == model.unit_dir
        assert draft["acceptance_test"] == list(model.acceptance_test)
        assert draft["acceptance_dir"] == "acceptance" and draft["acceptance_pattern"] == "*.spec.js"
        assert draft["install"] == [list(argv) for argv in model.install]
        assert draft["smoke_files"] == ["tests/client/scaffold-smoke.test.tsx", "acceptance/scaffold-smoke.spec.js"]
        assert draft["kept_files"] == []

    def test_a_service_in_a_language_with_no_pack_takes_only_the_acceptance_side_of_its_kind(self):
        kotlin = SimpleNamespace(language="Kotlin", framework="Ktor", frontend_framework="", testing_framework="JUnit")

        draft = custom_setup.draft_declaration(kotlin, "http_api", "notes")

        assert draft["unit_test"] == [] and draft["unit_dir"] == ""
        assert draft["acceptance_test"] == ["npm", "run", "test:acceptance"]
        assert draft["smoke_files"] == ["acceptance/scaffold-smoke.spec.js"]

    def test_a_kind_no_pack_has_gets_no_draft(self):
        assert custom_setup.draft_declaration(STACK, "", "notes") is None

    def test_a_declaration_already_there_is_never_replaced(self, tmp_path):
        (tmp_path / DECLARATION_FILE).write_text("{}")

        assert custom_setup.write_draft_declaration(tmp_path, STACK, "fullstack", "notes") is False
        assert (tmp_path / DECLARATION_FILE).read_text() == "{}"


class TestTheRequest:
    def test_it_states_the_sandbox_s_facts(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        (tmp_path / ".cache" / "ms-playwright").mkdir(parents=True)

        text = custom_setup.build_setup_request("notes", STACK, "fullstack")["messages"][0]["content"]

        assert "already installed" in text and "never install a browser" in text
        assert "Nothing runs as root" in text and "no `sudo`" in text
        assert "one program and its arguments, run without a shell" in text

    def test_with_no_browser_installed_it_says_how_to_install_one_without_root(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))

        text = custom_setup.build_setup_request("notes", STACK, "fullstack")["messages"][0]["content"]

        assert "No browser build is installed yet" in text and "never add `--with-deps`" in text

    def test_drafted_it_is_asked_to_correct_the_draft_not_to_write_one(self):
        text = custom_setup.build_setup_request("notes", STACK, "fullstack", drafted=True)["messages"][0]["content"]

        assert "The harness has already written `notes/stack-setup.json`" in text
        assert "First, before anything else, write" not in text

    def test_its_new_words_use_none_of_the_banned_words(self):
        from app.agents.environment_contract import the_setup_facts

        drafted = custom_setup.build_setup_request("notes", STACK, "fullstack", drafted=True)["messages"][0]["content"]
        start = drafted.index("The harness has already written")
        assert not BANNED.search(drafted[start:drafted.index("1. Create the project")])
        assert not BANNED.search(the_setup_facts())


# --- the stage -----------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _a_library_of_its_own(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("PROVEN_SETUP_LIBRARY", str(tmp_path_factory.mktemp("library")))


@pytest.fixture
def stage(monkeypatch, tmp_path):
    """The scaffold node with the setup stage's agent replaced: it records its request and what it found on disk."""
    from app.graph import acceptance_nodes, workflow

    calls: list[dict] = []
    monkeypatch.setattr("app.tools.repository.pinned_project_directory", lambda root: "notes")
    monkeypatch.setattr("app.agents.specialists.create_specialist_agent", lambda *a, **k: object())
    monkeypatch.setattr(workflow, "_stop_if_cancelled", lambda run_id: None)
    monkeypatch.setattr(acceptance_nodes, "_decide", lambda *a, **k: None)

    def run_gated(state, config, *, stage_name, agent, initial_request, output_key, next_stage):
        declared = tmp_path / "notes" / DECLARATION_FILE
        calls.append({"stage": stage_name, "request": initial_request["messages"][0]["content"],
                      "declared": json.loads(declared.read_text()) if declared.is_file() else None})
        return {output_key: object(), "stage": next_stage}

    def proved(root, project, stack, **kwargs):
        from app.stacks.scaffold import ScaffoldResult

        return ScaffoldResult(ok=True, pack=PROVEN_SETUP, project=project, problem="")

    monkeypatch.setattr(workflow, "_run_gated_agent", run_gated)
    monkeypatch.setattr(custom_setup, "prove", proved)
    ctx = acceptance_nodes.Context(model=None, judgement_model=None, checkpointer=None, repo_root=str(tmp_path))
    return SimpleNamespace(node=lambda state: acceptance_nodes.scaffold(state, {"configurable": {"thread_id": "t"}}, ctx),
                           calls=calls)


def test_the_setup_stage_finds_the_harness_s_draft_waiting(stage, tmp_path):
    state = {
        "repository": SimpleNamespace(root_path=str(tmp_path)),
        "stack_selection": SimpleNamespace(technology_stack=STACK),
        "product_intake": SimpleNamespace(product_name="notes"),
        "document": SimpleNamespace(text="A notes page with its own service."),
        "stack_pack": None,
    }

    stage.node(state)

    [call] = stage.calls
    assert call["stage"] == "stack_setup_0"
    assert call["declared"] is not None and call["declared"]["acceptance_test"] == ["npm", "run", "test:acceptance"]
    assert "The harness has already written `notes/stack-setup.json`" in call["request"]
    assert "Nothing runs as root" in call["request"]
