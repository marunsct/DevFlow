"""A write refused or noted for changing nothing counts as nothing new, so a stage writing the same files stops.

Measured on one gate run: an acceptance author wrote the same two files again
and again, each answered "the file already contains exactly this content", and
none counted toward the stall - it ran on toward its whole budget.
"""
from __future__ import annotations

from langchain_core.messages import AIMessage, ToolMessage

from app.agents.settled_answer import _nothing_new_lately

REFUSED = ('{"error": "Refusing this write: the file already contains exactly this content, and you have '
           'already been told that twice. Nothing was written and nothing would change if it were."}')
NOTED = "This file already contained exactly this content, so nothing was written."


def _turns(results):
    messages = []
    for index, (path, text) in enumerate(results):
        call = {"id": f"c{index}", "name": "write_artifact", "args": {"relative_path": path, "content": "same"}}
        messages += [AIMessage(content="", tool_calls=[call]), ToolMessage(content=text, tool_call_id=f"c{index}")]
    return messages


def test_writes_of_unchanged_files_stall_the_stage():
    results = [("a/auth.spec.js", NOTED), ("a/docs.spec.js", NOTED), ("a/auth.spec.js", REFUSED),
               ("a/docs.spec.js", REFUSED), ("a/auth.spec.js", REFUSED)]

    assert _nothing_new_lately(_turns(results))


def test_a_write_that_changed_a_file_is_new():
    results = [("a/auth.spec.js", REFUSED)] * 4 + [("a/docs.spec.js", '{"status": "written"}')]

    assert not _nothing_new_lately(_turns(results))
