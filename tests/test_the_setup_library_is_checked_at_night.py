"""Each proven-setup library entry is replayed on an empty project at night; one that no longer proves is set aside
(scaffolding plan SF.0b), and the check writes nothing back."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.stacks import custom_setup
from setup_runners import reporting_failures

DECLARED = {
    "kind": "http_api", "install": [["npm", "install"]],
    "unit_test": ["npm", "test"], "unit_report": "unit.xml", "unit_dir": "tests", "unit_pattern": "*.test.ts",
    "acceptance_test": ["npm", "run", "test:acceptance"], "acceptance_report": "acceptance.xml",
    "acceptance_dir": "acceptance", "acceptance_pattern": "*.spec.ts", "kept_files": ["vitest.config.ts"],
    "smoke_files": ["tests/smoke.test.ts", "acceptance/smoke.spec.ts"],
}
FILES = {"vitest.config.ts": "export default {}\n", "tests/smoke.test.ts": "// smoke\n", "acceptance/smoke.spec.ts": "// smoke\n"}


def _runners(project, *, passing=True):
    """The sandbox's runners for `project`: the install passes, and each smoke test passes or fails."""
    def run(argv, category, working_directory):
        report = "unit.xml" if list(argv) == ["npm", "test"] else "acceptance.xml"
        outcome = "" if passing else "<failure message='no'/>"
        (project / report).write_text(f"<testsuites><testcase name='smoke'>{outcome}</testcase></testsuites>")
        return {"returncode": "0" if passing else "1"}
    return reporting_failures(run, project.parent)


def test_a_failing_entry_is_set_aside_and_a_passing_one_kept(tmp_path, monkeypatch):
    library = tmp_path / "library"
    library.mkdir()
    for name in ("good", "bad"):
        (library / f"{name}.json").write_text(json.dumps({"declaration": json.dumps(DECLARED), "files": FILES}))
    monkeypatch.setenv("PROVEN_SETUP_LIBRARY", str(library))
    replayed = []

    def run_for(workspace):
        replayed.append((workspace / "product" / "vitest.config.ts").is_file())
        return _runners(workspace / "product", passing=workspace.name == "good")

    results = custom_setup.check_the_library(tmp_path / "scratch", run_for=run_for)

    assert sorted((name, ok) for name, ok, _ in results) == [("bad.json", False), ("good.json", True)]
    assert replayed == [True, True], "each entry's own files are on the empty project before it is proven"
    assert sorted(path.name for path in library.glob("*.json")) == ["good.json"], "nothing is written back"
    assert (library / "failed" / "bad.json").is_file()


@pytest.mark.parametrize(("keep", "entries"), [(False, 0), (True, 1)], ids=["the nightly check", "a run's setup"])
def test_a_proof_that_keeps_nothing_writes_no_library_entry(tmp_path, monkeypatch, keep, entries):
    library = tmp_path / "library"
    monkeypatch.setenv("PROVEN_SETUP_LIBRARY", str(library))
    project = tmp_path / "notes"
    for name, text in FILES.items():
        (project / name).parent.mkdir(parents=True, exist_ok=True)
        (project / name).write_text(text)
    (project / custom_setup.DECLARATION_FILE).write_text(json.dumps(DECLARED))
    stack = SimpleNamespace(language="TypeScript", framework="Hono", frontend_framework="", database="",
                            testing_framework="node:test", product_kind="http_api")

    proven = custom_setup.prove(tmp_path, "notes", stack, run=_runners(project), keep=keep)

    assert proven.ok, proven.problem
    assert len(list(library.glob("*.json"))) == entries
