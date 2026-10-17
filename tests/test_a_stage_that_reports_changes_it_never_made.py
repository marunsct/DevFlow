"""A stage whose answer names files nothing in it wrote has them dropped.

Measured on one run: asked by a re-planned milestone to cut a file it owned, a
stage read that file once and answered that it had removed a 30-line block,
replaced inline styles with classes and run the tests - none of which it did.
The file was unchanged, the milestone review blocked on the same size again,
and the record said the work order was delivered.

The clarification this used to send was itself a full model call - eleven a
day - and two measured stages doubled down anyway ("still reports changing
..., recorded without them"). The claim is dropped deterministically now, and
the warning line is the counting line for the per-model honesty signal
(Initiative Q.4).
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from langchain_core.messages import AIMessage, ToolMessage

from app.graph.workflow import _files_it_claims_but_never_wrote


def _call(name: str, call_id: str, **args) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "id": call_id, "args": args}])


def _result(call_id: str, content: dict | str) -> ToolMessage:
    return ToolMessage(content=content if isinstance(content, str) else json.dumps(content), tool_call_id=call_id)


def _answer(*files: str) -> SimpleNamespace:
    return SimpleNamespace(changed_files=list(files))


def test_a_file_only_read_is_named() -> None:
    result = {"messages": [
        _call("read_file", "1", file_path="app/main.js"),
        _result("1", "1  const a = 1;"),
    ]}

    assert _files_it_claims_but_never_wrote(result, _answer("app/main.js")) == ["app/main.js"]


def test_a_file_written_edited_or_moved_is_not() -> None:
    result = {"messages": [
        _call("write_artifact", "1", relative_path="app/a.js", content="x"),
        _result("1", {"path": "app/a.js", "status": "written"}),
        _call("replace_lines", "2", relative_path="./app/b.css", start_line=1, end_line=2, content="y"),
        _result("2", {"path": "app/b.css", "status": "edited"}),
        _call("move_artifact", "3", relative_path="app/c.js", destination="app/d.js"),
        _result("3", {"status": "moved"}),
    ]}

    assert _files_it_claims_but_never_wrote(result, _answer("app/a.js", "app/b.css", "app/d.js", "/app/c.js")) == []


def test_a_refused_write_does_not_count() -> None:
    result = {"messages": [
        _call("edit_artifact", "1", relative_path="app/a.js", find="x", replace="y"),
        _result("1", {"error": "Could not find that text in 'app/a.js'."}),
    ]}

    assert _files_it_claims_but_never_wrote(result, _answer("app/a.js")) == ["app/a.js"]


def test_a_file_a_command_names_is_not_judged() -> None:
    result = {"messages": [
        _call("run_terminal_command", "1", command=["npx", "prettier", "--write", "app/a.js"]),
        _result("1", {"returncode": "0"}),
    ]}

    assert _files_it_claims_but_never_wrote(result, _answer("app/a.js")) == []


def test_an_answer_without_the_field_is_not_judged() -> None:
    assert _files_it_claims_but_never_wrote({"messages": []}, SimpleNamespace()) == []
    assert _files_it_claims_but_never_wrote({"messages": []}, _answer()) == []


def test_a_phantom_claim_is_dropped_from_the_record() -> None:
    from pydantic import BaseModel

    from app.graph import workflow

    class Answer(BaseModel):
        changed_files: list[str] = []
        blockers: list[str] = []

    dropped = workflow._claims_dropped_from_the_record(
        Answer(changed_files=["app/a.js", "app/main.js"]), ["app/main.js"]
    )

    assert dropped.changed_files == ["app/a.js"]
    # The answer with nothing to drop comes back as it was.
    same = Answer(changed_files=["app/a.js"])
    assert workflow._claims_dropped_from_the_record(same, []) is same


def test_an_answer_of_the_wrong_shape_is_left_alone() -> None:
    from app.graph import workflow

    plain = SimpleNamespace(changed_files=["app/main.js"])

    assert workflow._claims_dropped_from_the_record(plain, ["app/main.js"]) is plain


def test_no_model_call_is_sent_about_a_phantom_claim() -> None:
    """The clarification was a full model call on the stage's own thread, and
    the two stages measured receiving it named the same file again; the drop
    answers it for nothing (Initiative Q.4)."""
    import inspect

    from app.graph import workflow

    source = inspect.getsource(workflow)

    assert "_ask_about_the_files_it_never_wrote" not in source
    assert "dropped from the record" in source


def test_a_report_its_test_commands_wrote_is_not_judged() -> None:
    """Measured on one run: a test round reporting the JUnit files its test
    commands wrote, at paths their configuration names, was asked what it had done."""
    ran = {"messages": [
        _call("run_terminal_command", "1", command=["npm", "run", "unit"], working_directory="notes-api"),
        _result("1", {"returncode": "0"}),
    ]}

    assert _files_it_claims_but_never_wrote(ran, _answer("notes-api/reports/unit.xml", "coverage/lcov.info")) == []
    assert _files_it_claims_but_never_wrote(ran, _answer("notes-api/src/store.ts")) == ["notes-api/src/store.ts"]


def test_without_a_command_a_report_is_judged_like_any_file() -> None:
    assert _files_it_claims_but_never_wrote({"messages": []}, _answer("notes-api/reports/unit.xml")) == ["notes-api/reports/unit.xml"]
