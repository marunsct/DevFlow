"""After a summary, a file the project memory holds whole is named as held, and the digest's calls say where they
are counted from (LF.1424).

Measured on one medium run's fixer: after a summary the stage was told its database module was among the "Files this
stage has read so far, whose text is no longer in this conversation" while the project memory held it whole; the
summary's next step was "Read database.py", and the fixer asked for it six times running, each answered with a
pointer to the memory. The digest at the end of each call then listed that pointer as "database.py (call 2)", and
after a summary its "(call 2)" named a call the summary had deleted.
"""
from __future__ import annotations

import re

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agents.compaction import FILES_READ, KEPT_REQUEST, files_read_line, with_held_reads_named
from app.agents.workspace_digest import already_known

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
READ = {"svc/routes/auth.py": [[1, 278]], "svc/database.py": [[1, 134]]}
POINTER = ("`svc/database.py` is in the project memory at the start of this conversation, whole and as it is now; "
           "it has not changed since.")


def _summary_message() -> HumanMessage:
    return HumanMessage(content="The request.\n\n## Left\n1. Read database.py\n\n" + files_read_line(READ),
                        additional_kwargs={FILES_READ: READ, KEPT_REQUEST: "The request.",
                                           "lc_source": "summarization"})


def test_a_file_the_memory_holds_is_named_as_held_not_as_gone():
    line = files_read_line(READ, held=["svc/database.py"])

    gone, _, held = line.partition("project memory")
    assert "`svc/routes/auth.py` (lines 1-278)" in gone and "svc/database.py" not in gone
    assert "`svc/database.py`" in held
    assert not BANNED.search(line)


def test_the_summary_in_the_request_is_rewritten_with_what_the_memory_holds_on_this_call():
    messages = [_summary_message(), AIMessage(content="Reading on.")]

    sent = with_held_reads_named(messages, ["svc/database.py", "docs/acceptance_criteria.md"])

    said = sent[0].content
    assert "whose text is no longer in this conversation: `svc/routes/auth.py` (lines 1-278)." in said
    assert "do not read them again: `svc/database.py`." in said
    assert sent[1] is messages[1]


def test_with_nothing_held_the_request_is_left_as_it_is():
    messages = [_summary_message()]
    assert with_held_reads_named(messages, ["docs/other.md"]) is messages


def _a_read(call: str, path: str, result: str) -> list:
    return [AIMessage(content="", tool_calls=[{"id": call, "name": "read_file", "args": {"file_path": path}}]),
            ToolMessage(content=result, tool_call_id=call)]


def test_a_read_answered_by_the_memory_is_not_named_as_in_this_conversation():
    known = already_known([HumanMessage(content="Fix it."),
                           *_a_read("a", "svc/routes/auth.py", "     1  import x\n     2  import y"),
                           *_a_read("b", "svc/database.py", POINTER)])

    assert "svc/routes/auth.py (call 1" in known
    assert "svc/database.py" not in known


def test_after_a_summary_the_calls_are_said_to_be_counted_from_it():
    known = already_known([_summary_message(), *_a_read("a", "svc/routes/auth.py", "     1  import x")])

    assert "calls counted from its summary" in known
    assert not BANNED.search(known)


def test_without_a_summary_the_calls_are_counted_as_before():
    known = already_known([HumanMessage(content="Fix it."), *_a_read("a", "svc/routes/auth.py", "     1  import x")])

    assert "Files already in this conversation (scroll up rather than read again): svc/routes/auth.py (call 1" in known
