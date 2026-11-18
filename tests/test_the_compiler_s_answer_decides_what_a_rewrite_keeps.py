"""The compiler's answer, not the order of the passes, decides what a rewrite or a draft's repair keeps.

Deep review 2026-11-18, item A2: a fix's rewrite ran up to three whole-file passes and kept the last even when it
ended "The compiler still reports ..." and an earlier pass had compiled; a draft's repair did the same in two passes
and never measured its last; each pass saw at most four findings. And a fix in a compiled language that wrote a call
to nothing, when nothing passed before it, was kept: only JavaScript, TypeScript and Python were asked after a fix.
"""
from __future__ import annotations

import subprocess
from types import SimpleNamespace

from app import ci
from app.agents.technical_lead import SpecialistTask
from app.graph import drafting, engineering, rewritten_fixes

FILE = "app/src/store.ts"


class _Versions:
    """A model that answers each call with the next version of the file."""

    def __init__(self, *versions: str) -> None:
        self.versions = list(versions)

    def invoke(self, messages, **kwargs):
        return SimpleNamespace(content=f"```ts\n{self.versions.pop(0)}\n```")


def _the_compiler(errors_by_version: dict[str, int], root):
    """The compiler as the edge: how many errors it reports depends on the file as it is on disk."""
    def diagnose(files):
        text = (root / FILE).read_text()
        many = next((count for marker, count in errors_by_version.items() if marker in text), 0)
        return [f"- In `{FILE}` line {n}: error {n}" for n in range(1, many + 1)]
    return diagnose


def _write(base, path, content):
    from pathlib import Path

    (Path(base) / path).write_text(content)


def test_a_rewrite_keeps_the_pass_the_compiler_found_fewest_errors_in(tmp_path):
    (tmp_path / "app" / "src").mkdir(parents=True)
    (tmp_path / FILE).write_text("export const store = 0;\n")
    defect = SimpleNamespace(description="The service does not start", expected_behavior="It starts",
                             affected_files=[FILE], actual_behavior=f"{FILE}:1 failed", reproduction_steps=[])
    model = _Versions("export const store = 'one';", "export const store = 'two';", "export const store = 'three';")

    output = rewritten_fixes.fix_by_rewriting(
        defect, tmp_path, model, write=_write,
        diagnose=_the_compiler({"'one'": 1, "'two'": 3, "'three'": 2}, tmp_path),
    )

    assert "'one'" in (tmp_path / FILE).read_text()
    assert "error 2" not in " ".join(output.decisions), "it reports the kept version's errors"


def test_a_draft_s_repair_keeps_the_version_with_fewest_errors(tmp_path, monkeypatch):
    (tmp_path / "app" / "src").mkdir(parents=True)
    versions = iter(["export const a = 'draft';\n", "export const a = 'first repair';\n",
                     "export const a = 'second repair';\n"])
    monkeypatch.setattr(drafting, "_draft_one", lambda *a, **k: next(versions))
    order = SpecialistTask(specialist_role="backend", task_description="build the store",
                           acceptance_criteria=["works"], files=[FILE])

    drafting.draft_work_orders(
        [order], object(), None, str(tmp_path), object(), write=_write,
        diagnose=_the_compiler({"'draft'": 2, "'first repair'": 1, "'second repair'": 3}, tmp_path),
    )

    assert "'first repair'" in (tmp_path / FILE).read_text()


def test_a_pass_is_given_more_than_four_findings(tmp_path, monkeypatch):
    from app.graph import workflow

    (tmp_path / ".project-directory").write_text("app")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "go.mod").write_text("module notes\n\ngo 1.22\n")
    (tmp_path / "app" / "main.go").write_text("package main\n")
    eight = "".join(f"./main.go:{n}:2: undefined: name{n}\n" for n in range(1, 9))
    monkeypatch.setattr("app.stacks.scaffold.sandbox_runner",
                        lambda root: lambda argv, category, project: {"returncode": "1", "stdout": "", "stderr": eight})
    state = {"repository": SimpleNamespace(root_path=str(tmp_path))}

    found = workflow._diagnostics_in_files_touched(state, {"messages": []}, SimpleNamespace(changed_files=["app/main.go"]),
                                                   most=workflow.MOST_DIAGNOSTICS_FOR_A_PASS)

    assert len(found) == 8


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), "-c", "user.email=h@example.com", "-c", "user.name=h", *args],
                          check=True, capture_output=True, text=True).stdout.strip()


def _a_go_project_and_its_fix(root):
    (root / ".project-directory").write_text("app")
    (root / "app").mkdir()
    (root / "app" / "go.mod").write_text("module notes\n\ngo 1.22\n")
    (root / "app" / "main.go").write_text("package main\n\nfunc main() {\n}\n")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    base = _git(root, "rev-parse", "HEAD")
    (root / "app" / "main.go").write_text("package main\n\nfunc main() {\n\trender()\n}\n")  # the fix: line 4
    return base


def _measured(monkeypatch, root, compiler_says, before_problem="the product did not start: no server"):
    nothing_passes = ci.Snapshot(label="latest", unit={"u1": "failed"}, unit_ran=True, problem=before_problem)
    after = ci.Snapshot(label="after", unit={"u1": "failed"}, unit_ran=True,
                        problem="the product did not start: the build failed")
    monkeypatch.setattr(engineering, "ci_applies", lambda root: True)
    monkeypatch.setattr(ci, "load", lambda root, which: nothing_passes)
    monkeypatch.setattr(ci, "take", lambda root, label: after)
    monkeypatch.setattr("app.analysis.language_service.underlined_in", lambda *a, **k: {})
    monkeypatch.setattr("app.stacks.scaffold.sandbox_runner",
                        lambda root: lambda argv, category, project: {"returncode": "1", "stdout": "",
                                                                       "stderr": compiler_says})


def test_a_compiled_fix_that_adds_an_error_on_its_own_line_is_reverted(tmp_path, monkeypatch):
    base = _a_go_project_and_its_fix(tmp_path)
    _measured(monkeypatch, tmp_path, "./main.go:4:2: undefined: render\n")

    broke = engineering.after_a_fix(str(tmp_path), base, "defect_fix_1_1", "start the server")

    assert any("app/main.go" in item and "line 4" in item and "undefined: render" in item for item in broke), broke
    assert "render" not in (tmp_path / "app" / "main.go").read_text()


def test_a_compiler_error_the_build_already_had_is_not_the_fix_s(tmp_path, monkeypatch):
    base = _a_go_project_and_its_fix(tmp_path)
    _measured(monkeypatch, tmp_path, "./main.go:4:2: undefined: render\n",
              before_problem="the product did not start: ./main.go:7:2: undefined: render")

    assert engineering.after_a_fix(str(tmp_path), base, "defect_fix_1_1", "start the server") == []


def test_a_compiler_error_on_a_line_the_fix_did_not_write_is_not_the_fix_s(tmp_path, monkeypatch):
    base = _a_go_project_and_its_fix(tmp_path)
    _measured(monkeypatch, tmp_path, "./main.go:1:1: expected package clause\n")

    assert engineering.after_a_fix(str(tmp_path), base, "defect_fix_1_1", "start the server") == []
