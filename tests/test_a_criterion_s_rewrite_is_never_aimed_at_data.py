"""A criterion's rewrite is never aimed at the product's data or a document from failure text alone (HR2.fix.3).

63 of 259 files declined rewrites were asked to correct were test, scratch or data files - `input.txt` among them.
Tests and scratch were already left out for a criterion the suite judges; data and documents now are too, unless the
defect itself names them. A dependency manifest stays: a fix may have to change it.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.graph.rewritten_fixes import files_to_fix


def _workspace(tmp_path):
    for name in ("cli/wordstats/cli.py", "cli/input.txt", "cli/notes.md", "cli/requirements.txt"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("x\n")
    return tmp_path


def test_a_criterion_s_failure_naming_its_data_rewrites_the_code(tmp_path) -> None:
    defect = SimpleNamespace(description="[AC-3] counts the words of a file", affected_files=[])
    failure = 'File "cli/wordstats/cli.py", line 4, in main\n  reading cli/input.txt and cli/notes.md\nAssertionError'
    assert files_to_fix(defect, failure, _workspace(tmp_path), lambda path: True) == ["cli/wordstats/cli.py"]


def test_a_defect_that_names_its_data_file_keeps_it(tmp_path) -> None:
    defect = SimpleNamespace(description="[AC-3] counts the words of a file", affected_files=["cli/input.txt"])
    found = files_to_fix(defect, 'File "cli/wordstats/cli.py", line 4', _workspace(tmp_path), lambda path: True)
    assert "cli/input.txt" in found


def test_a_dependency_manifest_is_still_a_file_a_fix_may_change(tmp_path) -> None:
    defect = SimpleNamespace(description="[AC-1] the service starts", affected_files=[])
    failure = "ModuleNotFoundError: No module named 'falcon' - add it to cli/requirements.txt"
    assert "cli/requirements.txt" in files_to_fix(defect, failure, _workspace(tmp_path), lambda path: True)
