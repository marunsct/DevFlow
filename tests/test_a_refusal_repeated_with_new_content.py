"""The same refusal, again, with the body rewritten each time.

The no-op branch of this middleware collapses content variation for a write
that changed nothing, because the event is the same whatever bytes were sent.
A refusal is the same kind of event and had no such treatment: the guard keyed
on the arguments, so a stage that rewrote the body on every attempt was never
counted as repeating itself.

Measured across every stored transcript, 26 combinations of stage, refusal and
path were refused three or more times, costing 72 model calls past the second.
One run's `test_round_0` wrote `docs/technical_specification.md` ten times
with different content each time - a document the workflow renders and no agent
may write - and was refused ten times without the guard ever seeing a repeat.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.messages import ToolMessage

from app.agents.repeated_queries import (
    _the_same_refusal,
    build_repeated_query_middleware,
)

REFUSAL = (
    '{"error": "Refusing to change \'docs/technical_specification.md\': the workflow '
    'writes this file from the structured response of the stage that produces it."}'
)
OTHER_REFUSAL = (
    '{"error": "Refusing to write \'app.js\': Node cannot parse this file on line 3."}'
)
SUCCESS = '{"path": "app.js", "status": "written"}'


@pytest.fixture
def call():
    middleware = build_repeated_query_middleware()

    def go(args: dict, content: str, name: str = "write_artifact") -> str:
        request = SimpleNamespace(
            tool_call={"name": name, "args": args, "id": "c1"},
            tool=None,
            state=None,
            runtime=None,
        )
        return middleware.wrap_tool_call(
            request, lambda _r: ToolMessage(content=content, tool_call_id="c1")
        ).content

    return go


def test_a_success_is_not_a_refusal():
    assert _the_same_refusal(SUCCESS) == ""


def test_two_refusals_pass_without_comment(call):
    for i in range(2):
        out = call({"relative_path": "docs/spec.md", "content": f"v{i}"}, REFUSAL)
        assert "failed the same way" not in out


def test_the_third_is_flagged_though_the_content_differs(call):
    for i in range(2):
        call({"relative_path": "docs/spec.md", "content": f"v{i}"}, REFUSAL)

    out = call({"relative_path": "docs/spec.md", "content": "something else entirely"}, REFUSAL)

    assert "failed the same way" in out
    assert "will fail this way again" in out


def test_another_file_is_counted_on_its_own(call):
    """For a refusal about CONTENT, a new file is a new problem.

    This used to use the workflow-document refusal, which is a refusal about
    what a file *is* - and that reads the same whatever path it lands on. See
    the test below: those now count together, deliberately.
    """
    for i in range(3):
        call({"relative_path": "app.js", "content": f"v{i}"}, OTHER_REFUSAL)

    out = call({"relative_path": "other.js", "content": "x"}, OTHER_REFUSAL)

    assert "failed the same way" not in out


def test_a_policy_refusal_counts_across_files(call):
    """For a refusal about what a file IS, the path is not part of the event.

    Measured on one run's `test_round_0`: refused a write to
    `docs/technical_specification.md`, then `docs/milestone_review.md`, then
    `docs/technical_specification.md` again - the same refusal in the same
    words, three times in one stage - and nothing ever fired, because two
    were spread over two paths and the third was only the second for its own.

    Counting per file gives three free attempts at each of the workflow's
    documents, and there are several.
    """
    call({"relative_path": "docs/technical_specification.md", "content": "a"}, REFUSAL)
    call({"relative_path": "docs/milestone_review.md", "content": "b"}, REFUSAL)

    out = call({"relative_path": "docs/technical_specification.md", "content": "c"}, REFUSAL)

    assert "failed the same way" in out


def test_a_different_refusal_about_the_same_file_is_counted_on_its_own(call):
    """Two different problems with one file are two things to learn, not one."""
    for i in range(3):
        call({"relative_path": "app.js", "content": f"v{i}"}, REFUSAL)

    out = call({"relative_path": "app.js", "content": "x"}, OTHER_REFUSAL)

    assert "failed the same way" not in out


def test_a_succeeding_write_is_untouched(call):
    for i in range(4):
        out = call({"relative_path": "app.js", "content": f"v{i}"}, SUCCESS)

    assert "failed the same way" not in out
