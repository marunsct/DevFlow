"""A design escalation the person sends back is not counted toward `MAX_ESCALATIONS` (TG.3).

Found in the review of the thorough-delivery design gate: sprint and design escalations shared one count of three, so
a thorough run whose person kept answering "Request changes" at the design escalation stopped as failed on the
fourth, for nothing but the person's own answers. A sprint escalation still counts as before
(`test_vertical_slices_and_escalation`).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.graph import escalation

CONFIG = {"configurable": {"thread_id": "t"}}


def _a_stuck_design(tmp_path, **fields):
    return {"repository": SimpleNamespace(root_path=str(tmp_path)), "decisions": [],
            "escalation": {"kind": "design", "error": "The reviewer still asks for changes.",
                           "findings": ["The interface is never served."]},
            **fields}


def _sent_back(state):
    """The state after the person answers the design escalation with a request for changes."""
    update = escalation.retry({**state, "revision_comments": ["Serve the interface beside the service."]}, CONFIG, None)
    return {**state, **update}


def test_a_person_who_keeps_sending_the_design_back_is_asked_again_rather_than_the_run_failing(tmp_path):
    state = _a_stuck_design(tmp_path)
    stages = []
    with patch("app.graph.workflow._review_enabled", lambda state, point: True):
        for _ in range(escalation.MAX_ESCALATIONS + 1):
            update = escalation.escalation(state, CONFIG, None)
            stages.append(update["stage"])
            state = _sent_back({**state, **update, "escalation": _a_stuck_design(tmp_path)["escalation"]})

    assert stages == ["user_review_escalation"] * (escalation.MAX_ESCALATIONS + 1)
