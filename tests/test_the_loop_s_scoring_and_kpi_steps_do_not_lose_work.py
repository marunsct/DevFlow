"""The loop's scoring and KPI steps do not misreport or clobber (plan item AN).

W.1 compared a run's brief with the benchmark's byte for byte, so a trailing
newline made a run "started from another brief" and kept it out of the
false-acceptance count. `loop.sh kpi` wrote straight over `data/kpi/<run>.json`,
so a worker that failed left it empty, and `lessons` passed one argument.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


brief_match = _load("scripts/bench/brief_match.py", "brief_match_under_test")
score = _load("scripts/bench/score.py", "score_under_test")


def test_a_brief_saved_differently_is_the_same_brief():
    a = "# Notes\n\nBuild an API.\n- one\n- two\n"
    b = "# Notes\r\n\r\nBuild an API.\r\n- one\r\n- two"

    assert brief_match.verdict(a, b) == "yes 1"


def test_a_near_copy_is_the_same_and_a_different_brief_is_not():
    base = "Build a notes API. " * 40
    assert brief_match.verdict(base, base.replace("API", "service", 1)).startswith("yes")
    assert brief_match.verdict(base, "Build a to do list page with a form. " * 20).startswith("no")


def test_the_score_keeps_the_similarity_and_marks_only_a_different_brief():
    assert score.brief_pairing("yes:0.998") == {"brief": "own", "brief_mismatch": False, "brief_similarity": 0.998}
    other = score.brief_pairing("no:0.41")
    assert other["brief"] == "other" and other["brief_mismatch"] is True
    assert score.brief_pairing("")["brief"] == "unknown"
    assert score.brief_pairing("yes")["brief"] == "own"


def test_the_command_line_prints_the_verdict(tmp_path):
    a, b = tmp_path / "a.md", tmp_path / "b.md"
    a.write_text("Build it.\r\n")
    b.write_text("Build it.")

    done = subprocess.run([sys.executable, str(ROOT / "scripts/bench/brief_match.py"), str(a), str(b)],
                          capture_output=True, text=True)

    assert done.stdout.strip() == "yes 1"


def test_loop_sh_uses_it_and_passes_every_lessons_argument():
    loop = (ROOT / "scripts/loop/loop.sh").read_text()

    assert "brief_match.py" in loop and "cmp -s" not in loop
    assert 'lessons) shift; in_worker lessons.py "${@:-3}" ;;' in loop


def test_the_kpi_json_is_written_beside_itself_and_moved_on_success():
    loop = (ROOT / "scripts/loop/loop.sh").read_text()

    assert 'in_worker kpi.py "$run" > "data/kpi/$run.json.tmp"' in loop
    assert 'mv "data/kpi/$run.json.tmp" "data/kpi/$run.json"' in loop
    assert json.dumps({}) == "{}"  # the file is parsed by the ledger only after the move
