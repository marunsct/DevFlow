"""Defects failing at one layer behind one root cause are one fixer's work.

Bundling existed for identical problems only: one run queued 13 defects
from one root cause - every acceptance criterion failing behind a server
that did not serve - and the fixers worked them one by one while the cause
was one thing (Initiative L.1). The clustering is by failing surface plus
first failing layer, not by identical description: a layer error the whole
product meets (connection refused, one auth middleware's 401 behind every
API criterion) clusters wholesale; a layer error two criteria meet
clusters only when they share a surface; and assertion-level failures -
each criterion's own expectation - are never a shared layer at all.
"""

from __future__ import annotations

import inspect
import re

from app.agents.specialists import ReportedDefect
from app.graph import workflow
from app.graph.workflow import (
    _one_defect_per_root_error,
    _share_a_failing_surface,
    _the_first_failing_layer,
)

BANNED = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")


def _d(description, actual="a", files=(), owner="backend", severity="major"):
    return ReportedDefect(
        description=description, severity=severity, reproduction_steps="r",
        expected_behavior="e", actual_behavior=actual, affected_files=list(files), owner=owner,
    )


def test_the_layer_a_failure_meets_is_read_from_its_text() -> None:
    assert _the_first_failing_layer("page.goto: net::ERR_CONNECTION_REFUSED at http://localhost:8000") == "connection-refused"
    assert _the_first_failing_layer("request failed: ECONNREFUSED 127.0.0.1:8000") == "connection-refused"
    assert _the_first_failing_layer("GET /notes answered 404 Not Found") == "not-found"
    assert _the_first_failing_layer("expected 200 but the server answered 401 Unauthorized") == "unauthorized"
    assert _the_first_failing_layer("the server answered 500 Internal Server Error") == "server-error"
    assert _the_first_failing_layer("locator.getByRole: Timeout 5000ms exceeded") == "timeout"


def test_an_assertion_is_a_symptom_not_a_layer() -> None:
    assert _the_first_failing_layer("expect(received).toBe(expected) // Object.is equality") == ""
    assert _the_first_failing_layer("the list is empty when it should hold two entries") == ""


def test_a_layer_the_whole_product_meets_clusters_wholesale() -> None:
    """Four criteria, four surfaces, one server that does not start: one
    fixer, carrying every member's failure as evidence."""
    reported = [
        _d("[AC-1] the list shows the entries", "page.goto: net::ERR_CONNECTION_REFUSED"),
        _d("[AC-2] a new entry appears", "page.goto: net::ERR_CONNECTION_REFUSED"),
        _d("[AC-3] an entry can be edited", "request failed: ECONNREFUSED 127.0.0.1:8000"),
        _d("[AC-4] an entry can be deleted", "page.goto: net::ERR_CONNECTION_REFUSED", severity="blocking"),
    ]

    merged = _one_defect_per_root_error(reported)

    assert len(merged) == 1
    assert merged[0].description.startswith("[AC-1]")
    assert "the same first failure" in merged[0].description
    assert "[AC-4]" in merged[0].description
    assert merged[0].severity == "blocking"


def test_a_layer_two_criteria_meet_clusters_only_on_a_shared_surface() -> None:
    same_route = [
        _d("[AC-1] notes are listed", "GET /notes answered 404 Not Found"),
        _d("[AC-2] notes survive a reload", "GET /notes answered 404 Not Found"),
    ]
    assert len(_one_defect_per_root_error(same_route)) == 1

    different_routes = [
        _d("[AC-1] notes are listed", "GET /notes answered 404 Not Found"),
        _d("[AC-2] tags are listed", "GET /tags answered 404 Not Found"),
    ]
    assert len(_one_defect_per_root_error(different_routes)) == 2


def test_two_defects_in_one_file_share_a_surface() -> None:
    one = _d("[AC-1] x", "404 Not Found", files=["src/routes.js"])
    two = _d("[AC-2] y", "404 Not Found", files=["app/src/routes.js"])
    assert _share_a_failing_surface(one, two)

    three = _d("[AC-3] z", "404 Not Found", files=["src/other.js"])
    assert not _share_a_failing_surface(one, three)


def test_different_layers_stay_apart() -> None:
    reported = [
        _d("[AC-1] the list shows", "page.goto: net::ERR_CONNECTION_REFUSED"),
        _d("[AC-2] a note opens", "GET /notes/1 answered 404 Not Found"),
        _d("[AC-3] a note saves", "locator.getByRole: Timeout 5000ms exceeded"),
    ]

    assert len(_one_defect_per_root_error(reported)) == 3


def test_defects_with_no_layer_are_left_alone() -> None:
    reported = [
        _d("[AC-1] the list shows", "expect(received).toBe(expected)"),
        _d("[AC-2] a note opens", "the page rendered nothing"),
    ]

    assert _one_defect_per_root_error(reported) == reported


def test_the_round_s_assembly_asks_for_the_clustering() -> None:
    source = inspect.getsource(workflow.build_workflow_graph)

    assert "reported = _one_defect_per_cause(reported)" in source
    assert "reported = _one_defect_per_root_error(reported)" in source


def test_the_cluster_s_words_are_plain_language() -> None:
    reported = [
        _d("[AC-1] the list shows the entries", "page.goto: net::ERR_CONNECTION_REFUSED"),
        _d("[AC-2] a new entry appears", "page.goto: net::ERR_CONNECTION_REFUSED"),
        _d("[AC-3] an entry can be edited", "page.goto: net::ERR_CONNECTION_REFUSED"),
    ]

    merged = _one_defect_per_root_error(reported)[0]

    text = " ".join(str(v) for v in merged.model_dump().values() if v)
    for word in BANNED:
        assert not re.search(rf"\b{word}\b", text, re.IGNORECASE), word
