"""The tests a fixer is told about after a write run on the project the suite would run, not on the write as it stands.

Measured on a small-model run: a service on a runtime that runs `.ts` files itself; a fixer changed `./app.ts` to
`./app.js` in an import, the after-write check said the defect's tests "still fail" because of that import alone, and
the fixer spent its stage on the same edit. The harness corrects the extension (and puts back its own files) when the
suite runs; the check ran before that.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.graph import workflow
from app.stacks import contract, pack_named


def test_the_check_puts_the_import_extension_right_before_it_runs_the_tests(tmp_path, monkeypatch):
    pack = pack_named("node-hono-native-api")
    contract.write(tmp_path, pack, "notes", "Notes")
    project = tmp_path / "notes"
    (project / "src").mkdir(parents=True)
    (project / "src" / "app.ts").write_text("export const app = 1;\n")
    main = project / "src" / "main.ts"
    main.write_text("import { app } from './app.js';\nconsole.log(app);\n")
    seen = {}

    def run_unit_tests(root):
        seen["main"] = main.read_text()
        return True, ""

    monkeypatch.setattr(workflow, "_run_unit_tests_procedurally", run_unit_tests)
    defect = SimpleNamespace(description=f"{workflow.UNIT_TESTS_FAIL} It says: x", affected_files=[])

    assert workflow._the_defect_s_tests_pass(tmp_path, defect) is True
    assert "./app.ts'" in seen["main"] and "./app.js'" not in seen["main"]


def test_a_failing_unit_run_is_measured_again_by_the_unit_tests_whatever_ids_their_names_carry(tmp_path, monkeypatch):
    """Measured on two runs: unit tests named "AC-1 CreateNoteTest" sent the re-measure to the acceptance files of those
    criteria, which passed, and the defect was closed every round with four unit tests still failing."""
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    folder = tmp_path / "notes" / "acceptance"
    folder.mkdir(parents=True)
    (folder / "a.spec.js").write_text("test('[AC-1] creates', () => {});\n")
    monkeypatch.setattr(workflow, "_run_unit_tests_procedurally", lambda root: (False, "1 failing"))
    monkeypatch.setattr("app.acceptance.per_file.each_file", lambda *a, **k: [{"outcome": "finished"}])
    defect = SimpleNamespace(description=f"{workflow.UNIT_TESTS_FAIL} It says: AC-1 CreateNoteTest failed", affected_files=[])

    assert workflow._the_defect_s_tests_pass(tmp_path, defect) is False
