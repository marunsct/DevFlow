"""A fix after which the unit tests no longer compile is reverted with the compiler's words first (LF.1620).

Measured on a C# run: three fixes of mutation findings each wrote a test that subclassed a class whose methods
cannot be overridden. The test project stopped compiling, every unit test "broke", and each revert said "broke 17
test(s) that passed before it" with the seventeen names and "(its runner's words were not kept)". The next fixers
read the names, never the error, and wrote the same subclass again.
"""
from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

from app import ci
from app.analysis import compiler_check
from app.graph import engineering, what_a_revert_broke

TEST_FILE = "tests/NotesTests.cs"
BEFORE = "public class NotesTests {\n    public void Lists() {}\n}\n"
AFTER = ("public class NotesTests {\n    public void Lists() {}\n"
         "    class Failing : Store { public override int Add() => 0; }\n}\n")
ERROR = "'NotesTests.Failing.Add()': cannot override inherited member 'Store.Add()' because it is not marked virtual"
DEFECT = SimpleNamespace(description="No test notices a deliberate change to `src/Store.cs` line 9: `==` made `!=`.",
                         source="mutation")


def _git(root, *args):
    return subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=root, check=True,
                          capture_output=True, text=True).stdout.strip()


def _a_fix_that_stops_the_unit_tests_compiling(root, monkeypatch, *, compiler_says):
    (root / "tests").mkdir()
    (root / TEST_FILE).write_text(BEFORE)
    (root / ".gitignore").write_text(".harness/\n")  # as every workspace's: the harness's records outlive a revert
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "before the fix")
    base = _git(root, "rev-parse", "HEAD")
    (root / TEST_FILE).write_text(AFTER)
    before = ci.Snapshot(label="before", unit_ran=True,
                         unit={"UnitTests › NotesTests.Lists": "passed", "UnitTests › NotesTests.Adds": "passed"})
    after = ci.Snapshot(label="after", unit={ci.UNIT_TESTS_DID_NOT_RUN: "failed"})
    monkeypatch.setattr(engineering, "ci_applies", lambda r: True)
    monkeypatch.setattr(ci, "load", lambda r, which="latest": before)
    monkeypatch.setattr(ci, "take", lambda r, label, **k: after)
    # The compiler, run in the sandbox: an unmanaged dependency, its answer stubbed.
    monkeypatch.setattr(compiler_check, "findings", lambda *a, **k: compiler_says)
    return base


def _reverted(root, base):
    return engineering.after_a_fix(
        str(root), base, "defect_fix_1_0", DEFECT.description,
        on_revert=lambda lost: what_a_revert_broke.record(root, base, DEFECT, "defect_fix_1_0", lost, "agent"))


def test_the_compiler_s_error_on_the_fix_s_own_line_comes_first_and_reaches_the_next_fixer(tmp_path, monkeypatch):
    base = _a_fix_that_stops_the_unit_tests_compiling(
        tmp_path, monkeypatch, compiler_says=[{"file": TEST_FILE, "line": 3, "message": ERROR, "code": "CS0506"}])

    broke = _reverted(tmp_path, base)

    assert ERROR in broke[0] and TEST_FILE in broke[0]
    assert (tmp_path / TEST_FILE).read_text() == BEFORE, "reverted as before"
    told = what_a_revert_broke.told(tmp_path, DEFECT)
    assert ERROR in told, "the next fixer of the defect reads the compiler's words"


def test_without_a_line_of_its_own_the_unit_run_s_own_words_come_first(tmp_path, monkeypatch):
    base = _a_fix_that_stops_the_unit_tests_compiling(tmp_path, monkeypatch, compiler_says=[])
    record = tmp_path / ci.UNIT_RUN_FILE
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps({"passed": False, "output": (
        f"Build started.\n{TEST_FILE}(3,49): error CS0506: {ERROR} [tests/UnitTests.csproj]\nBuild FAILED.\n")}))

    broke = _reverted(tmp_path, base)

    assert "unit tests no longer compile" in broke[0] and ERROR in broke[0] and TEST_FILE in broke[0]
