"""An explicit plan a stage keeps, opt-in and unproven.

`langchain` ships `TodoListMiddleware`, which adds a `write_todos` tool and a
`todos` state channel. Its tool is a `StructuredTool` with a synchronous
implementation, so unlike the MCP tools of Part II it works in this harness's
synchronous control plane - confirmed against the installed package, not just
the documentation.

**No measurement supports it yet, and this module says so rather than
pretending otherwise.** The waste this harness actually measures is repeated
*calls*: 1,134 failed tool results in 9,632 across the 50 stored transcripts,
of which `edit_artifact` text-matching failures are 37%, and 30% of reads
fetching bytes an earlier stage already had. A task list reduces none of
those directly. The two most expensive runaway stages - `specialist_testing_2`
at 170 tool calls and `specialist_ui_ux_0` at 175 - were in edit-run-edit-run
loops on a failing suite, where every iteration is a different attempt at the
*same* task. A list with "fix the failing test" marked in-progress would have
been accurate the whole way down.

There is also a cost. `write_todos` is a model call, and the default prompt
that ships with the middleware says in as many words that for objectives of
fewer than three steps it is better not to use the tool - while the median
stage here takes 3 to 12 tool calls. On a stage with a 40-call budget, a plan
written and revised four times is 10% of the budget spent on planning.

So: off by default, `HARNESS_TASK_LIST=true` to turn it on, and §25 of the
hardening plan records the experiment that decides whether it stays.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

#: Written rather than taken from the default, which is addressed to a chat
#: assistant deciding whether a task is worth tracking. This is addressed to a
#: stage with a fixed job, a plan it did not write and a call budget.
TASK_LIST_PROMPT = """## Keeping a task list

You have `write_todos`. Use it to track the work of THIS stage.

- The sprint plan you were given is the task list. Copy its items for this
  stage; do not invent a different plan, and do not restate the whole sprint.
- Write it once, at the start, and then leave it alone except to mark
  progress. A plan rewritten every turn is a plan that is being used as a
  notepad, and every rewrite is a model call out of this stage's budget.
- Mark a task `completed` when its evidence exists - the test passes, the
  command succeeds, the file does what the task said it would. Not when you
  have written the file. "Written" and "works" are the two things every later
  stage has to tell apart, and marking the first as the second is how a stage
  reports finished work that does not run.
- If you cannot finish a task, leave it `in_progress` and say why in your
  structured response. Do NOT delete it and do not reword it to match what
  you managed to do. A plan edited to fit the outcome tells the next stage
  nothing, and the next stage is the one that has to pick this up.
- For a stage of one or two steps, skip the tool. Writing a list costs a call
  and tracking two things needs no list.

The list is not the answer. Whatever the workflow asked you for still has to
come back as your structured response; marking the last task complete
delivers nothing by itself."""


def task_list_enabled() -> bool:
    """Whether stages keep an explicit task list. Off unless asked for."""
    return os.environ.get("HARNESS_TASK_LIST", "false").strip().lower() in {
        "1", "true", "yes", "on",
    }


def build_task_list_middleware() -> list[Any]:
    """`[TodoListMiddleware]` when it is switched on, `[]` otherwise.

    A list rather than an optional value so the caller splices it into the
    chain without a conditional, the way the settled-answer middleware is
    already spliced.

    Never raises. A langchain that does not ship this middleware must not
    stop a stage being built: the harness worked without it yesterday.
    """
    if not task_list_enabled():
        return []
    try:
        from langchain.agents.middleware import TodoListMiddleware
    except Exception:  # noqa: BLE001 - an absent middleware is not a failure
        logger.warning(
            "HARNESS_TASK_LIST is on but this langchain has no TodoListMiddleware; "
            "stages will run without a task list.",
            exc_info=True,
        )
        return []
    return [TodoListMiddleware(system_prompt=TASK_LIST_PROMPT)]


__all__ = ["TASK_LIST_PROMPT", "build_task_list_middleware", "task_list_enabled"]
