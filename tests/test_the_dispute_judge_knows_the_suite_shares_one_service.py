"""The QA lead judging a failed attempt's locked tests is told when the suite runs against one shared service.

Measured on one run: a locked test counted every entry in a list other tests also add to. The QA lead,
shown only the code and the failures, judged it fair, and it failed a right product through every round.
The suite's writer and its reviewer were told the service is shared; the judge was not.
"""
from __future__ import annotations

import inspect
import re

from app.acceptance.requests import shares_one_service
from app.agents.suite_dispute import ONE_SHARED_SERVICE, build_dispute_request
from app.graph import workflow
from app.stacks import contract, pack_named

BANNED = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")
FAILING = [("[AC-3] lists", "AC-3: List entries", "Expected: 1\nReceived: 3")]


def _text(**options) -> str:
    return build_dispute_request(FAILING, "test('x')", "Brief", **options)["messages"][0]["content"]


def test_a_shared_service_is_named_to_the_judge() -> None:
    text = _text(shared_service=True)
    assert ONE_SHARED_SERVICE in text
    assert "never emptied between tests" in text
    assert text.index("How the suite runs") < text.index("The suite's code")


def test_a_suite_that_starts_its_own_product_is_not_told_so() -> None:
    assert "How the suite runs" not in _text()
    assert "How the suite runs" not in _text(shared_service=False)


def test_which_workspaces_share_one_service(tmp_path) -> None:
    service, program, bare = tmp_path / "service", tmp_path / "program", tmp_path / "bare"
    contract.write(service, pack_named("node-hono-native-api"), "notes", "Notes")
    contract.write(program, pack_named("python-cli"), "notes", "Notes")
    bare.mkdir()
    assert shares_one_service(service) is True
    assert shares_one_service(program) is False
    assert shares_one_service(bare) is False


def test_the_dispute_node_says_it() -> None:
    source = inspect.getsource(workflow)
    assert "shared_service=shares_one_service(root)" in source


def test_the_rule_names_no_product() -> None:
    for word in BANNED:
        assert not re.search(rf"\b{re.escape(word)}\b", ONE_SHARED_SERVICE.lower()), word
