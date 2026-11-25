"""A fixer is shown "what the last failing command printed" only when that command is about its defect (LF.1456).

Measured on 17 runs: 53 fix briefs carried the section, followed by "this is the machine's own output ... believe
this", and 45 of the 49 readable named none of the defect's files - an acceptance run of other tests for an import a
type checker underlined, forty `PASSED` lines for a service rule, a browser install the stack setup ran hours before,
a missing runner in another folder, and a refusal (exit -1) of a command that had passed three times.

Each record below is the real command, its real result and the real defect its fixer was shown it for.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

RECORDS = json.loads((Path(__file__).parent / "fixtures" / "evidence_records" / "last_failing_commands.json")
                     .read_text(encoding="utf-8"))


def _the_run(tmp_path, monkeypatch, rows: list[dict]) -> str:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))  # read at each call by `transcript_path`
    run_id = "run-shown"
    path = tmp_path / "transcripts" / f"{run_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    return run_id


def _defect(record: dict) -> SimpleNamespace:
    return SimpleNamespace(description=record["defect"], affected_files=record["affected_files"])


@pytest.mark.parametrize("record", RECORDS, ids=[f"{r['stage']}-{r['call']['args'].get('command', [''])[0]}"
                                                 for r in RECORDS])
def test_a_command_about_another_defect_is_not_shown_as_this_one_s(tmp_path, monkeypatch, record) -> None:
    from app.observability.transcript import last_failing_command

    run_id = _the_run(tmp_path, monkeypatch, [record["call"], record["result"]])

    assert last_failing_command(run_id, about=_defect(record)) is None


def _the_acceptance_run() -> dict:
    return next(r for r in RECORDS if r["call"]["args"].get("command") == ["npm", "run", "test:acceptance"])


def test_a_failing_command_whose_output_names_the_defect_s_file_is_shown(tmp_path, monkeypatch) -> None:
    """The same real acceptance run, for a defect in a file it ran."""
    from app.observability.transcript import last_failing_command

    record = _the_acceptance_run()
    run_id = _the_run(tmp_path, monkeypatch, [record["call"], record["result"]])
    defect = SimpleNamespace(description="[AC-12] POST /api/bookmarks - the acceptance suite says this does not work",
                             affected_files=["bookmarks/acceptance/api.spec.js"])

    found = last_failing_command(run_id, about=defect)

    assert found is not None and found["command"] == "npm run test:acceptance"


def test_a_failure_older_than_the_run_s_last_hour_is_not_shown(tmp_path, monkeypatch) -> None:
    """The browser install fixers were shown ran 3 h 38 min before them."""
    from app.observability.transcript import last_failing_command

    record = _the_acceptance_run()
    later = {"kind": "tool_call", "call_id": "later", "tool": "run_terminal_command", "args": {"command": ["ls"]},
             "stage": "defect_fix_2_0", "at": "2026-11-25T14:10:00+00:00"}
    later_result = {"kind": "tool_result", "call_id": "later", "at": "2026-11-25T14:10:01+00:00",
                    "content": json.dumps({"stdout": "", "stderr": "", "returncode": "0"})}
    run_id = _the_run(tmp_path, monkeypatch, [record["call"], record["result"], later, later_result])
    defect = SimpleNamespace(description="", affected_files=["bookmarks/acceptance/api.spec.js"])

    assert last_failing_command(run_id, about=defect) is None


def test_a_stage_s_inline_script_is_its_probe(tmp_path, monkeypatch) -> None:
    """One fixer's `python -c` failing on a missing configuration file was shown a later fixer as the product's."""
    from app.observability.transcript import last_failing_command

    call = {"kind": "tool_call", "call_id": "p", "tool": "run_terminal_command", "stage": "defect_fix_2_1",
            "args": {"command": ["python", "-c", "import json; json.load(open('app/routers/auth.py.json'))"]}}
    result = {"kind": "tool_result", "call_id": "p", "content": json.dumps(
        {"stdout": "", "stderr": "FileNotFoundError: [Errno 2] No such file or directory: 'app/routers/auth.py.json'",
         "returncode": "1"})}
    run_id = _the_run(tmp_path, monkeypatch, [call, result])
    defect = SimpleNamespace(description="", affected_files=["task-management-dashboard/backend/app/routers/auth.py"])

    assert last_failing_command(run_id, about=defect) is None
