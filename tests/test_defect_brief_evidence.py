"""The failing command's own output, in the brief that asks for a fix.

One run's `defect_fix_2_1` was briefed to fix a "Syntax error in
createElementFallback causing renderTasks failure ... Observe stderr showing
Unexpected token '}'". There was no syntax error in that file. The suite was
failing with an assertion at `app.test.mjs:50` and, a round later, a
`ReferenceError`. The brief was the reporting specialist's prose reading of a
failure it had seen earlier, and the fixer spent its stage looking for
something that was not there. Three remediation rounds, defect unmoved.

The machine's own words were on disk the whole time: the transcript records
every command a stage runs, with its result, verbatim. A failure the same
command has passed since is not handed over: it is no longer the truth.
"""

from __future__ import annotations

import json

import pytest

from app.agents.specialists import build_defect_fix_request


def _brief(**kwargs) -> str:
    request = build_defect_fix_request(
        kwargs.pop("description", "Syntax error in createElementFallback"),
        kwargs.pop("reproduction_steps", "Run node todo-app/app.test.mjs"),
        kwargs.pop("expected_behavior", "renders two items"),
        kwargs.pop("actual_behavior", "Unexpected token '}'"),
        kwargs.pop("affected_files", ["todo-app/app.js"]),
        True,
        "/",
        None,
        kwargs.pop("observed", None),
    )
    return request["messages"][0]["content"]


def test_the_output_reaches_the_fixer() -> None:
    brief = _brief(
        observed={
            "command": "node --test ./app.test.mjs",
            "output": "AssertionError: renderTasks should create two items\n0 !== 2",
            "at": "2026-09-16T14:43:40+00:00",
            "stage": "implementation",
        }
    )

    assert "node --test ./app.test.mjs" in brief
    assert "0 !== 2" in brief
    # And the prose stays: it carries which failure matters.
    assert "Syntax error in createElementFallback" in brief


def test_the_fixer_is_told_which_to_believe() -> None:
    brief = _brief(observed={"command": "npm test", "output": "boom"})

    assert "Where the two disagree, believe this" in brief


@pytest.mark.parametrize("observed", [None, {}, {"command": "npm test", "output": ""}])
def test_a_brief_with_nothing_recorded_is_unchanged(observed) -> None:
    """Transcripts can be switched off, and a run can fail before any command."""
    brief = _brief(observed=observed)

    assert "What the last failing command actually printed" not in brief
    assert "A test failure has been assigned to you to fix." in brief


def test_the_transcript_reader_finds_the_last_failure(tmp_path, monkeypatch) -> None:
    from app.observability import transcript

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(transcript, "_DATA_DIR", None, raising=False)
    run_id = "run-test-0001"
    path = tmp_path / "transcripts" / f"{run_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {"kind": "tool_call", "call_id": "a", "tool": "run_terminal_command",
         "args": {"command": ["npm", "test"]}, "stage": "implementation"},
        # `returncode` really does arrive as a string; matching only the bare
        # integer form found nothing at all, silently.
        {"kind": "tool_result", "call_id": "a",
         "content": json.dumps({"stdout": "1 passing", "stderr": "", "returncode": "0"})},
        {"kind": "tool_call", "call_id": "b", "tool": "run_terminal_command",
         "args": {"command": ["node", "--test", "."]}, "stage": "implementation"},
        {"kind": "tool_result", "call_id": "b", "at": "2026-09-16T14:43:40+00:00",
         "content": json.dumps(
             {"stdout": "not ok 1", "stderr": "ReferenceError: mockList is not defined",
              "returncode": "1"})},
        # A refusal is the harness declining, not the project failing.
        {"kind": "tool_call", "call_id": "c", "tool": "run_terminal_command",
         "args": {"command": ["node", "-e", "1"]}, "stage": "implementation"},
        {"kind": "tool_result", "call_id": "c",
         "content": json.dumps({"error": "'node -e' is not permitted"})},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    found = transcript.last_failing_command(run_id)

    assert found is not None
    assert found["command"] == "node --test ."
    assert "mockList is not defined" in found["output"]
    assert "not ok 1" in found["output"]


def test_no_run_id_means_no_lookup() -> None:
    from app.observability.transcript import last_failing_command

    assert last_failing_command(None) is None
    assert last_failing_command("") is None


def _transcript(tmp_path, monkeypatch, *results) -> str:
    """A run whose transcript holds `(tool, command, returncode, stdout)` results in order."""
    from app.observability import transcript

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(transcript, "_DATA_DIR", None, raising=False)
    run_id = "run-test-0002"
    path = tmp_path / "transcripts" / f"{run_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for n, (tool, command, code, stdout) in enumerate(results):
        rows.append({"kind": "tool_call", "call_id": f"c{n}", "tool": tool,
                     "args": {"command": command}, "stage": f"stage_{n}"})
        rows.append({"kind": "tool_result", "call_id": f"c{n}",
                     "content": json.dumps({"stdout": stdout, "stderr": "", "returncode": code})})
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return run_id


def test_a_failure_the_same_command_has_passed_since_is_not_handed_over(tmp_path, monkeypatch) -> None:
    """One run's fixer was told to believe a 47-test unit failure over the
    report; the suite had since grown to 61 and passed, through another tool."""
    from app.observability.transcript import last_failing_command

    run_id = _transcript(
        tmp_path, monkeypatch,
        ("run_terminal_command", ["npm", "test"], "1", "tests 47\nfail 1"),
        ("run_validation", ["npm", "test"], 0, "tests 61\nfail 0"),
    )

    assert last_failing_command(run_id) is None


def test_every_tool_that_runs_a_command_is_read(tmp_path, monkeypatch) -> None:
    from app.observability.transcript import last_failing_command

    run_id = _transcript(
        tmp_path, monkeypatch,
        ("run_terminal_command", ["npm", "test"], "0", "tests 61"),
        ("run_validation", ["npm", "run", "check"], 1, "22 failed\n10 passed"),
    )

    found = last_failing_command(run_id)
    assert found is not None and found["command"] == "npm run check"
    assert "22 failed" in found["output"]


def test_a_command_spelled_from_another_directory_is_the_same_command(tmp_path, monkeypatch) -> None:
    from app.observability.transcript import last_failing_command

    run_id = _transcript(
        tmp_path, monkeypatch,
        ("run_terminal_command", "npm test", "1", "fail 1"),
        ("run_terminal_command", ["cd", "the-app", "&&", "npm", "test"], "0", "fail 0"),
    )

    assert last_failing_command(run_id) is None


def test_a_command_still_failing_is_found_behind_one_that_recovered(tmp_path, monkeypatch) -> None:
    from app.observability.transcript import last_failing_command

    run_id = _transcript(
        tmp_path, monkeypatch,
        ("run_terminal_command", ["make", "unit"], "2", "AssertionError: 0 !== 2"),
        ("run_terminal_command", ["make", "lint"], "1", "lint: 3 problems"),
        ("run_validation", ["make", "lint"], "0", "lint: clean"),
    )

    found = last_failing_command(run_id)
    assert found is not None and found["command"] == "make unit"
    assert "0 !== 2" in found["output"]


def test_a_result_without_a_command_is_no_failure(tmp_path, monkeypatch) -> None:
    """A file read that happens to contain an exit code ran nothing."""
    from app.observability.transcript import last_failing_command

    run_id = _transcript(
        tmp_path, monkeypatch,
        ("read_file", None, "1", '{"returncode": 1}'),
    )

    assert last_failing_command(run_id) is None
