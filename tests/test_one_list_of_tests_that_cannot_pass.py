"""The test round knows every test the suite's review knows cannot pass.

The review that locks the suite and each test round decided "cannot pass
whatever is built" from two hand-kept lists, and the round's lacked four of
the review's checks. A review that has spent its rounds locks the suite with
its problems still open, so a test only the review's list named - one holding
the product to an order no criterion states, say - was later failed against
the product and charged to it as a defect no fix could close.

Checks that make a suite too lenient (it passes a product it should fail)
stay with the review: they never charge the product for anything.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.acceptance import suite
from app.graph import acceptance_nodes

CANNOT_PASS = (
    "tests_that_assert_an_unstated_order",
    "locators_that_contradict_their_assertions",
    "tests_with_module_system_mismatch",
    "tests_with_unawaited_async_helpers",
)
TOO_LENIENT = ("locators_nobody_sees", "locators_that_pick_one")


@pytest.fixture
def every_check_names_itself(monkeypatch):
    names = [n for n in dir(suite) if n.startswith(("tests_", "locators_", "assertions_", "controls_")) or n == "vacuous_green"]
    names = [n for n in names if n != "tests_that_cannot_pass"]
    for name in names:
        monkeypatch.setattr(suite, name, lambda *a, _n=name, **k: [f"{_n}: AC-1 a test"])
    result = SimpleNamespace(ran=True)
    monkeypatch.setattr(acceptance_nodes, "run_for_sprint", lambda state: (result, []))
    monkeypatch.setattr(acceptance_nodes.acceptance_requests, "acceptance_block", lambda result, due: "suite")


def _named(broken: list[str]) -> set[str]:
    return {item.split(":", 1)[0] for item in broken}


def test_the_round_names_what_the_review_says_cannot_pass(every_check_names_itself, tmp_path) -> None:
    _, broken = acceptance_nodes.acceptance_for_round({"repository": SimpleNamespace(root_path=str(tmp_path))})
    assert set(CANNOT_PASS) <= _named(broken)


def test_a_too_lenient_suite_is_not_charged_to_anyone_at_the_round(every_check_names_itself, tmp_path) -> None:
    _, broken = acceptance_nodes.acceptance_for_round({"repository": SimpleNamespace(root_path=str(tmp_path))})
    assert not set(TOO_LENIENT) & _named(broken)


def test_the_shared_list_is_one_function(every_check_names_itself, tmp_path) -> None:
    shared = _named(suite.tests_that_cannot_pass(str(tmp_path), SimpleNamespace(ran=True)))
    _, broken = acceptance_nodes.acceptance_for_round({"repository": SimpleNamespace(root_path=str(tmp_path))})
    assert shared <= _named(broken)
    assert set(CANNOT_PASS) <= shared
