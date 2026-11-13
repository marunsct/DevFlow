"""When the contradiction call's rulings are dropped, the rulings file says how many it gave and why each was dropped.

Measured: a run whose call kept no ruling - its locked suite then carried the specification's self-contradicting
example and its fixers chased two tests no product could pass - could not be diagnosed: the reasons were only in the
worker's log, and a deploy had recreated the worker.
"""
import json

from tests.test_a_contradiction_left_open_is_settled_before_the_build import (  # noqa: F401 - the fixture
    RULINGS_FILE, Model, _decide, _reply, on,
)


def test_a_rejected_ruling_is_recorded_with_its_reason(tmp_path, on):
    _decide(tmp_path, Model(_reply(first="GET /health answers with nothing at all")))
    saved = json.loads((tmp_path / RULINGS_FILE).read_text())
    assert saved["rulings"] == [] and saved["answered"] == 1
    assert saved["rejected"] == ["finding 1: a quote is not in the specification word for word"]


def test_an_unreadable_answer_is_recorded_as_such(tmp_path, on):
    _decide(tmp_path, Model("not json at all"))
    saved = json.loads((tmp_path / RULINGS_FILE).read_text())
    assert saved["rulings"] == [] and saved["answered"] == 0
    assert saved["rejected"] == ["the call gave no readable answer"]


def test_a_kept_ruling_leaves_no_rejection(tmp_path, on):
    _decide(tmp_path, Model(_reply()))
    saved = json.loads((tmp_path / RULINGS_FILE).read_text())
    assert len(saved["rulings"]) == 1 and saved["answered"] == 1 and "rejected" not in saved
