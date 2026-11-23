"""A fix round takes the defects its latest test round raised before the ones carried over from earlier rounds.

Measured on one run (a Python interface and a page, 97 acceptance tests): a test round raised ten defects, the first
"the router is mounted with a double prefix, causing every endpoint under it to return 404" and eight more its
symptoms ("creation returns 404 - all AC-2, AC-9 tests fail", ...). The fix round after it went in the order of the
ledger, so its first fixers took two defects carried over from earlier rounds - judged on a product that no longer
existed - and twenty-five minutes later the double prefix had not been worked, the suite stood at 17 of 97 and no fix
on a route under it could be measured. Only the order may change: nothing is dropped, and a product that does not
start is still fixed alone first.
"""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest
import the_fix_stage

from app.graph.acceptance_nodes import THE_PRODUCT_DOES_NOT_START

EFFECTS = Path(__file__).resolve().parent.parent / "scripts" / "loop" / "effects.py"
#: Where each defect sits in the ledger below.
CARRIED = (0, 1, 2)
ROOT = 3
SYMPTOMS = (4, 5, 6, 7)


def _carried(description: str, file: str, criterion: str):
    """Raised by round 0, worked once and left open; round 1 did not raise it again."""
    return the_fix_stage.a_defect(description, affected_files=[file], found_in_round=0, fix_attempts=1,
                                  evidence=[{"test": f"{criterion} {description}", "criterion": criterion}])


def _raised_by_round_1(description: str, file: str):
    return the_fix_stage.a_defect(description, affected_files=[file], found_in_round=1)


def _the_ledger():
    """The open defects as the measured fix round found them: carried over first, then what round 1 raised."""
    return [
        _carried("Registration endpoint returns non-201 response (likely 500 or 404)", "app/auth.py", "AC-1"),
        _carried("Due date handling fails - ISO 8601 dates are not accepted", "app/dates.py", "AC-5"),
        _carried("Listing filters ignore the owner", "app/filters.py", "AC-7"),
        _raised_by_round_1("Notes router mounted with double prefix causing all note CRUD endpoints to return 404",
                           "app/main.py"),
        _raised_by_round_1("Note creation endpoint returns 404 - all AC-2, AC-9 tests fail", "app/routers/create.py"),
        _raised_by_round_1("Note update endpoint returns 404", "app/routers/update.py"),
        _raised_by_round_1("Priority validation tests fail - all AC-4 tests return 404", "app/routers/priority.py"),
        _raised_by_round_1("Due date tests fail - AC-5 all return 404", "app/routers/due.py"),
    ]


@pytest.fixture
def transcript(monkeypatch, tmp_path):
    from app.observability.transcript import read_transcript

    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    # A node run on its own has no graph config to name its run by.
    monkeypatch.setattr("app.observability.transcript._run_id_from_config", lambda: "r")
    return lambda: read_transcript("r", {"fix_order"})


def _one_at_a_time(root, defects) -> list[int]:
    """Every defect the fix round sends, one at a time, until it hands back to the test round."""
    sent: list[int] = []
    cursor = 0
    while True:
        update, seen = the_fix_stage.run(root, the_fix_stage.a_state(root, *defects, defect_cursor=cursor))
        if update.get("stage") == "test_and_triage":
            return sent
        sent += [int(stage.rsplit("_", 1)[1]) for stage, _ in seen.shown]
        cursor = update["defect_cursor"]


@pytest.mark.parametrize("criteria_first", ["off", "on"])
def test_one_at_a_time_the_cause_the_latest_round_raised_is_fixed_first_and_none_is_dropped(
        monkeypatch, tmp_path, criteria_first):
    monkeypatch.setenv("FIX_ORDER_CRITERIA_FIRST", criteria_first)

    sent = _one_at_a_time(tmp_path, _the_ledger())

    assert sent == [ROOT, *SYMPTOMS, *CARRIED]


def test_side_by_side_the_first_batch_opens_with_the_cause_the_latest_round_raised(monkeypatch, tmp_path):
    monkeypatch.setenv("HARNESS_MAX_PARALLEL", "2")

    update, _ = the_fix_stage.run(tmp_path, the_fix_stage.a_state(tmp_path, *_the_ledger()), side_by_side=True)

    assert update["fix_batch"] == [ROOT, SYMPTOMS[0]]


def test_a_carried_over_product_that_does_not_start_is_still_fixed_alone_first(monkeypatch, tmp_path):
    monkeypatch.setenv("HARNESS_MAX_PARALLEL", "2")
    start = the_fix_stage.a_defect(THE_PRODUCT_DOES_NOT_START, affected_files=[], kind="start_failure",
                                   found_in_round=0)

    update, seen = the_fix_stage.run(tmp_path, the_fix_stage.a_state(tmp_path, start, *_the_ledger()),
                                     side_by_side=True)

    assert not update.get("fix_batch")
    assert [stage for stage, _ in seen.shown] == ["defect_fix_2_0"]


def test_a_defect_the_latest_round_raised_again_counts_as_its_own(monkeypatch, tmp_path):
    """Raised again, a carried-over defect takes the latest round: the latest measurement confirms it."""
    ledger = _the_ledger()
    ledger[1] = ledger[1].model_copy(update={"found_in_round": 1})

    sent = _one_at_a_time(tmp_path, ledger)

    assert sent == [1, ROOT, *SYMPTOMS, 0, 2]


def test_defects_all_raised_by_one_round_go_in_the_order_raised(monkeypatch, tmp_path, transcript):
    monkeypatch.setenv("FIX_ORDER_CRITERIA_FIRST", "off")
    ledger = [defect.model_copy(update={"found_in_round": 1}) for defect in _the_ledger()]

    sent = _one_at_a_time(tmp_path, ledger)

    assert sent == list(range(8))
    assert transcript() == []


def test_the_reorder_is_recorded_once_and_counted_by_the_effects_report(monkeypatch, tmp_path, transcript):
    from app.observability import switch_firing

    monkeypatch.setenv("FIX_ORDER_CRITERIA_FIRST", "off")

    _one_at_a_time(tmp_path, _the_ledger())

    [entry] = transcript()
    assert [moved["index"] for moved in entry["moved_ahead"]] == [ROOT, *SYMPTOMS]
    assert "double prefix" in entry["moved_ahead"][0]["description"]
    assert entry["round"] == 2 and entry["behind"] == len(CARRIED)
    # Not the criteria-first switch's doing: it was off.
    assert switch_firing.fired([entry]) == []
    lines = "\n".join(runpy.run_path(str(EFFECTS))["effects"]([entry], ""))
    assert "   1  LF.1244 the latest round's defects fixed ahead of those carried over" in lines
