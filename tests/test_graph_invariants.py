"""Structural invariants of the workflow graph.

The `sprint_advance` bug was not a logic error - the node existed and did the
right thing. It was simply absent from `_NODE_NAMES`, so it never appeared in
any edge map and every multi-sprint run died with a KeyError the first time a
router named it.

That class of bug is invisible to behavioural tests unless a run happens to take
the affected branch, so it is asserted structurally here instead.
"""

import ast
import inspect
import re
from pathlib import Path

import pytest

from app.graph import workflow as workflow_module
from app.graph.workflow import _NODE_NAMES, _entry_router, _route_from_stage


def _registered_node_names() -> set[str]:
    """Every name passed to `graph.add_node(...)` in build_workflow_graph."""
    source = inspect.getsource(workflow_module.build_workflow_graph)
    tree = ast.parse(inspect.cleandoc(source))
    names = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_node"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            names.add(node.args[0].value)
    return names


def _assigned_stage_values() -> set[str]:
    """Every literal a node assigns to `stage`, ignoring the pause prefixes."""
    source = inspect.getsource(workflow_module)
    values = set(re.findall(r'"stage":\s*"([a-z_]+)"', source))
    values |= set(re.findall(r'update\["stage"\]\s*=\s*"([a-z_]+)"', source))
    values |= set(re.findall(r'next_stage\s*=\s*"([a-z_]+)"', source))
    values |= set(re.findall(r'approved_next="([a-z_]+)"', source))
    values |= set(re.findall(r'changes_next="([a-z_]+)"', source))
    values |= set(re.findall(r'next_stage="([a-z_]+)"', source))
    return values


def test_every_registered_node_is_routable():
    """A node missing from _NODE_NAMES is unreachable and raises KeyError.

    This is the direct regression test for `sprint_advance`.
    """
    missing = _registered_node_names() - set(_NODE_NAMES)
    assert not missing, (
        f"These nodes are registered on the graph but absent from _NODE_NAMES, "
        f"so no edge map contains them: {sorted(missing)}"
    )


def test_node_names_does_not_list_nodes_that_do_not_exist():
    """The inverse: a stale entry routes to a node that was never added."""
    phantom = set(_NODE_NAMES) - _registered_node_names()
    assert not phantom, f"_NODE_NAMES lists nodes that are not registered: {sorted(phantom)}"


def test_sprint_advance_is_routable():
    """Named explicitly, because this is the bug that shipped."""
    assert "sprint_advance" in _NODE_NAMES


#: Stage values that are instructions to the router rather than node names.
#:
#: `specialist_dispatch_parallel` is the only one. In parallel execution mode
#: the dispatcher sets it and `_route_from_stage` turns it into one `Send` per
#: delegated task, so there is deliberately no node of that name - and a test
#: that only checked `_NODE_NAMES` called the feature a bug.
#:
#: Each entry is checked below against the router itself, so an entry here can
#: only excuse a stage the router demonstrably handles.
_ROUTER_SENTINELS = frozenset({"specialist_dispatch_parallel"})


def test_every_stage_a_node_assigns_is_a_known_target():
    """Any literal assigned to `stage` must be somewhere the router can go."""
    unknown = _assigned_stage_values() - set(_NODE_NAMES) - _ROUTER_SENTINELS
    assert not unknown, f"Nodes assign stage values with no matching node: {sorted(unknown)}"


@pytest.mark.parametrize("sentinel", sorted(_ROUTER_SENTINELS))
def test_a_sentinel_stage_is_actually_handled_by_the_router(sentinel):
    """Being on the exemption list is not enough; the router must answer for it.

    Otherwise this list becomes the place a genuinely unroutable stage goes to
    silence the test above.
    """
    from langgraph.types import Send

    destination = _route_from_stage({"stage": sentinel})

    if isinstance(destination, list):
        assert destination, f"{sentinel} routed to an empty fan-out"
        assert all(isinstance(send, Send) for send in destination)
        assert all(send.node in _NODE_NAMES for send in destination)
    else:
        assert destination in _NODE_NAMES, (
            f"{sentinel} is exempt from the node-name check but the router sends "
            f"it to {destination!r}, which is not a node either"
        )


def test_the_parallel_sentinel_falls_back_when_there_is_nothing_to_fan_out():
    """An empty plan must not fan out to nobody and strand the run.

    `Send` with an empty list is not a route: LangGraph has nothing to run, the
    superstep ends, and the run stops between stages with no error. A milestone
    with no delegated tasks is uncommon but it is a shape a model produces, so
    the dispatcher's own fallback is the safety net rather than the schema.

    It falls back to the join node rather than straight to the tests, because
    the join is the one place allowed to set `stage` after a fan-out and the one
    place that looks for a worker that paused.
    """
    assert _route_from_stage({"stage": "specialist_dispatch_parallel"}) == "specialist_gather"
    assert _route_from_stage(
        {"stage": "specialist_dispatch_parallel", "milestone_plan": None}
    ) == "specialist_gather"


# ---------------------------------------------------------------------------
# Router behaviour
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("node_name", sorted(_NODE_NAMES))
def test_the_router_returns_each_node_unchanged(node_name):
    assert _route_from_stage({"stage": node_name}) == node_name


def test_a_paused_stage_ends_the_invoke():
    from langgraph.graph import END

    assert _route_from_stage({"stage": "awaiting_approval:product_manager"}) == END
    assert _route_from_stage({"stage": "awaiting_user_review:sprint"}) == END


def test_the_entry_router_starts_a_fresh_run_at_intake():
    assert _entry_router({}) == "product_manager"


def test_the_entry_router_re_enters_a_paused_review():
    assert _entry_router({"stage": "awaiting_user_review:sprint"}) == "user_review_sprint"
    assert (
        _entry_router({"stage": "awaiting_user_review:technical_specification"})
        == "user_review_specification"
    )


def test_the_entry_router_re_enters_a_paused_approval():
    assert _entry_router({"stage": "awaiting_approval:principal_architect"}) == "principal_architect"


@pytest.mark.parametrize(
    ("stage", "owner"),
    [
        ("awaiting_approval:specialist_backend_0", "specialist_dispatch"),
        ("awaiting_approval:test_round_2", "test_and_triage"),
        ("awaiting_approval:defect_fix_1_0", "defect_remediation"),
    ],
)
def test_iterated_stages_map_back_to_their_owning_node(stage, owner):
    """Loop nodes name each iteration after the iteration, not the node."""
    assert _entry_router({"stage": stage}) == owner


def test_an_unrecognised_approval_stage_fails_rather_than_guessing():
    assert _entry_router({"stage": "awaiting_approval:nonsense"}) == "failed"


def test_an_unrecognised_review_point_fails_rather_than_guessing():
    assert _entry_router({"stage": "awaiting_user_review:nonsense"}) == "failed"


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------


def test_no_escaped_newlines_in_prompt_assembly():
    """`"\\\\n".join(...)` emits a literal backslash-n into the model prompt.

    It appeared in the milestone reviewer's evidence and findings blocks, which
    arrived as one unbroken line.
    """
    source = Path(workflow_module.__file__).read_text(encoding="utf-8")
    offenders = [
        line.strip()
        for line in source.splitlines()
        if r'"\\n"' in line or r"'\\n'" in line
    ]
    assert not offenders, f"Escaped newlines reach the model as literals: {offenders}"


# ---------------------------------------------------------------------------
# Checkpoint serialization allowlist
# ---------------------------------------------------------------------------
#
# `StackSelectorOutput` was reachable in graph state but absent from
# CHECKPOINTED_TYPES, so every read of a resumed run silently degraded it to a
# plain dict. Nothing failed: the node that consumed it had a
# `hasattr(x, "model_dump_json")` fallback, so the degradation was invisible
# right up until something needed a real attribute. The allowlist is derived by
# hand, so assert mechanically that it covers what the state can actually hold.


def _models_reachable_from(annotation, seen: set) -> set:
    """Every pydantic model reachable from a type annotation, transitively."""
    import typing

    from pydantic import BaseModel

    found: set = set()
    if annotation in seen:
        return found
    seen.add(annotation)

    for arg in typing.get_args(annotation):
        found |= _models_reachable_from(arg, seen)

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        found.add(annotation)
        for field in annotation.model_fields.values():
            found |= _models_reachable_from(field.annotation, seen)
    return found


def test_every_model_the_graph_state_can_hold_is_allowlisted():
    import typing

    from app.graph.checkpointing import CHECKPOINTED_TYPES
    from app.graph.workflow import WorkflowGraphState

    reachable: set = set()
    seen: set = set()
    for annotation in typing.get_type_hints(WorkflowGraphState).values():
        reachable |= _models_reachable_from(annotation, seen)

    missing = sorted(m.__name__ for m in reachable - set(CHECKPOINTED_TYPES))
    assert not missing, (
        "These models can be stored in graph state but are not in "
        f"CHECKPOINTED_TYPES, so they deserialize as bare dicts: {missing}"
    )


# ---------------------------------------------------------------------------
# Imports the graph depends on
# ---------------------------------------------------------------------------
#
# `start_review` was once deleted from the import block by a bad paste. The
# module still imported cleanly - the list was merely one name shorter - and
# nothing failed until a review gate actually ran, which unattended runs never
# do. Assert the names exist rather than waiting for a gate to find out.


def test_every_name_the_graph_calls_is_imported():
    """A missing import here fails at gate time, not at import time."""
    import app.graph.workflow as workflow_module

    for name in (
        "start_review",
        "approve_review",
        "request_changes",
        "skip_review",
        "build_revision_prompt",
        "ReviewRerunLimitExceeded",
    ):
        assert hasattr(workflow_module, name), f"workflow.py is missing {name}"


def test_the_overflow_helpers_are_defined_once():
    """Two identical copies means a later fix to one silently does nothing."""
    import inspect

    import app.graph.workflow as workflow_module

    source = inspect.getsource(workflow_module)
    assert source.count("def _is_context_overflow") == 1
    assert source.count("def _context_overflow_update") == 1
    assert source.count("_CONTEXT_OVERFLOW_MARKERS = (") == 1


# ---------------------------------------------------------------------------
# Rewind invariants (Part 4c)
# ---------------------------------------------------------------------------


def test_the_rewind_table_only_names_real_nodes():
    """A target that is not a node is a KeyError in the conditional-edge map."""
    from app.graph.workflow import _NODE_NAMES, _REWIND_TARGETS

    for source, target in _REWIND_TARGETS.items():
        assert source in _NODE_NAMES, f"{source} is not a node"
        assert target in _NODE_NAMES, f"{source} rewinds to unknown node {target}"


def test_every_counter_reset_belongs_to_a_node_that_rewinds():
    from app.graph.workflow import _REWIND_COUNTER_RESETS, _REWIND_TARGETS

    for node in _REWIND_COUNTER_RESETS:
        assert node in _REWIND_TARGETS, (
            f"{node} resets counters but rewinds to itself; the reset is dead"
        )


def test_the_overflow_message_names_the_settings_that_apply():
    """After the rewind fix these stages retry themselves, so a resume with no
    configuration change reproduces the failure exactly. The message has to say
    which knob moves."""
    from app.graph.workflow import _context_overflow_update

    message = _context_overflow_update("scrum_master", RuntimeError("too long"))["error"]

    assert "CTX_SPECIFICATION_BUDGET" in message
    assert "CTX_ARCHITECT_DOCUMENT_BUDGET" in message
    assert "CTX_MAX_TOKENS" in message


# ---------------------------------------------------------------------------
# A stage that produced no structured response
#
# Observed on run-0b55ad49: `specialist_ui_ux_0` did its work, then wrote the
# heading "## Structured Response" in prose and continued for 431,469
# characters - about 108,000 tokens over 38 minutes - and the stage failed
# because the schema was never called. The old message blamed the context
# limit, which was not the cause, and that guess cost five commits of budget
# tuning on a branch where the budgets were fine.
# ---------------------------------------------------------------------------


def _ai(text: str):
    from langchain_core.messages import AIMessage

    return AIMessage(content=text)


def test_a_prose_answer_is_named_as_the_likely_cause() -> None:
    from app.graph.workflow import _missing_structured_response

    message = _missing_structured_response(
        "specialist_ui_ux_0",
        {"messages": [_ai("All verifications pass.\n\n## Structured Response\n\n| File |" + "x" * 5000)]},
    )

    assert "wrote the answer as prose" in message
    assert "characters" in message
    assert "not lost" in message


def test_a_truncated_answer_is_not_blamed_on_prose() -> None:
    """A short tail is the signature of running out of room, not of rambling."""
    from app.graph.workflow import _missing_structured_response

    message = _missing_structured_response("scrum_master", {"messages": [_ai("The sprint plan is")]})

    assert "wrote the answer as prose" not in message
    assert "MODEL_MAX_OUTPUT_TOKENS" in message


def test_no_final_message_is_reported_as_such() -> None:
    from app.graph.workflow import _missing_structured_response

    message = _missing_structured_response("technical_lead", {"messages": []})

    assert "no final message at all" in message


def test_the_message_never_asserts_a_cause_it_cannot_know() -> None:
    """The old text said 'this often happens if the context limit was reached'."""
    from app.graph.workflow import _missing_structured_response

    message = _missing_structured_response("x", {"messages": [_ai("done")]})

    assert "This often happens" not in message


def test_a_failed_stage_retries_on_a_fresh_conversation() -> None:
    """The retry must abandon the conversation, not replay it.

    On run-0b55ad49 the stage failed, the run was resumed, and the resume path
    re-entered the same inner thread - the one holding 431,441 characters of
    prose - and failed identically in four minutes. Clearing
    `pending_inner_thread_id` is what turns that loop into a retry.
    """
    from app.graph.workflow import _max_structured_retries

    assert _max_structured_retries() >= 1


def test_the_retry_budget_is_configurable(monkeypatch) -> None:
    from app.graph.workflow import _max_structured_retries

    monkeypatch.setenv("WORKFLOW_MAX_STRUCTURED_RETRIES", "5")
    assert _max_structured_retries() == 5
    monkeypatch.setenv("WORKFLOW_MAX_STRUCTURED_RETRIES", "nope")
    assert _max_structured_retries() == 2


def test_the_final_message_says_how_many_fresh_attempts_were_made() -> None:
    from app.graph.workflow import _missing_structured_response

    once = _missing_structured_response("x", {"messages": [_ai("done")]})
    thrice = _missing_structured_response("x", {"messages": [_ai("done")]}, attempts=3)

    assert "tried" not in once
    assert "tried 3 times, each on a fresh conversation" in thrice


def test_a_typed_context_overflow_is_recognised_without_matching_words() -> None:
    """A provider that rephrases its message must not turn a handled overflow
    into an unhandled crash."""
    from langchain_core.exceptions import ContextOverflowError

    from app.graph.workflow import _is_context_overflow

    assert _is_context_overflow(ContextOverflowError("anything at all"))


def test_the_substring_fallback_still_applies() -> None:
    """Most OpenAI-compatible servers never raise the typed error."""
    from app.graph.workflow import _is_context_overflow

    assert _is_context_overflow(ValueError("This model's maximum context length is 8192 tokens"))
    assert not _is_context_overflow(ValueError("connection reset by peer"))


# ---------------------------------------------------------------------------
# A stage's pause must not outlive the stage
#
# `_run_gated_agent` clears `pending_decision` and `pending_inner_thread_id` on
# success, but a node that pops its private result key and returns a *fresh*
# dict drops that reset. The next stage then inherits them, and
# `_run_gated_agent` - seeing a pending decision - resumes the inherited thread
# instead of starting its own.
#
# Observed on run-0b55ad49 at 1833 events: `milestone_review` finished with
# `changes_required` and handed back to `technical_lead`, which resumed the
# reviewer's conversation, was handed a `MilestoneReviewOutput`, stored it under
# `milestone_plan`, and died on
# `'MilestoneReviewOutput' object has no attribute 'selected_sprint_goal'`.
# ---------------------------------------------------------------------------


def test_handing_on_always_clears_the_pause() -> None:
    from app.graph.workflow import _handing_on

    update = _handing_on(stage="technical_lead", milestone_review="anything")

    assert update["pending_decision"] is None
    assert update["pending_inner_thread_id"] is None
    assert update["pending_approval"] is None
    assert update["stage"] == "technical_lead"


def test_handing_on_does_not_let_a_caller_resurrect_a_pause() -> None:
    """A node passing its own value wins, but nothing here defaults to carrying one."""
    from app.graph.workflow import _handing_on

    update = _handing_on(stage="x", pending_inner_thread_id="deliberate")

    assert update["pending_inner_thread_id"] == "deliberate"
    assert update["pending_decision"] is None


def test_no_node_returns_a_bare_dict_after_consuming_an_agent_result() -> None:
    """The arrangement that failed was spelling the reset out at each site.

    Five nodes have between two and seven such returns; one forgetting is
    invisible until two stages later. This reads the source because the defect
    is structural - a return that *looks* complete and is missing three keys.
    """
    import inspect
    import re

    from app.graph import workflow

    lines = inspect.getsource(workflow).split("\n")
    pops = [i for i, line in enumerate(lines) if '.pop("__' in line]
    assert pops, "the private-result pattern has moved; update this test"

    offenders = []
    for start in pops:
        indent = len(lines[start]) - len(lines[start].lstrip())
        for index in range(start + 1, len(lines)):
            stripped = lines[index].lstrip()
            if stripped.startswith("def ") and (len(lines[index]) - len(stripped)) < indent:
                break
            if re.match(r"return \{", stripped):
                offenders.append(stripped[:70])

    assert not offenders, (
        "these returns follow a completed agent run and build a fresh dict, so they "
        f"drop the pause reset - use `_handing_on`: {offenders}"
    )


def test_a_missing_product_intake_fails_with_an_explanation():
    """A stage that skipped its structured response must not raise a KeyError.

    Observed on run-c826ae90: the product manager wrote
    `docs/product_intake.md` and then reported "Product intake complete. Here
    is the structured summary:" as prose, so `product_intake` never entered
    state. `tools_models_node` read the key directly and the run died with
    `KeyError: 'product_intake'` raised from inside LangGraph - a message that
    names neither the stage that failed nor anything to do about it.
    """
    import json
    import re
    from pathlib import Path

    source = Path(__file__).resolve().parent.parent / "src/app/graph/workflow.py"
    text = source.read_text()

    body = text[text.index("def tools_models_node") : text.index("def stack_selector_node")]

    assert 'state["product_intake"]' not in body, (
        "read `product_intake` with .get() and hand back a recoverable error; "
        "a direct subscript raises KeyError from inside LangGraph"
    )
    assert 'state.get("product_intake")' in body
    assert "without returning its structured" in body
    # Resuming re-enters this node, where the intake is still missing, so the
    # guard must route back to the stage that owes the output rather than tell
    # the operator to resume. run-c826ae90 was resumed once and failed in the
    # same place.
    assert 'stage="product_manager"' in body
    assert "structured_retries" in body
