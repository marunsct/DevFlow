"""Every event type the code emits must be one `RunEvent` accepts.

run-84e05d4b reached its third sprint and died on

    ValidationError: 1 validation error for RunEvent
    event_type
      Input should be 'stage_change', 'log', 'artifact', 'review_request',
      'approval_request', 'approval_auto', 'error', 'complete',
      'agent_message', 'tool_call' or 'tool_result'
      [type=literal_error, input_value='approval_denied']

The runner had been given a new event type and the model had not. The full
test suite passed: no test ran the runner's denial path against the real
`RunEvent`, so the two halves never met until a live run made them.

This test makes them meet. It reads the literal strings passed as
`event_type=` anywhere in `app/`, and checks each against the model - so the
next person to add an event type finds out here rather than three sprints into
a run.
"""

from __future__ import annotations

import ast
import typing
from pathlib import Path

import pytest

from app.server.events import RunEvent

SOURCE = Path(__file__).resolve().parents[1] / "src" / "app"


def _emitted_event_types() -> set[str]:
    """Every literal passed as `event_type=` in the application source."""
    found: set[str] = set()
    for path in SOURCE.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):  # pragma: no cover - unreadable source
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg != "event_type":
                    continue
                if isinstance(keyword.value, ast.Constant) and isinstance(
                    keyword.value.value, str
                ):
                    found.add(keyword.value.value)
    return found


def _accepted_event_types() -> set[str]:
    annotation = RunEvent.model_fields["event_type"].annotation
    return set(typing.get_args(annotation))


def test_the_source_emits_at_least_the_ones_we_know_about() -> None:
    """A guard on the guard: if the scan finds nothing, it has stopped working.

    The scan sees `event_type="..."` written as a keyword with a literal, which
    is how the runner writes every one of them - and is the shape the bug had.
    Call sites that pass a variable cannot be checked statically and are not
    counted here, so this floor is well below the model's full set.
    """
    emitted = _emitted_event_types()

    assert "approval_auto" in emitted
    assert "approval_denied" in emitted
    assert len(emitted) >= 6


@pytest.mark.parametrize("event_type", sorted(_emitted_event_types()))
def test_every_emitted_event_type_is_accepted(event_type: str) -> None:
    assert event_type in _accepted_event_types(), (
        f"`{event_type}` is passed as event_type= somewhere in app/ but "
        "RunEvent does not accept it; publishing one raises ValidationError "
        "and ends the run."
    )


@pytest.mark.parametrize("event_type", sorted(_emitted_event_types()))
def test_the_model_actually_builds_with_it(event_type: str) -> None:
    """The literal check and the model agreeing is not quite proof."""
    event = RunEvent(run_id="r", sequence=1, stage="s", event_type=event_type, message="m")

    assert event.event_type == event_type
