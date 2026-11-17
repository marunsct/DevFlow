"""A real role agent on a scripted model, for tests of what every role agent does.

`create_role_agent` builds the whole middleware chain; a test that wants to know
"every role agent carries X" builds one here and looks at what X does - the
request the model is sent, or the files a reply's tool calls leave behind -
rather than reading `role_agent.py` for the line that adds X.

The model is the one double: it answers with the replies given, records every
request, and stops the stage when it has nothing left to say. The plugin
instructions store (Postgres) is cut off, since no test here is about it.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import BaseModel


class Stopped(Exception):
    """The scripted model has nothing left to say."""


class Scripted(BaseChatModel):
    """Answers with `replies` in order, recording each request; raises `Stopped` after the last."""

    replies: list[AIMessage] = []
    requests: list[list[BaseMessage]] = []
    offered: list[list[str]] = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "Scripted":
        """Records the names of the tools the stage is offered on each call."""
        self.offered.append([getattr(tool, "name", None) or tool.get("name", "") for tool in tools])
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.requests.append(list(messages))
        if not self.replies:
            raise Stopped()
        return ChatResult(generations=[ChatGeneration(message=self.replies.pop(0))])


class Answer(BaseModel):
    summary: str


def run_a_role_agent(
    root: Path | str,
    monkeypatch,
    replies: list[AIMessage] = (),
    *,
    approve: int = 0,
    system_prompt: str = "You are the probe.\n",
    configurable: dict[str, Any] | None = None,
) -> list[list[BaseMessage]]:
    """Build a role agent over `root`, give it "go", approve `approve` gated calls, and return every request its
    model was sent. `configurable` is what the workflow puts in the invoke's config (the run, the stage)."""
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.types import Command

    from app.agents.role_agent import create_role_agent

    monkeypatch.setattr("app.plugins.middleware.get_plugin_instructions", lambda keys, role: "")
    model = Scripted(replies=list(replies), requests=[], offered=[])
    agent = create_role_agent(
        name="probe", stage="probe", system_prompt=system_prompt, response_format=Answer,
        model=model, repo_root=str(root), checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": "t", **(configurable or {})}}
    try:
        agent.invoke({"messages": [{"role": "user", "content": "go"}]}, config)
        if approve:
            agent.invoke(Command(resume={"decisions": [{"type": "approve"}] * approve}), config)
    except Stopped:
        pass
    return model.requests


def the_first_request(root: Path | str, monkeypatch, **kwargs: Any) -> list[BaseMessage]:
    """The messages a role agent's model is sent on its first call."""
    return run_a_role_agent(root, monkeypatch, **kwargs)[0]


def the_tools_offered(create: Any, root: Path | str, monkeypatch) -> list[str]:
    """The tool names an agent built by `create(model=..., repo_root=...)` offers its model on the first call."""
    monkeypatch.setattr("app.plugins.middleware.get_plugin_instructions", lambda keys, role: "")
    model = Scripted(replies=[], requests=[], offered=[])
    agent = create(model=model, repo_root=str(root))
    try:
        agent.invoke({"messages": [{"role": "user", "content": "go"}]}, {"configurable": {"thread_id": "t"}})
    except Stopped:
        pass
    return model.offered[0]
