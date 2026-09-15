"""Withdrawn. Kept for the record of why it did not work.

NOT WIRED INTO ANY AGENT. `create_role_agent` no longer installs this.

The idea was that a stage answering in prose had simply lost sight of the
requirement, hundreds of messages back, so restating it near the end would
help. Two things were wrong with that.

It cannot be timed. `wrap_model_call` runs *before* a model call, so it has no
way to know the model is about to finish; it fired on every call once the
conversation passed a threshold and hoped one of them was the last.

And firing mid-work has a plausible cost that matches what was actually
observed. A model repeatedly told "return your answer now" while it is still
working may announce an answer it has not formed - which is exactly the failure
shape in the logs: "Here is my structured response:" followed by nothing.

Measured, as far as it can be: run-61c5a5b6 ran without this and retried twice
in 17 stage entries (12%). run-2b5def74 ran with it and retried five times in
26 (19%). That is not proof - different work, small numbers - but there is no
evidence of benefit on either side of it, and a change carries the burden of
justifying itself.

What replaced it is correctly timed by construction:
`_nudge_for_the_structured_response` fires only after a stage has ended without
a structured response, and `_answer_written_into_the_conversation` recovers an
answer the model already produced. Both act on a fact rather than a guess.

Removing it also makes the next run a cleaner experiment: one uncontrolled
variable fewer when measuring whether the salvage works.

Original docstring follows.

Keep the response schema in view in a conversation that has grown long.

Measured on run-61c5a5b6: two stages of about twenty-five produced no
structured response, and both were among the longest in the run -
`test_round_0` after 38 file reads, `specialist_ui_ux_1` after 203 events. Both
wrote the answer into the conversation as prose, one of them opening with
"Here's my structured response:" and then not returning one. The instruction to
use the schema is in the system prompt, hundreds of messages earlier.

`app.graph.workflow` recovers from this by asking the same conversation again,
which is cheap and works. This is the other half: making the first attempt more
likely to be right, by putting the requirement back in front of the model when
the conversation is long enough for the original to have receded.

The reminder is injected into the request in flight and never written to state,
so it does not accumulate - a conversation of forty turns carries one reminder,
not forty.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

#: Below this a conversation is short enough that the system prompt is still
#: close, and a reminder would be noise on every single call.
DEFAULT_AFTER_MESSAGES = 24

REMINDER = (
    "Reminder, because this conversation has grown long: when you are done, "
    "return your answer through the response schema. Prose written into the "
    "conversation is not returned to the workflow - a stage that answers in "
    "text has delivered nothing, however complete the text is."
)


def _threshold() -> int:
    try:
        return max(1, int(os.environ.get("RESPONSE_REMINDER_AFTER_MESSAGES", "")))
    except (TypeError, ValueError):
        return DEFAULT_AFTER_MESSAGES


def build_response_reminder_middleware(after_messages: int | None = None) -> Any:
    """Middleware that restates the response requirement in a long conversation."""
    from langchain.agents.middleware import AgentMiddleware

    threshold = after_messages if after_messages is not None else _threshold()

    class ResponseReminderMiddleware(AgentMiddleware):
        """Append the reminder to the request, not to the stored history."""

        name = "ResponseReminderMiddleware"

        def wrap_model_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
            messages = getattr(request, "messages", None)
            if not isinstance(messages, list) or len(messages) < threshold:
                return handler(request)
            # A stage with no structured output to give - there is nothing for
            # the reminder to be about, and saying it anyway invites the model
            # to invent a schema it was not given.
            if getattr(request, "response_format", None) is None:
                return handler(request)
            try:
                request = request.override(
                    messages=[*messages, {"role": "user", "content": REMINDER}]
                )
            except Exception:  # noqa: BLE001 - a reminder must never fail a call
                return handler(request)
            return handler(request)

    return ResponseReminderMiddleware()


__all__ = [
    "DEFAULT_AFTER_MESSAGES",
    "REMINDER",
    "build_response_reminder_middleware",
]
