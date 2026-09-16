"""The failing command's own output, in the brief that asks for a fix.

run-d3965815's `defect_fix_2_1` was briefed to fix a "Syntax error in
createElementFallback causing renderTasks failure ... Observe stderr showing
Unexpected token '}'". There was no syntax error in that file. The suite was
failing with an assertion at `app.test.mjs:50` and, a round later, a
`ReferenceError`. The brief was the reporting specialist's prose reading of a
failure it had seen earlier, and the fixer spent its stage looking for
something that was not there. Three remediation rounds, defect unmoved.

The machine's own words were on disk the whole time: the transcript records
every `run_terminal_command` result verbatim.
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
