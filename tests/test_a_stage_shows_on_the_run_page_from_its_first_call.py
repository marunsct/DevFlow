"""A stage shows on the run page from its first model call, even one that answers in structured output alone.

The run page builds its steps and its activity from the run's events, and the
activity stream published only a reply's text, tool calls and results. A stage
that answered in structured output - an intake, a technology consultation -
published nothing, so the page said "Not started yet" while two stages had
finished and a third was working.
"""
from __future__ import annotations

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from app.server.agent_stream import AgentActivityStream


class Recording(AgentActivityStream):
    def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
        super().__init__(*args, **kwargs)
        self.published: list[tuple[str, str, dict]] = []

    def _publish(self, event_type, message, metadata=None):  # noqa: ANN001
        self.published.append((event_type, message, metadata or {}))


def test_a_stage_with_no_text_and_no_tool_call_is_announced_once():
    stream = Recording("run-1", "product_manager")
    model = GenericFakeChatModel(messages=iter([AIMessage(content=""), AIMessage(content="")]))

    model.invoke("intake", config={"callbacks": [stream]})
    model.invoke("intake again", config={"callbacks": [stream]})

    announced = [p for p in stream.published if p[0] == "stage_change"]
    assert len(announced) == 1 and announced[0][2] == {"status": "running"} and announced[0][1]


def test_the_announcement_puts_the_stage_on_the_page_s_steps():
    from app.server.events import RunEvent
    from app.server.runs import _derive_stages

    stream = Recording("run-1", "tools_models")
    stream.on_chat_model_start({}, [[]])
    event_type, message, metadata = stream.published[0]
    event = RunEvent(run_id="run-1", sequence=1, stage="tools_models", event_type=event_type,
                     message=message, metadata=metadata)

    steps = _derive_stages([event], None)

    assert [s["name"] for s in steps] == ["tools_models"] and steps[0]["meaning"] == message


def test_an_iterated_stage_reads_as_what_its_family_does():
    from app.server.runner import _stage_meaning

    for stage in ("consult_security_reliability", "defect_fix_2_5", "test_round_1", "specialist_backend_0"):
        assert _stage_meaning(stage) != stage and _stage_meaning(stage).endswith("."), stage
    assert _stage_meaning("product_manager").startswith("Reading the product document")
    assert _stage_meaning("an_unknown_stage") == "an_unknown_stage"


def test_every_iterated_family_has_a_meaning():
    from app.graph.workflow import _ITERATED_STAGE_OWNERS
    from app.server.runner import _FAMILY_MEANINGS

    assert {p for p in _ITERATED_STAGE_OWNERS if p.endswith("_")} <= set(_FAMILY_MEANINGS)
