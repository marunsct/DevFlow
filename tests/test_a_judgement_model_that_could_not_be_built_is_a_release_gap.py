"""A judgement model that could not be built is among the release's completion gaps (Initiative AH.3).

The run fell back to the build model for every review; that was a log line and
a run event, and the completion read as independently reviewed.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.graph import delivery
from app.models import roles


def test_a_downgrade_is_a_gap() -> None:
    token = roles._DOWNGRADE.set("The judgement model 'x' could not be built (ValueError)")
    try:
        assert delivery._reviews_that_were_not_independent() == [
            "The judgement model 'x' could not be built (ValueError)"
        ]
    finally:
        roles._DOWNGRADE.reset(token)


def test_no_downgrade_no_gap() -> None:
    assert delivery._reviews_that_were_not_independent() == []


def test_a_release_on_the_build_model_alone_names_it_among_its_gaps(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.graph.workflow._stop_if_cancelled", lambda run_id: None)
    state = {"repository": SimpleNamespace(root_path=str(tmp_path)), "product_intake": SimpleNamespace(product_name="Notes")}
    token = roles._DOWNGRADE.set("The judgement model 'x' could not be built (ValueError)")
    try:
        released = delivery.release(state, {"configurable": {"thread_id": "t"}}, None)
    finally:
        roles._DOWNGRADE.reset(token)

    assert released["stage"] == "complete"
    assert "The judgement model 'x' could not be built (ValueError)" in released["completion_gaps"]
