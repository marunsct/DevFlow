"""A product the locked suite accepts is released with its failing unit tests recorded, not held back until the run stops.

Measured on a small-model run: hidden tests 9 of 9, the acceptance suite passing but for one deferred criterion,
and the run ended as failed because the unit tests the model wrote could not be made to pass: every release hold
sent the last sprint round again, every round ended in an escalation, and the escalation budget ran out.
"""
from __future__ import annotations

import pytest

from app.graph import release_with_failing_unit_tests as ship

FAILS = ["unit: pytest > tests.test_notes > test_a", "unit: pytest > tests.test_notes > test_b"]


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("RELEASE_WITH_FAILING_UNIT_TESTS", "on")


def _may(**changes):
    arguments = {"unit_failures": FAILS, "failing": FAILS, "accepted_at_an_escalation": True,
                 "release_attempts": 0, "most_release_attempts": 2}
    return ship.may_ship(**{**arguments, **changes})


def test_it_ships_when_only_the_unit_tests_fail_and_the_sprint_was_accepted_with_them_open():
    assert _may()


def test_it_ships_when_the_release_has_held_the_product_back_as_often_as_it_may():
    assert _may(accepted_at_an_escalation=False, release_attempts=2)


def test_it_holds_back_while_the_harness_has_not_given_the_tests_its_chances():
    assert not _may(accepted_at_an_escalation=False, release_attempts=0)
    assert not _may(accepted_at_an_escalation=False, release_attempts=1)


def test_it_never_ships_what_a_criterion_or_the_handoff_fails():
    assert not _may(failing=["AC-3"])
    assert not _may(failing=[*FAILS, "the suite did not run"])
    assert not _may(failing=["The handoff is not ready"], unit_failures=[])
    assert not _may(unit_failures=[], failing=[])


def test_it_is_a_switch_and_off_it_holds_the_product_back_as_before(monkeypatch):
    monkeypatch.setenv("RELEASE_WITH_FAILING_UNIT_TESTS", "off")
    assert not _may()


def test_the_gap_names_the_tests_so_no_record_reads_as_a_plain_success():
    text = ship.gap(FAILS)
    assert "2 of the project's own unit tests still fail and ship failing" in text and "test_a" in text
    assert "and 2 more" in ship.gap([f"t{n}" for n in range(8)])


def test_the_release_gate_uses_it(monkeypatch, tmp_path):
    """The release gate, with a locked suite that passes and unit tests that fail after an accepted escalation, releases."""
    from types import SimpleNamespace

    from app.graph import delivery

    monkeypatch.setattr(delivery.suite, "is_locked", lambda root: True)
    monkeypatch.setattr(delivery.suite, "run", lambda root: SimpleNamespace(
        failing=lambda: [], summary=lambda: "17 passed", ran=True))
    monkeypatch.setattr(delivery.suite, "vacuous_green", lambda root, result: [])
    monkeypatch.setattr(delivery.suite, "deferred", lambda root: {})
    monkeypatch.setattr(delivery, "_unit_tests_failing", lambda root: list(FAILS))
    monkeypatch.setattr(delivery, "_root", lambda state: str(tmp_path))

    class _Stop(Exception):
        pass

    # The gate decides before anything is written: stop right after the decision it records.
    recorded = {}

    def _record(state, update, **kwargs):
        recorded.update(kwargs)
        raise _Stop

    monkeypatch.setattr("app.decisions.record_decision", _record)
    state = {"known_issues": ["the sprint was accepted with its unit tests open"], "release_attempts": 0}
    with pytest.raises(_Stop):
        delivery.release(state, {"configurable": {}}, SimpleNamespace(judgement_model=None))

    assert recorded["decision"] == "release"
    assert "still fail and ship failing" in recorded["rationale"]
