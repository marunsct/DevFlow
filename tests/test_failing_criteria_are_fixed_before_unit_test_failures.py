"""With `FIX_ORDER_CRITERIA_FIRST` on, a fix round sends failing criteria and release findings before the rest.

Measured on one run: a sprint's second attempt raised the unit-test failure, six regressions of single unit tests, an
unstyled page, a failed install and a failed build, then three failing acceptance criteria. Fixers went in the order
raised, two side by side, and the criteria waited more than 35 minutes behind unit-test fixes. Only the order may
change: nothing is dropped, and a product that does not start is still fixed alone first.
"""

from __future__ import annotations

import pytest
import the_fix_stage

from app.graph.acceptance_nodes import THE_PRODUCT_DOES_NOT_START

CRITERIA = (10, 11, 12)


def _criterion(ids: str, text: str):
    first = ids.strip("[]").split("][")[0]
    return the_fix_stage.a_defect(f"{ids} {text} - the acceptance suite says this does not work yet.",
                                  affected_files=[], kind="failing_test",
                                  evidence=[{"test": f"{first} {text}", "criterion": first}])


def _regression(test_file: str, name: str):
    return the_fix_stage.a_defect(f"Regression: `unit: {test_file} › {name}` passed before a fix was kept, and fails now.",
                                  affected_files=[])


def _the_round_as_raised():
    """Thirteen defects in the order one measured round raised them."""
    return [
        the_fix_stage.a_defect("The unit tests fail. It says: 5 failing", affected_files=["web/src/hooks/useEntries.ts"],
                               kind="failing_test", evidence=[{"test": "unit: adds an entry"}]),
        *(_regression("tests/components/AddEntryForm.test.tsx", f"case {n}") for n in range(3)),
        *(_regression("tests/components/FilterBar.test.tsx", f"case {n}") for n in range(3)),
        the_fix_stage.a_defect("The interface is not styled: the only stylesheet is the one the scaffold wrote.",
                               affected_files=["web/src/index.css"], source="page check", owner="ui_ux"),
        the_fix_stage.a_defect("The project's dependencies do not install, so nothing its manifests declare is there.",
                               affected_files=[]),
        the_fix_stage.a_defect("The project's production build fails, so what would be shipped does not exist.",
                               affected_files=[]),
        _criterion("[AC-3][AC-10]", "Edit an entry's title"),
        _criterion("[AC-13]", "Entries can be added, edited and deleted"),
        _criterion("[AC-14]", "Entries persist between page loads"),
    ]


@pytest.fixture
def two_side_by_side(monkeypatch):
    monkeypatch.setenv("HARNESS_MAX_PARALLEL", "2")


@pytest.fixture
def transcript(monkeypatch, tmp_path):
    from app.observability.transcript import read_transcript

    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    # A node run on its own has no graph config to name its run by.
    monkeypatch.setattr("app.observability.transcript._run_id_from_config", lambda: "r")
    return lambda: read_transcript("r", {"fix_order"})


def _the_round_side_by_side(root, defects) -> list[list[int]]:
    """Every batch the fix round sends, in order, until it hands back to the test round."""
    tried: list[str] = []
    batches: list[list[int]] = []
    while True:
        state = the_fix_stage.a_state(root, *defects, fixes_tried=list(tried))
        update, seen = the_fix_stage.run(root, state, side_by_side=True)
        if update.get("stage") == "test_and_triage":
            return batches
        sent = list(update.get("fix_batch") or [int(stage.rsplit("_", 1)[1]) for stage, _ in seen.shown])
        batches.append(sent)
        tried += [f"defect_fix_2_{index}" for index in sent]


def test_side_by_side_the_failing_criteria_go_in_the_first_batch(monkeypatch, tmp_path, two_side_by_side):
    monkeypatch.setenv("FIX_ORDER_CRITERIA_FIRST", "on")

    update, _ = the_fix_stage.run(tmp_path, the_fix_stage.a_state(tmp_path, *_the_round_as_raised()), side_by_side=True)

    assert update["fix_batch"] == [10, 11]


def test_side_by_side_with_the_switch_off_the_defects_go_as_raised(monkeypatch, tmp_path, two_side_by_side):
    monkeypatch.setenv("FIX_ORDER_CRITERIA_FIRST", "off")

    update, _ = the_fix_stage.run(tmp_path, the_fix_stage.a_state(tmp_path, *_the_round_as_raised()), side_by_side=True)

    assert update["fix_batch"] == [0, 1]


def test_every_open_defect_is_still_sent_in_the_same_round(monkeypatch, tmp_path, two_side_by_side):
    """The regressions included: the order changes, the round's work does not."""
    monkeypatch.setenv("FIX_ORDER_CRITERIA_FIRST", "on")

    batches = _the_round_side_by_side(tmp_path, _the_round_as_raised())

    assert sorted(index for batch in batches for index in batch) == list(range(13))
    assert batches[0] == [10, 11] and 12 in batches[1]


def test_a_product_that_does_not_start_is_still_fixed_alone_first(monkeypatch, tmp_path, two_side_by_side):
    monkeypatch.setenv("FIX_ORDER_CRITERIA_FIRST", "on")
    start = the_fix_stage.a_defect(THE_PRODUCT_DOES_NOT_START, affected_files=[], kind="start_failure")

    update, seen = the_fix_stage.run(tmp_path, the_fix_stage.a_state(tmp_path, *_the_round_as_raised(), start),
                                     side_by_side=True)

    assert not update.get("fix_batch")
    assert [stage for stage, _ in seen.shown] == ["defect_fix_2_13"]


def test_one_at_a_time_the_criteria_come_first_then_the_rest_as_raised(monkeypatch, tmp_path):
    monkeypatch.setenv("FIX_ORDER_CRITERIA_FIRST", "on")
    defects = _the_round_as_raised()
    sent: list[str] = []
    cursor = 0

    while True:
        update, seen = the_fix_stage.run(tmp_path, the_fix_stage.a_state(tmp_path, *defects, defect_cursor=cursor))
        if update.get("stage") == "test_and_triage":
            break
        sent += [stage for stage, _ in seen.shown]
        cursor = update["defect_cursor"]

    assert sent == [f"defect_fix_2_{index}" for index in (10, 11, 12, *range(10))]


def test_a_round_whose_order_changed_is_recorded_once_with_what_moved_ahead(monkeypatch, tmp_path, two_side_by_side,
                                                                           transcript):
    from app.observability import switch_firing

    monkeypatch.setenv("FIX_ORDER_CRITERIA_FIRST", "on")

    _the_round_side_by_side(tmp_path, _the_round_as_raised())

    [entry] = transcript()
    assert [moved["index"] for moved in entry["moved_ahead"]] == list(CRITERIA)
    assert entry["round"] == 2 and entry["behind"] == 10
    assert switch_firing.fired([entry]) == ["FIX_ORDER_CRITERIA_FIRST"]


def test_nothing_is_recorded_with_the_switch_off(monkeypatch, tmp_path, two_side_by_side, transcript):
    monkeypatch.setenv("FIX_ORDER_CRITERIA_FIRST", "off")

    the_fix_stage.run(tmp_path, the_fix_stage.a_state(tmp_path, *_the_round_as_raised()), side_by_side=True)

    assert transcript() == []


@pytest.mark.parametrize("finding", [
    "Requests at the edges of the interface contract are not handled: GET /entries/0 answered 500",
    "The server fails on a request it should answer or refuse: POST /entries answered 500",
    "A check of the page in a browser finds: the list is empty after a reload",
])
def test_what_a_release_probe_finds_goes_ahead_of_a_unit_test_failure(monkeypatch, finding):
    from app.graph import order_of_fixes

    monkeypatch.setenv("FIX_ORDER_CRITERIA_FIRST", "on")
    defects = [the_fix_stage.a_defect("The unit tests fail."), the_fix_stage.a_defect(finding)]

    assert order_of_fixes.ordered(defects, [0, 1]) == [1, 0]
