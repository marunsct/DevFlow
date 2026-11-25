"""A defect a test round raises in its own words carries the error its own commands printed (FX.8, LF.1412).

Measured on a medium run: the first test round's command results held
`AttributeError: 'SQLiteTypeCompiler' object has no attribute 'visit_ARRAY'` word for word, and the round raised the
defect as "SQLAlchemy ARRAY type blocks SQLite table creation in test fixtures". No fixer was shown the error, and
the lookup for a stuck defect, which needs an error line, never built a query. Another round named its error as
"sqlalchemy.exc.InvalidRequestError." with no message, which was not read as an error at all.
"""
from __future__ import annotations

import json

import pytest

import workflow_nodes
from app.acceptance.what_went_wrong import the_errors_stated
from app.observability import transcript

RUN = "run-printed-errors"
PRINTED = (
    "...........EEEE....\n"
    "___ ERROR at setup of TestRegister.test_register_success ___\n"
    "    def _compiler_dispatch(self, visitor, **kw):\n"
    ">           meth = getter(visitor)\n"
    "E           AttributeError: 'SQLiteTypeCompiler' object has no attribute 'visit_ARRAY'. Did you mean: "
    "'visit_REAL'?\n"
    ".venv/lib/python3.12/site-packages/sqlalchemy/sql/visitors.py:124: AttributeError\n"
    "E           KeyError: 'session_token'\n"
    "4 errors in 1.2s\n"
)


@pytest.fixture
def a_run(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("RUN_TRANSCRIPT", "true")
    monkeypatch.setattr(workflow_nodes, "CONFIG", {"configurable": {"thread_id": "t", "run_id": "r",
                                                                    "app_run_id": RUN}})
    return tmp_path


def _ran(stage: str, output: str, code: int = 1) -> None:
    """One command of `stage` and what it printed, as the transcript records them."""
    transcript.record(RUN, stage, "tool_call", tool="run_validation", call_id=f"{stage}-{len(output)}",
                      args={"command": "npm test"})
    transcript.record(RUN, stage, "tool_result", tool="run_validation", call_id=f"{stage}-{len(output)}",
                      content=json.dumps({"command": ["npm", "test"], "returncode": code, "stdout": output}))


def _raised(tmp_path, description: str, actual: str = "The fixtures cannot create the tables."):
    found = [workflow_nodes.reported(description, owner="database", actual_behavior=actual)]
    # The run the ledger records it under, as a graph run's config names it.
    with transcript.asked_for("test_round_1", RUN):
        update, _ = workflow_nodes.a_test_round(tmp_path, found)
    return update["remediation"].defects[-1]


def test_a_round_s_defect_in_its_own_words_carries_the_error_its_commands_printed(a_run):
    _ran("test_round_1", PRINTED)

    defect = _raised(a_run, "SQLAlchemy ARRAY type blocks SQLite table creation in test fixtures")

    assert "AttributeError: 'SQLiteTypeCompiler' object has no attribute 'visit_ARRAY'" in defect.actual_behavior
    # Only the error its words match: another error of the same output is another defect's.
    assert "session_token" not in defect.actual_behavior
    # The ledger's record of it says which error it carries, so an audit can count defects raised with one.
    raised = [e for e in transcript.read_transcript(RUN, {"defect"}) if e.get("event") == "raised"]
    assert "visit_ARRAY" in raised[-1]["error_as_printed"]


def test_a_defect_that_matches_no_printed_error_is_left_as_raised(a_run):
    _ran("test_round_1", PRINTED)

    defect = _raised(a_run, "The page title is missing on the home view")

    assert defect.actual_behavior == "The fixtures cannot create the tables."


def test_a_defect_that_states_its_error_already_is_left_as_raised(a_run):
    _ran("test_round_1", PRINTED)
    stated = "TypeError: cannot read the ARRAY column of SQLite table creation"

    defect = _raised(a_run, "SQLAlchemy ARRAY type blocks SQLite table creation in test fixtures", actual=stated)

    assert defect.actual_behavior == stated


def test_what_an_earlier_visit_of_the_same_round_printed_is_not_attached(a_run):
    """A sprint planned again runs a round of the same name again, on another product."""
    _ran("test_round_1", PRINTED)
    _ran("defect_fix_1_0", "ok", code=0)
    _ran("test_round_1", "2 failed: expected 3 items, found 2\nAssertionError: expected 3, received 2\n")

    defect = _raised(a_run, "SQLAlchemy ARRAY type blocks SQLite table creation in test fixtures")

    assert "visit_ARRAY" not in defect.actual_behavior


@pytest.mark.parametrize("line", [
    "The fixtures fail with sqlalchemy.exc.InvalidRequestError.",
    "It stops at java.lang.IllegalStateException when the pool starts",
])
def test_a_dotted_exception_name_with_no_message_is_an_error_line(line):
    assert the_errors_stated(line) == [line]


@pytest.mark.parametrize("line", ["Internal Server Error", "an Error here", "see file.Error for details"])
def test_a_bare_error_word_is_still_not_an_error_line(line):
    assert the_errors_stated(line) == []
