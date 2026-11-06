"""A run is scored against the benchmark whose brief it was started from, not the last one started on the host.

Measured on one run: two ports ran different families; `loop.sh score` took the benchmark from the brief last
started, scored a web-todo product against the full-stack benchmark's hidden tests, and the hidden tests could not
even start it.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("brief_match", ROOT / "scripts" / "bench" / "brief_match.py")
brief_match = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(brief_match)


def _benchmarks(tmp_path):
    for name, text in (("web-todo", "# Todo\nA list of things to do.\n"),
                       ("fullstack-bookmarks-py", "# Bookmarks\nA web app for saving links.\n")):
        (tmp_path / name / "hidden").mkdir(parents=True)
        (tmp_path / name / "brief.md").write_text(text)
    return tmp_path


def test_the_benchmark_whose_brief_the_run_was_started_from(tmp_path):
    root = _benchmarks(tmp_path)
    assert brief_match.benchmark_of("# Todo\r\nA list of things to do.", root) == "web-todo"
    assert brief_match.benchmark_of("# Bookmarks\nA web app for saving links.", root) == "fullstack-bookmarks-py"


def test_a_brief_no_benchmark_holds_names_none(tmp_path):
    assert brief_match.benchmark_of("# Something else entirely", _benchmarks(tmp_path)) == ""


def test_the_real_benchmarks_name_themselves():
    for brief in sorted((ROOT / "benchmarks").glob("*/brief.md")):
        if (brief.parent / "hidden").is_dir():
            assert brief_match.benchmark_of(brief.read_text(), ROOT / "benchmarks") == brief.parent.name
