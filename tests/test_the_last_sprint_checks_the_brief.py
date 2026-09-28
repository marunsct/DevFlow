"""A run does not finish until the brief is delivered.

Every milestone review is scoped to its own milestone, and deferring a
requirement out of one is legitimate - a sprint plan exists to do exactly
that. One run's first review put both `edit` and the filter bar into
later sprints, correctly.

Nothing asked again at the end. `complete_node` returns `{"stage":
"complete"}` and nothing else, so a requirement deferred out of every
milestone in turn was never checked at all, and three completed runs shipped
with no way to edit a task: three runs.
"""

from __future__ import annotations

import types
from pathlib import Path

import pytest

from app.graph.workflow import _a_brief_requirement_the_run_never_built

BRIEF = """# Product Brief

## Acceptance Criteria
- Users can add, edit, delete tasks
"""

WITHOUT_EDIT = """
export function addTask(t) { return { t }; }
export function deleteTask(id) { return id; }
"""

WITH_EDIT = WITHOUT_EDIT + "\nexport function editTask(id, title) { return title; }\n"


def _state(tmp_path: Path, product: str, brief: str = BRIEF) -> dict:
    (tmp_path / "app.js").write_text(product, encoding="utf-8")
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><body><script type="module" src="app.js"></script></body></html>',
        encoding="utf-8",
    )
    return {
        "document": types.SimpleNamespace(text=brief),
        "repository": types.SimpleNamespace(root_path=str(tmp_path)),
    }


def test_a_brief_requirement_never_built_is_reported(tmp_path) -> None:
    finding = _a_brief_requirement_the_run_never_built(_state(tmp_path, WITHOUT_EDIT))

    assert "`edit`" in finding
    assert "MUST FIX" in finding


def test_it_says_this_is_the_last_check(tmp_path) -> None:
    """The lead has to know why this arrived after an acceptance."""
    finding = _a_brief_requirement_the_run_never_built(_state(tmp_path, WITHOUT_EDIT))

    assert "the last sprint is accepted and the brief is not delivered" in finding.lower()
    assert "does not finish until it passes" in finding


def test_a_delivered_brief_is_silent(tmp_path) -> None:
    assert _a_brief_requirement_the_run_never_built(_state(tmp_path, WITH_EDIT)) == ""


def test_a_run_with_no_brief_is_silent(tmp_path) -> None:
    """Nothing to check against is not a failure to deliver."""
    assert _a_brief_requirement_the_run_never_built(_state(tmp_path, WITHOUT_EDIT, "")) == ""


def test_a_gate_that_cannot_run_never_stops_a_finished_run(tmp_path) -> None:
    """A run that has passed everything else must not die because a check
    could not be executed."""
    broken = {"document": types.SimpleNamespace(text=BRIEF), "repository": None}

    assert _a_brief_requirement_the_run_never_built(broken) == ""


def test_a_missing_workspace_is_silent(tmp_path) -> None:
    state = _state(tmp_path, WITHOUT_EDIT)
    state["repository"] = types.SimpleNamespace(root_path=str(tmp_path / "nowhere"))

    assert _a_brief_requirement_the_run_never_built(state) == ""


# --- where it is asked ----------------------------------------------------


def test_it_is_asked_only_on_the_last_sprint() -> None:
    """Deferring a requirement out of a middle milestone is what a sprint plan
    is for. Asking there would turn every plan into a finding."""
    import inspect

    from app.graph import workflow

    source = inspect.getsource(workflow)
    call = source[source.index("unbuilt = _a_brief_requirement_the_run_never_built") :]
    before = source[: source.index("unbuilt = _a_brief_requirement_the_run_never_built")]

    assert before.rstrip().endswith("if not has_more_sprints:")
    assert "stage=\"technical_lead\"" in call[:900]


def test_it_sends_the_work_back_before_it_gives_up() -> None:
    """Failing a run that built most of the product would be worse than
    building the rest of it. The existing revision ceiling bounds this."""
    import inspect

    from app.graph import workflow

    source = inspect.getsource(workflow)
    block = source[source.index("unbuilt = _a_brief_requirement_the_run_never_built") :][:1400]

    assert "MAX_MILESTONE_REVISIONS" in block
    assert "_escalate_to_a_human" in block
    assert "revision_comments" in block
