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


def test_every_stage_a_node_assigns_is_a_known_target():
    """Any literal assigned to `stage` must be somewhere the router can go."""
    unknown = _assigned_stage_values() - set(_NODE_NAMES)
    assert not unknown, f"Nodes assign stage values with no matching node: {sorted(unknown)}"


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
