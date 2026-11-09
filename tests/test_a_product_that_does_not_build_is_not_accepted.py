"""A project that declares a production build has it run: a failure is a defect, and the release is held back.

Measured on one run: 12 of 12 locked tests on the development server, 1 of 10 hidden tests, and a build no step of the
harness had ever run.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.acceptance import suite
from app.graph import acceptance_nodes, delivery, workflow
from app.stacks import contract, pack_named, production_build
from app.stacks.packs import ALL_PACKS

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
COMPILER = "src/App.tsx(3,18): error TS2503: Cannot find namespace 'JSX'."


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def project(tmp_path):
    """A workspace with a real repository and a React pack's contract, as a run has one."""
    root = tmp_path / "workspace"
    (root / "web" / "src").mkdir(parents=True)
    (root / "web" / "src" / "App.tsx").write_text("export const App = 1;\n")
    (root / "web" / "package.json").write_text(json.dumps({"scripts": {"build": "tsc --noEmit && vite build"}}))
    (root / ".harness").mkdir()
    (root / contract.CONTRACT_FILE).write_text(json.dumps({"pack": "browser-react", "project": "web"}))
    (root / ".gitignore").write_text(".harness/\n")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "first")
    return root


class Fake:
    def __init__(self, code=1, stdout=COMPILER):
        self.calls, self.code, self.stdout = [], code, stdout

    def __call__(self, argv, category, project):
        self.calls.append((list(argv), category, project))
        return {"returncode": str(self.code), "stdout": self.stdout, "stderr": ""}


def _state(root):
    return {"repository": SimpleNamespace(root_path=str(root)), "milestone_plan": None}


def test_a_failing_build_says_what_the_compiler_said(project):
    fake = Fake()
    assert COMPILER in production_build.failure(project, fake)
    assert fake.calls == [(["npm", "run", "build"], "build", "web")]


def test_it_runs_once_per_version_of_the_product_and_a_failure_stands_unchanged(project):
    fake = Fake()
    first = production_build.failure(project, fake)
    assert production_build.failure(project, fake) == first and first
    assert len(fake.calls) == 1, "nothing changed: not run again, and the answer is still the failure"
    (project / "web" / "src" / "App.tsx").write_text("export const App = 2;\n")
    fake.code = 0
    assert production_build.failure(project, fake) == ""
    assert len(fake.calls) == 2


def test_a_commit_of_what_was_measured_is_no_change(project):
    fake = Fake()
    (project / "web" / "src" / "App.tsx").write_text("export const App = 2;\n")
    production_build.failure(project, fake)
    _git(project, "add", "-A")
    _git(project, "commit", "-qm", "the batch")
    production_build.failure(project, fake)
    assert len(fake.calls) == 1


@pytest.mark.parametrize("outcome", [{"error": "refused"}, {"returncode": "124", "stdout": "x", "error": "timed out"}, {}])
def test_a_build_that_could_not_run_or_finish_is_no_answer(project, outcome):
    calls = []

    def runner(argv, category, where):
        calls.append(argv)
        return outcome

    assert production_build.failure(project, runner) == ""
    production_build.failure(project, runner)
    assert len(calls) == 2, "no answer is kept: the next round asks again"


def test_it_never_raises(project):
    def runner(*_):
        raise RuntimeError("boom")

    assert production_build.failure(project, runner) == ""


def test_a_project_with_no_pack_uses_what_its_manifest_declares(tmp_path, monkeypatch):
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"build": "tsc"}}))
    assert production_build.declared(tmp_path) is None, "nothing is installed to build with"
    (tmp_path / "node_modules").mkdir()
    assert production_build.declared(tmp_path) == (["npm", "run", "build"], "")


@pytest.mark.parametrize("manifest", [{"scripts": {"test": "x"}}, {}, ["not", "an", "object"]])
def test_a_manifest_that_names_no_build_has_none(tmp_path, manifest):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "package.json").write_text(json.dumps(manifest))
    assert production_build.declared(tmp_path) is None


def test_a_project_with_no_manifest_has_none_and_nothing_runs(tmp_path):
    def runner(*_):
        raise AssertionError("nothing to run")

    assert production_build.failure(tmp_path, runner) == ""


def test_a_proven_setup_s_declared_build_is_kept_as_pack_data():
    from app.stacks.custom_setup import pack_from

    pack = pack_from({"pack": "proven-setup", "setup": {
        "kind": "http_api", "unit_test": ["a"], "acceptance_test": ["b"], "unit_report": "u", "acceptance_report": "r",
        "unit_dir": "u", "acceptance_dir": "a", "acceptance_pattern": "*", "unit_pattern": "*", "build": ["make", "dist"],
    }})
    assert pack.production_build == ("make", "dist")


def test_every_page_pack_on_a_development_server_declares_its_build():
    for pack in ALL_PACKS:
        if pack.kind == "browser_app" and '"build"' in str(pack.files.get("package.json") or ""):
            assert pack.production_build == ("npm", "run", "build"), pack.name


def test_the_harness_names_no_stack_for_it():
    source = Path(production_build.__file__).read_text(encoding="utf-8")
    assert not re.search(r"\b(?:react|vue|svelte|angular|vite|next)\b", source, re.I)


def test_the_round_raises_a_blocking_defect_with_the_compiler_s_output_on_a_green_suite(project, monkeypatch):
    """The suite passes everything, as it did on the run that shipped a product that does not build."""
    monkeypatch.setattr(acceptance_nodes, "_failing_due", lambda _s: ([], "npx playwright test"))
    monkeypatch.setattr(suite, "last_result", lambda _r: {"ran": True, "failed": 0})
    monkeypatch.setattr(acceptance_nodes, "_owner_for", lambda _s, _t: "frontend")
    fake = Fake()
    real = production_build.failure
    monkeypatch.setattr(production_build, "failure", lambda root: real(root, fake))
    defects = acceptance_nodes.failing_due_defects(_state(project), [])
    assert len(defects) == 1
    defect = defects[0]
    assert defect.severity == "blocking"
    assert COMPILER in defect.actual_behavior
    assert defect.affected_files == ["web/src/App.tsx"]
    assert "npm run build" in defect.reproduction_steps
    for text in (defect.description, defect.reproduction_steps, defect.expected_behavior):
        assert not BANNED.search(text), text


def test_the_round_raises_it_beside_a_product_that_does_not_start(project, monkeypatch):
    monkeypatch.setattr(acceptance_nodes, "_failing_due", lambda _s: (
        [{"id": "AC-1", "text": "x", "tests": []}], "npx playwright test"))
    monkeypatch.setattr(suite, "last_result", lambda _r: {"problem": suite.PRODUCT_DID_NOT_START + ": x"})
    monkeypatch.setattr(acceptance_nodes, "_owner_for", lambda _s, _t: "frontend")
    monkeypatch.setattr(acceptance_nodes, "_what_the_language_service_finds", lambda _s: [])
    fake = Fake()
    real = production_build.failure
    monkeypatch.setattr(production_build, "failure", lambda root: real(root, fake))
    said = [d.description for d in acceptance_nodes.failing_due_defects(_state(project), [])]
    assert production_build.THE_PRODUCT_DOES_NOT_BUILD in said
    assert acceptance_nodes.THE_PRODUCT_DOES_NOT_START in said


def test_a_build_that_passes_raises_nothing(project, monkeypatch):
    monkeypatch.setattr(acceptance_nodes, "_failing_due", lambda _s: ([], "x"))
    monkeypatch.setattr(suite, "last_result", lambda _r: {})
    fake = Fake(code=0)
    real = production_build.failure
    monkeypatch.setattr(production_build, "failure", lambda root: real(root, fake))
    assert acceptance_nodes.failing_due_defects(_state(project), []) == []


def _defect():
    return SimpleNamespace(description=production_build.THE_PRODUCT_DOES_NOT_BUILD, affected_files=[])


def test_the_defect_is_settled_by_the_build_itself(project, monkeypatch):
    results = {"code": 1}

    def fake(root, runner=None):
        return "" if results["code"] == 0 else COMPILER

    monkeypatch.setattr(production_build, "failure", fake)
    assert workflow._the_defect_s_tests_pass(project, _defect()) is False
    results["code"] = 0
    assert workflow._the_defect_s_tests_pass(project, _defect()) is True


def test_a_fix_of_the_build_needs_no_other_regression_test(project, monkeypatch):
    monkeypatch.setattr(production_build, "failure", lambda _root, _runner=None: "")
    state = {"repository": SimpleNamespace(root_path=str(project))}
    assert workflow._the_suite_already_guards_it(state, "the fix", _defect()) is True
    monkeypatch.setattr(production_build, "failure", lambda _root, _runner=None: COMPILER)
    assert workflow._the_suite_already_guards_it(state, "the fix", _defect()) is False


def _release(root, attempts=0):
    return delivery.release(
        {"repository": SimpleNamespace(root_path=str(root)), "release_attempts": attempts},
        {"configurable": {}},
        SimpleNamespace(judgement_model=None, checkpointer=None, repo_root=str(root), allow_subdirectories=True),
    )


def test_the_release_is_held_back_with_the_compiler_s_output(project, monkeypatch):
    monkeypatch.setattr(production_build, "failure", lambda _root: COMPILER)
    monkeypatch.setattr(delivery, "_unit_tests_failing", lambda _root: [])
    update = _release(project)
    assert update["stage"] == "technical_lead"
    assert COMPILER in update["revision_comments"][-1]
    assert update["release_attempts"] == 1


def test_a_failing_build_never_ships_under_the_unit_tests_allowance(project, monkeypatch):
    """Failing unit tests may ship recorded when nothing else fails; a failing build is something else."""
    monkeypatch.setenv("RELEASE_WITH_FAILING_UNIT_TESTS", "on")
    monkeypatch.setattr(production_build, "failure", lambda _root: COMPILER)
    monkeypatch.setattr(delivery, "_unit_tests_failing", lambda _root: ["a unit test"])
    update = _release(project, attempts=delivery.MAX_RELEASE_ATTEMPTS)
    assert update.get("stage") != "complete"
    assert "completion_gaps" not in update
    assert COMPILER in str(update)


def test_the_real_command_runs_for_real(project):
    """No stand-in for the command: a real process, a real exit code, a real repository's fingerprint."""
    (project / "web" / "package.json").write_text(json.dumps({"scripts": {"build": "echo 'src/App.tsx(1,1): error X' && exit 2"}}))
    (project / "web" / "node_modules").mkdir()

    def runner(argv, category, where):
        done = subprocess.run(argv, cwd=project / where, capture_output=True, text=True, check=False)
        return {"returncode": str(done.returncode), "stdout": done.stdout, "stderr": done.stderr}

    said = production_build.failure(project, runner)
    assert "src/App.tsx(1,1): error X" in said
    assert production_build.files_named(project, said) == ["web/src/App.tsx"]
    (project / "web" / "package.json").write_text(json.dumps({"scripts": {"build": "echo built"}}))
    assert production_build.failure(project, runner) == ""
    assert pack_named("browser-react") is not None
