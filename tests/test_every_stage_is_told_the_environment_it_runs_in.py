"""Every stage is told the environment it actually runs in.

Only the stack selector heard the truth about the sandbox. Measured on one
run: the architect specified a database server and startup migrations on a
machine with no database (its own sandbox logged the readiness probe
refused), QA wrote a suite against services that cannot start, and a fixer
looped thirty calls on installs that landed in a user site the acceptance
server's interpreter never reads. The contract is one derived block,
byte-stable, appended to every role agent's calls ahead of the workspace
listing (Initiative K.1).
"""

from __future__ import annotations

import inspect
import re

from app.agents import environment_contract, role_agent
from app.agents.environment_contract import (
    build_environment_contract_middleware,
    environment_contract_text,
)
from app.agents.stack_selector import EXECUTION_ENVIRONMENT, describe_execution_environment
from app.tools.sandbox import allowed_executables


class _Request:
    def __init__(self, messages):
        self.messages, self.captured = messages, {}

    def override(self, **changes):
        self.captured.update(changes)
        return self


def test_the_contract_lists_every_command_the_sandbox_allows():
    for command in allowed_executables("testing_specialist"):
        assert command in environment_contract_text(), f"{command} is permitted but not described"


def test_the_contract_is_the_same_bytes_on_every_call():
    """Byte-stable, or it breaks the prefix cache it is appended under."""
    assert environment_contract.the_environment_contract() == environment_contract_text()


def test_the_middleware_appends_the_contract_after_the_conversation():
    request = _Request([{"role": "user", "content": "design it"}])

    build_environment_contract_middleware().wrap_model_call(request, lambda r: r)

    messages = request.captured["messages"]
    assert messages[0]["content"] == "design it"
    assert messages[-1]["content"] == environment_contract_text()


def test_the_middleware_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT_CONTRACT", "0")
    request = _Request([{"role": "user", "content": "design it"}])

    build_environment_contract_middleware().wrap_model_call(request, lambda r: r)

    assert request.captured == {}


def test_every_role_agent_carries_the_contract_ahead_of_the_listing():
    """Ahead of the digest: the stable bytes come first, the listing that
    changes comes last, so the prefix cache breaks no earlier than before."""
    source = inspect.getsource(role_agent)
    assert source.index("build_environment_contract_middleware()") < source.index(
        "build_workspace_digest_middleware("
    )


def test_the_contract_names_no_product_word():
    banned = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")
    for word in banned:
        assert not re.search(rf"\b{re.escape(word)}\b", environment_contract_text(), re.IGNORECASE), word


def test_the_selector_keeps_its_own_fuller_text():
    assert describe_execution_environment is environment_contract.describe_execution_environment
    assert "Choose a testing approach" in EXECUTION_ENVIRONMENT
    assert "Choose a testing approach" not in environment_contract_text()
