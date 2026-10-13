"""A stack no pack covers is set up by an agent and proven by the harness, like a pack.

Before, a stack with no pack (Nuxt, SvelteKit, Ktor, Quarkus ...) started with
no setup at all, and its runners were set up piecemeal by whichever stage
needed one first. Now a setup stage creates the project with the framework's
own generator and declares its runners in `stack-setup.json`; the harness runs
the install and both smoke tests through exactly those commands, and only a
setup that passes is recorded - as a contract every later stage and gate reads
the way it reads a pack's.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.stacks import contract, custom_setup
from app.stacks.custom_setup import DECLARATION_FILE, PROVEN_SETUP, prove, read_declaration

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
PASSED = "<testsuites><testcase name='smoke'/></testsuites>"
FAILED = "<testsuites><testcase name='smoke'><failure message='no'>no</failure></testcase></testsuites>"

STACK = SimpleNamespace(
    language="TypeScript", framework="Nuxt", frontend_framework="Vue",
    database="", testing_framework="Vitest and Playwright", product_kind="",
)

DECLARED = {
    "kind": "fullstack",
    "install": [["npm", "install"]],
    "unit_test": ["npm", "test"],
    "unit_report": "test-results/unit.xml",
    "unit_dir": "tests",
    "unit_pattern": "*.test.ts",
    "acceptance_test": ["npm", "run", "test:acceptance"],
    "acceptance_report": "test-results/acceptance.xml",
    "acceptance_dir": "acceptance",
    "acceptance_pattern": "*.spec.ts",
    "kept_files": ["vitest.config.ts", "playwright.config.ts"],
    "smoke_files": ["tests/smoke.test.ts", "acceptance/smoke.spec.ts"],
    "guide": "Unit tests are Vitest files in tests/.",
    "acceptance_guide": "Acceptance tests open the page with Playwright.",
}


def _set_up(root: Path, declared: dict | None = None) -> Path:
    project = root / "notes"
    for name in ("vitest.config.ts", "playwright.config.ts", "tests/smoke.test.ts", "acceptance/smoke.spec.ts"):
        (project / name).parent.mkdir(parents=True, exist_ok=True)
        (project / name).write_text(f"// {name}\n")
    (project / "package.json").write_text(json.dumps({"scripts": {
        "dev": "nuxt dev", "test": "vitest run --reporter=junit", "test:acceptance": "playwright test",
    }}))
    (project / DECLARATION_FILE).write_text(json.dumps(declared or DECLARED))
    return project


def _runner(root: Path, failing: str = "", seen: list | None = None):
    def run(argv, category, working_directory):
        if seen is not None:
            seen.append((list(argv), category))
        if category != "test":
            return {"returncode": "0"}
        unit = list(argv) == DECLARED["unit_test"]
        report = root / working_directory / DECLARED["unit_report" if unit else "acceptance_report"]
        report.parent.mkdir(parents=True, exist_ok=True)
        fails = failing == ("unit" if unit else "acceptance")
        report.write_text(FAILED if fails else PASSED)
        return {"returncode": "1" if fails else "0", "stdout": "AssertionError: smoke" if fails else ""}

    return run


# --- the declaration ---------------------------------------------------------------

def test_a_declaration_is_read_as_the_commands_and_places_it_names(tmp_path):
    declared, problem = read_declaration(_set_up(tmp_path))

    assert problem == ""
    assert declared.unit_test == ("npm", "test")
    assert declared.install == (("npm", "install"),)
    assert declared.kept_files == ("vitest.config.ts", "playwright.config.ts")


@pytest.mark.parametrize("change, said", [
    ({"unit_report": "../../etc/x.xml"}, "`unit_report` must be a path inside the project"),
    ({"unit_test": "npm test"}, "`unit_test` must be a command"),
    ({"acceptance_dir": "tests"}, "a directory of their own"),
    ({"kept_files": ["missing.config.ts"]}, "do not exist: `missing.config.ts`"),
    ({"smoke_files": ["tests/smoke.test.ts"]}, "`smoke_files` must list"),
    ({"kind": "game"}, "`kind` must be one of"),
])
def test_a_declaration_that_cannot_be_used_says_why(tmp_path, change, said):
    declared, problem = read_declaration(_set_up(tmp_path, {**DECLARED, **change}))

    assert declared is None
    assert said in problem


def test_no_declaration_at_all_is_said(tmp_path):
    (tmp_path / "notes").mkdir()

    assert "was not written" in read_declaration(tmp_path / "notes")[1]


# --- proving it --------------------------------------------------------------------

def test_a_setup_whose_smoke_tests_pass_is_recorded_like_a_pack(tmp_path):
    project = _set_up(tmp_path)
    seen: list = []

    result = prove(tmp_path, "notes", STACK, title="Notes", run=_runner(tmp_path, seen=seen))

    assert result.ok, result.problem
    assert [argv for argv, _ in seen] == [["npm", "install"], ["npm", "test"], ["npm", "run", "test:acceptance"]]
    pack, record = contract.the_pack(tmp_path)
    assert pack.name == PROVEN_SETUP and record["pack"] == PROVEN_SETUP
    assert pack.kind == "fullstack" and pack.language == "typescript"
    assert record["acceptance_test"] == ["npm", "run", "test:acceptance"]
    assert pack.acceptance_dir == "acceptance" and pack.unit_pattern == "*.test.ts"
    assert contract.kept_paths(tmp_path) == {"notes/vitest.config.ts", "notes/playwright.config.ts"}
    assert pack.kept_scripts == {"test": "vitest run --reporter=junit", "test:acceptance": "playwright test"}
    # The smoke tests and the declaration are not the product's.
    assert not (project / "tests/smoke.test.ts").exists()
    assert not (project / "acceptance/smoke.spec.ts").exists()
    assert not (project / DECLARATION_FILE).exists()


def test_what_it_proved_is_kept_as_it_was_proven(tmp_path):
    project = _set_up(tmp_path)
    prove(tmp_path, "notes", STACK, run=_runner(tmp_path))
    (project / "playwright.config.ts").write_text("// tests switched off\n")
    manifest = json.loads((project / "package.json").read_text())
    manifest["scripts"]["test"] = "echo skipped"
    (project / "package.json").write_text(json.dumps(manifest))

    repairs = contract.enforce(tmp_path)

    assert (project / "playwright.config.ts").read_text() == "// playwright.config.ts\n"
    assert json.loads((project / "package.json").read_text())["scripts"]["test"] == "vitest run --reporter=junit"
    assert len(repairs) == 2


def test_every_stage_is_told_the_setup_as_it_is_told_a_pack_s(tmp_path):
    _set_up(tmp_path)
    prove(tmp_path, "notes", STACK, run=_runner(tmp_path))

    told = contract.describe(tmp_path)

    assert "`notes/tests/`, files named `*.test.ts`; run with `npm test`" in told
    assert "Unit tests are Vitest files in tests/." in told


def test_the_acceptance_suite_runs_on_the_proven_command(tmp_path):
    from app.acceptance import suite

    _set_up(tmp_path)
    prove(tmp_path, "notes", STACK, run=_runner(tmp_path))

    assert suite._command(tmp_path) == (["npm", "run", "test:acceptance"], "test-results/acceptance.xml", "notes")


@pytest.mark.parametrize("failing", ["unit", "acceptance"])
def test_a_setup_whose_smoke_test_fails_is_not_recorded_and_says_what_failed(tmp_path, failing):
    project = _set_up(tmp_path)

    result = prove(tmp_path, "notes", STACK, run=_runner(tmp_path, failing=failing))

    assert not result.ok
    assert f"The {failing} smoke test did not pass" in result.problem
    assert "AssertionError: smoke" in result.problem
    assert contract.read(tmp_path) is None
    assert (project / DECLARATION_FILE).exists(), "kept for the second attempt to correct"


def test_an_install_that_fails_twice_is_not_a_setup(tmp_path):
    _set_up(tmp_path)

    def run(argv, category, working_directory):
        return {"returncode": "1", "stderr": "ERESOLVE could not resolve"}

    result = prove(tmp_path, "notes", STACK, run=run)

    assert not result.ok and "ERESOLVE" in result.problem


def test_the_request_names_no_product_and_points_at_the_registry():
    text = custom_setup.build_setup_request("notes", STACK, "fullstack", "The unit smoke test did not pass")["messages"][0]["content"]

    assert not BANNED.search(text)
    assert "look_up_package" in text
    assert "notes/stack-setup.json" in text
    assert "The unit smoke test did not pass" in text


# --- the stage -----------------------------------------------------------------------

def _state(root: Path, scaffold_result: dict | None = None) -> dict:
    return {
        "repository": SimpleNamespace(root_path=str(root)),
        "stack_selection": SimpleNamespace(technology_stack=STACK),
        "product_intake": SimpleNamespace(product_name="notes"),
        "document": SimpleNamespace(text="A notes page with its own service."),
        "stack_pack": None,
        **({"scaffold_result": scaffold_result} if scaffold_result else {}),
    }


@pytest.fixture
def stage(monkeypatch, tmp_path):
    """The scaffold node with the setup stage's agent replaced by `answer`."""
    from app.graph import acceptance_nodes, workflow

    calls: list[dict] = []
    monkeypatch.setattr("app.tools.repository.pinned_project_directory", lambda root: "notes")
    monkeypatch.setattr("app.agents.specialists.create_specialist_agent", lambda *a, **k: object())
    monkeypatch.setattr(workflow, "_stop_if_cancelled", lambda run_id: None)
    monkeypatch.setattr(acceptance_nodes, "_decide", lambda *a, **k: None)
    outcome = {"proven": True}

    def run_gated(state, config, *, stage_name, agent, initial_request, output_key, next_stage):
        calls.append({"stage": stage_name, "request": initial_request["messages"][0]["content"]})
        return {output_key: object(), "stage": next_stage}

    def proved(root, project, stack, **kwargs):
        from app.stacks.scaffold import ScaffoldResult

        return ScaffoldResult(ok=outcome["proven"], pack=PROVEN_SETUP, project=project,
                              problem="" if outcome["proven"] else "The unit smoke test did not pass")

    monkeypatch.setattr(workflow, "_run_gated_agent", run_gated)
    monkeypatch.setattr(custom_setup, "prove", proved)
    ctx = acceptance_nodes.Context(model=None, judgement_model=None, checkpointer=None, repo_root=str(tmp_path))
    config = {"configurable": {"thread_id": "t"}}

    def node(state):
        return acceptance_nodes.scaffold(state, config, ctx)

    return SimpleNamespace(node=node, calls=calls, outcome=outcome)


def test_a_proven_setup_hands_on_to_qa_as_a_pack_would(stage, tmp_path):
    update = stage.node(_state(tmp_path))

    assert [call["stage"] for call in stage.calls] == ["stack_setup_0"]
    assert update["stage"] == "acceptance_author"
    assert update["stack_pack"] == PROVEN_SETUP
    assert update["scaffold_result"]["ok"] is True


def test_an_unproven_setup_is_sent_back_once_with_what_failed(stage, tmp_path):
    stage.outcome["proven"] = False

    first = stage.node(_state(tmp_path))
    second = stage.node(_state(tmp_path, first["scaffold_result"]))

    assert first["stage"] == "scaffold"
    assert "The unit smoke test did not pass" in stage.calls[1]["request"]
    assert [call["stage"] for call in stage.calls] == ["stack_setup_0", "stack_setup_1"]
    assert second["stage"] == "acceptance_author"
    assert second["scaffold_result"]["left_to_the_agents"] is True
    assert stage.node(_state(tmp_path, second["scaffold_result"]))["stage"] == "acceptance_author"
    assert len(stage.calls) == 2, "never set up a third time"


def test_a_seeded_codebase_is_built_on_as_it_is(stage, tmp_path):
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "go.mod").write_text("module notes\n")

    assert stage.node(_state(tmp_path))["stage"] == "acceptance_author"
    assert stage.calls == []


def test_it_can_be_switched_off(stage, tmp_path, monkeypatch):
    monkeypatch.setenv("CUSTOM_STACK_SETUP", "false")

    assert stage.node(_state(tmp_path))["stage"] == "acceptance_author"
    assert stage.calls == []


def test_a_setup_stage_that_pauses_or_restarts_comes_back_to_the_scaffold():
    from app.graph.workflow import _owning_node

    assert _owning_node("stack_setup_1") == "scaffold"
