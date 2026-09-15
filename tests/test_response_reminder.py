"""Make the first attempt more likely to be right, not just the recovery cheap.

Run-61c5a5b6 lost two stages of about twenty-five to a prose answer, and both
were among its longest: `test_round_0` after 38 file reads, `specialist_ui_ux_1`
after 203 events. One of them opened "Here's my structured response:" and then
wrote prose - it knew what was wanted and the requirement had simply receded
hundreds of messages into the past.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.response_reminder import (
    REMINDER,
    build_response_reminder_middleware,
)


class _Request:
    """Minimal stand-in for ModelRequest: a message list and `.override()`."""

    def __init__(self, count, response_format="schema"):
        self.messages = [{"role": "user", "content": f"m{i}"} for i in range(count)]
        self.response_format = response_format

    def override(self, **changes):
        clone = _Request(0, self.response_format)
        clone.messages = changes.get("messages", self.messages)
        return clone


def _seen(request):
    """Run the middleware and return the messages the model would receive."""
    captured = {}

    def handler(final):
        captured["messages"] = final.messages
        return SimpleNamespace(result=[])

    build_response_reminder_middleware(after_messages=10).wrap_model_call(request, handler)
    return captured["messages"]


def test_a_short_conversation_is_left_alone():
    """The system prompt is still close; a reminder on every call is noise."""
    messages = _seen(_Request(4))

    assert all(REMINDER not in str(m) for m in messages)


def test_a_long_conversation_is_reminded():
    messages = _seen(_Request(40))

    assert REMINDER in str(messages[-1])


def test_the_reminder_says_what_prose_costs():
    """"Use the schema" alone does not explain why the model should care."""
    assert "not returned to the workflow" in REMINDER
    assert "has delivered nothing" in REMINDER


def test_the_reminder_does_not_accumulate():
    """It is added to the request, never to stored state, so forty turns carry
    one reminder rather than forty."""
    request = _Request(40)
    before = list(request.messages)

    messages = _seen(request)

    assert request.messages == before, "the stored history was modified"
    assert sum(REMINDER in str(m) for m in messages) == 1


def test_a_stage_with_no_schema_is_not_reminded():
    """There is nothing for the reminder to be about, and saying it anyway
    invites the model to invent a schema it was not given."""
    messages = _seen(_Request(40, response_format=None))

    assert all(REMINDER not in str(m) for m in messages)


def test_a_broken_request_never_fails_the_call():
    """A reminder that can raise is worse than no reminder."""

    class Hostile(_Request):
        def override(self, **changes):
            raise RuntimeError("no override here")

    messages = _seen(Hostile(40))

    assert len(messages) == 40


def test_every_role_agent_gets_it():
    """The prose failure is not specific to one role - it hit a test round and
    a UI specialist in the same run."""
    import inspect

    from app.agents.role_agent import create_role_agent

    assert "build_response_reminder_middleware()" in inspect.getsource(create_role_agent)
