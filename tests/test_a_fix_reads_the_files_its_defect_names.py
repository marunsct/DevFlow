"""A rewrite takes the files the defect's own words name, not only those of its failure text.

Measured on one run: a failing unit run named its test file only in the description, a cross-file finding merged into
the defect brought the manifest as its one affected file, and six fixes rewrote the manifest and nothing else.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.graph.engineering import SAME_PROBLEM_ELSEWHERE
from app.graph.rewritten_fixes import files_to_fix


def _project(tmp_path):
    for name in ("shop/package.json", "shop/src/data.ts", "shop/test/data.test.ts", "shop/test/other.test.ts"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("x\n")
    return tmp_path


def _defect(root, merged=""):
    return SimpleNamespace(
        description=f"The unit tests fail. It says: Title is required ({root}/shop/test/data.test.ts)" + merged,
        affected_files=["shop/package.json"], actual_behavior="",
    )


def test_the_test_file_the_description_names_is_rewritten(tmp_path):
    root = _project(tmp_path)
    assert "shop/test/data.test.ts" in files_to_fix(_defect(root), "no file named here", root, lambda _: True)


def test_a_file_only_a_merged_finding_mentions_is_not_taken_from_it(tmp_path):
    root = _project(tmp_path)
    merged = SAME_PROBLEM_ELSEWHERE + "- [cross-file check] shop/test/other.test.ts is wrong"
    assert "shop/test/other.test.ts" not in files_to_fix(_defect(root, merged), "nothing", root, lambda _: True)
