"""A page in Angular starts from a pack whose tests already run.

Angular was the one major component framework with no pack: a stack naming it
was "a custom stack", set up by the agents' own commands. The pack is the
application the Angular CLI generates, cut to what a product starts from, and
its two smoke tests were run through the commands a run uses
(`scripts/loop/verify_packs.py`).

Proving it took two changes outside the pack. Angular 22 needs Node 22.22 or
later (`test_one_node_everywhere`). And its CLI could not start under the
sandbox's per-process data limit, which counts what V8 reserves for each
thread rather than what it uses: measured through the sandbox in the
candidate image, `ng test` stopped at "Failed to reserve virtual memory for
CodeRange" under 1 GB and 1.5 GB and ran out of heap at 2 GB, and `ng serve`
needed 4 GB - while the unit run used 439 MB at most in one process and the
acceptance run, browser and all, 1.6 GB together. A pack now says what its
toolchain's processes need (`StackPack.process_memory`); the command's whole
tree is still bounded by what it really uses.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.stacks import choose_pack, contract, pack_named, supported_stacks_note
from app.stacks.packs import browser_angular
from app.tools import sandbox

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _stack(language: str, framework: str, frontend: str) -> SimpleNamespace:
    return SimpleNamespace(
        language=language, framework=framework, frontend_framework=frontend,
        database="", testing_framework="", product_kind="",
    )


@pytest.mark.parametrize("language, framework, frontend", [
    ("TypeScript", "Angular", "Angular"),
    ("TypeScript", "Angular 22", ""),
    ("TypeScript", "None", "Angular 22 with signals"),
])
def test_a_page_in_angular_gets_its_pack(language, framework, frontend):
    assert choose_pack(_stack(language, framework, frontend), "A page to keep notes").name == "browser-angular"


@pytest.mark.parametrize("frontend, chosen", [
    ("React", "browser-react"), ("Vue", "browser-vue"), ("Svelte", "browser-svelte"),
])
def test_the_other_component_frameworks_keep_theirs(frontend, chosen):
    assert choose_pack(_stack("TypeScript", frontend, frontend), "A page to keep notes").name == chosen


def test_the_stack_selector_is_offered_it():
    assert "Browser app in Angular and TypeScript" in supported_stacks_note()


def test_its_unit_tests_sit_beside_the_code_and_report_junit():
    pack = pack_named("browser-angular")
    files = pack.render("notes", "Notes", "notes")

    assert pack.unit_dir == "src" and pack.unit_pattern == "*.spec.ts"
    assert pack.kept_scripts["test"].startswith("ng test --no-watch --reporters=junit")
    assert "--output-file=test-results/unit.xml" in pack.kept_scripts["test"]
    assert "ng serve --host 127.0.0.1 --port ${port}" in files["playwright.config.js"]
    assert '"analytics": false' in files["angular.json"], "no prompt may wait on a terminal"
    assert "<h1>Notes</h1>" in files["src/app/app.html"]
    assert not any("{{" in text for text in files.values() if text)


def test_its_guide_names_no_product():
    pack = pack_named("browser-angular")

    assert not BANNED.search(pack.guide)
    assert not BANNED.search(browser_angular.GUIDE)


def _contracted(tmp_path: Path, name: str) -> Path:
    contract.write(tmp_path, pack_named(name), "notes", "Notes", "notes", scaffolded=False)
    return tmp_path


def test_a_project_gets_the_data_limit_its_pack_needs(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox, "MEMORY_LIMIT", "1g")

    assert sandbox._process_memory(tmp_path) == 1024**3, "no pack: the configured limit"
    assert sandbox._process_memory(_contracted(tmp_path, "browser-angular")) == 4 * 1024**3


def test_a_larger_configured_limit_stands(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox, "MEMORY_LIMIT", "6g")

    assert sandbox._process_memory(_contracted(tmp_path, "browser-angular")) == 6 * 1024**3


def test_a_pack_that_says_nothing_gets_the_configured_limit(tmp_path, monkeypatch):
    """A pack that runs no Node; one that does is given room for its threads
    (`tests/test_a_node_toolchain_gets_room_for_its_threads.py`)."""
    monkeypatch.setattr(sandbox, "MEMORY_LIMIT", "1g")

    assert sandbox._process_memory(_contracted(tmp_path, "python-http-api")) == 1024**3


@pytest.mark.skipif(not hasattr(__import__("resource"), "RLIMIT_DATA"), reason="Linux only")
def test_the_child_runs_under_the_limit_it_was_given(tmp_path):
    code = "import resource; print(resource.getrlimit(resource.RLIMIT_DATA)[0])"

    finished = sandbox._run_and_watch_the_tree(
        [sys.executable, "-c", code], cwd=str(tmp_path), env=dict(os.environ), timeout=30,
        data_bytes=3 * 1024**3,
    )

    assert int(finished.stdout.strip()) == 3 * 1024**3


def test_a_command_in_the_project_is_given_its_pack_s_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox, "MEMORY_LIMIT", "1g")
    given = {}

    def run(argv, **kwargs):
        given.update(kwargs)
        import subprocess

        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(sandbox, "_run_and_watch_the_tree", run)

    sandbox.SandboxExecutor._execute_here(
        ["node", "--version"], str(_contracted(tmp_path, "browser-angular")), "testing_specialist", "test", 30, None
    )

    assert given["data_bytes"] == 4 * 1024**3


def test_the_scaffold_records_its_pack_before_the_first_install(tmp_path):
    """The scaffold's own install and smoke tests run under the pack's limit too."""
    from app.stacks.scaffold import scaffold

    seen = []

    def run(argv, category, working_directory):
        seen.append(contract.read(tmp_path))
        return {"returncode": "1", "stderr": "no network"}

    result = scaffold(tmp_path, pack_named("browser-angular"), "notes", "Notes", run=run)

    assert not result.ok
    assert seen and seen[0] is not None and seen[0]["pack"] == "browser-angular"
    assert seen[0]["scaffolded"] is False
