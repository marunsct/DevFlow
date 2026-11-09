"""Each suite dispute's outcome is recorded as one decision (harness review HR2.Q.4).

A dispute could end with its tests kept locked because they passed alone, their service stopped by itself, they were
past the run's cap, or the ruling's quote was not in the standard - and each of those was only a log warning, so the
audit could not judge whether disputes were right.
"""
from __future__ import annotations

import inspect
import json
from types import SimpleNamespace

from app.agents import suite_dispute
from app.graph import dispute_outcomes


def test_a_disputed_test_that_passes_alone_is_recorded_as_passed_alone(tmp_path) -> None:
    line = "`[AC-4] deletes a record` cannot pass for any product that does what its criterion says: it checks x."
    record = dispute_outcomes.outcome(
        shown=["[AC-4] deletes a record", "[AC-5] lists records"],
        called_wrong=[line], passed_alone=[line], reopened=False,
    )
    assert record["passed_alone"] == ["[AC-4] deletes a record"]
    assert record["called_wrong"] == ["[AC-4] deletes a record"]
    assert record["reopened"] is False and record["reopened_tests"] == []
    assert "1 passed alone" in dispute_outcomes.summary(record)
    assert dispute_outcomes.summary(record).startswith("the suite stays locked")

    dispute_outcomes.write(tmp_path, record, sprint="1:0")
    row = json.loads((tmp_path / dispute_outcomes.OUTCOMES_FILE).read_text().splitlines()[0])
    assert row["passed_alone"] == ["[AC-4] deletes a record"] and row["sprint"] == "1:0"


def test_a_reopened_dispute_names_only_the_tests_it_reopened() -> None:
    record = dispute_outcomes.outcome(
        shown=["a", "b", "c"], called_wrong=["`a` x", "`b` y"], past_the_cap=["`b` y"],
        missing=["`c` is missing from the locked suite"], reopened=True,
    )
    assert record["reopened_tests"] == ["a", "c"]
    assert dispute_outcomes.summary(record).startswith("reopened the suite for 2 test(s)")


def test_a_ruling_refused_for_its_quote_is_reported(monkeypatch) -> None:
    monkeypatch.setattr(suite_dispute.structured_verdict_switch, "enabled", lambda: True)
    ruling = SimpleNamespace(
        test="[AC-4] deletes a record", the_test_is_wrong=True,
        the_standard_says="records are kept for ninety days after deletion",
        the_test_asserts="the record is gone at once",
    )
    refused: list[tuple[str, str]] = []
    named = suite_dispute.tests_it_names(
        SimpleNamespace(rulings=[ruling]), ["[AC-4] deletes a record"],
        standard="A deleted record is gone at once.", refused=refused,
    )
    assert named == []
    assert refused == [("[AC-4] deletes a record", "quotes what the standard does not say")]


def test_the_dispute_node_records_the_outcome_on_both_exits() -> None:
    from app.graph import workflow

    source = inspect.getsource(workflow)
    node = source[source.index("def acceptance_dispute_node"):source.index("def _advice_reviews_due")]
    assert 'point="acceptance_dispute"' in node
    assert node.count("_the_outcome(True)") == 1 and node.count("_the_outcome(False)") == 1
    assert "refused=refused" in node
