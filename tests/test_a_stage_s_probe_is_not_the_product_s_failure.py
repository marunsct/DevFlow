"""A stage's throwaway probe is neither the product's failure nor a file to fix.

Measured live: a fixer wrote `tmp-check-auth-service.py` to try an import,
and it failed on its own import path. It was then the run's last failing
command, so two later fixes of other defects were briefed with its
traceback, rewrote the probe, and were recorded as having fixed them.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from app.graph.rewritten_fixes import files_to_fix


def _transcript(tmp_path, monkeypatch, rows):
    from app.observability import transcript

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(transcript, "_DATA_DIR", None, raising=False)
    path = tmp_path / "transcripts" / "run-probe.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return transcript


def _ran(call_id, argv, returncode, stderr=""):
    return [
        {"kind": "tool_call", "call_id": call_id, "tool": "run_terminal_command",
         "args": {"command": argv}, "stage": "defect_fix_2_1"},
        {"kind": "tool_result", "call_id": call_id,
         "content": json.dumps({"stdout": "", "stderr": stderr, "returncode": str(returncode)})},
    ]


def test_a_failing_probe_is_not_the_last_failure(tmp_path, monkeypatch):
    transcript = _transcript(tmp_path, monkeypatch, [
        *_ran("a", ["pytest", "tests/test_search.py"], 1, "AssertionError: search returned nothing"),
        *_ran("b", ["python", "app/tmp-check-imports.py"], 1, "ModuleNotFoundError: No module named 'x'"),
    ])

    found = transcript.last_failing_command("run-probe")

    assert found is not None
    assert found["command"] == "pytest tests/test_search.py"


def test_a_product_command_still_counts(tmp_path, monkeypatch):
    transcript = _transcript(tmp_path, monkeypatch, [
        *_ran("a", ["node", "server/app.js"], 1, "SyntaxError: Unexpected token"),
    ])

    assert transcript.last_failing_command("run-probe")["command"] == "node server/app.js"


def test_a_probe_the_failure_names_is_not_rewritten(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "tmp-check-auth.py").write_text("import x\n", encoding="utf-8")
    (tmp_path / "app" / "search.py").write_text("def search(): return []\n", encoding="utf-8")
    failure = 'File "app/tmp-check-auth.py", line 1\nFile "app/search.py", line 1'

    found = files_to_fix(SimpleNamespace(affected_files=[]), failure, tmp_path, lambda _: True)

    assert found == ["app/search.py"]


def test_a_criterion_the_suite_judges_is_never_fixed_in_a_unit_test(tmp_path):
    """Measured live: a login criterion's rewrite rewrote `tests/test_auth.py`,
    named by the run's last failing command, and was recorded as fixed."""
    (tmp_path / "app" / "tests").mkdir(parents=True)
    (tmp_path / "app" / "tests" / "test_auth.py").write_text("def test_login(): pass\n", encoding="utf-8")
    (tmp_path / "app" / "login.py").write_text("def login(): return None\n", encoding="utf-8")
    failure = 'File "app/tests/test_auth.py", line 1\nFile "app/login.py", line 1'
    criterion = SimpleNamespace(affected_files=[], description="[AC-1] Sign-in - the acceptance suite says this does not work yet.")
    unit_failure = SimpleNamespace(affected_files=[], description="The unit tests fail.")

    assert files_to_fix(criterion, failure, tmp_path, lambda _: True) == ["app/login.py"]
    assert files_to_fix(unit_failure, failure, tmp_path, lambda _: True) == ["app/tests/test_auth.py", "app/login.py"]
