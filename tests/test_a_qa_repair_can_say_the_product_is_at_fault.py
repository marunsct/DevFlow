"""Behind `QA_SAYS_THE_PRODUCT_IS_AT_FAULT`: a dispute's repair may end when QA finds no fault in the test, only on evidence.

Measured on one run: QA concluded a crash was "likely a product bug", could not say so, and spent about 90 minutes.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import switches
from app.acceptance import suite
from app.graph import acceptance_nodes, product_at_fault
from app.observability import provenance

_TEST = "[AC-1] saving answers 201"
_STANDARD = "saving a record answers 201 with the record"
_FAILURE = "Expected: 201 Received: 500"
_CLAIM = f'{product_at_fault.MARK}: {_TEST}: the standard says "{_STANDARD}"; the run shows "{_FAILURE}"'
_BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
_STATE = {"suite_repairs": 1, "suite_repaired_tests": ["earlier"], "suite_reclassified_tests": ["earlier"]}


def _result(outcome: str = "failed", message: str = f"Error {_FAILURE} at line 3"):
    test = SimpleNamespace(name=f"api.spec.js:1:1 › {_TEST}", outcome=outcome, message=message)
    return SimpleNamespace(ran=True, report=SimpleNamespace(tests=[test]), server_log="")


@pytest.fixture
def root(monkeypatch, tmp_path):
    monkeypatch.setenv("QA_SAYS_THE_PRODUCT_IS_AT_FAULT", "on")
    spec = tmp_path / "acceptance" / "api.spec.js"
    spec.parent.mkdir()
    spec.write_text(f"test('{_TEST}', async () => {{}});\n")
    monkeypatch.setattr(suite, "suite_files", lambda _root: [spec])
    copy = tmp_path / suite.SNAPSHOT_DIR / "acceptance" / "api.spec.js"
    copy.parent.mkdir(parents=True)
    copy.write_text(spec.read_text())
    return str(tmp_path)


def _claimed(root, *claims):
    assert product_at_fault.offered(_STATE, root, [_TEST]) == [product_at_fault.RULE]
    assert product_at_fault.take_claims(root, [*claims, "AC-9: nothing can check this"]) == ["AC-9: nothing can check this"]


def _evidence(root, result=None, problems=()):
    return product_at_fault.evidence(root, result or _result(), list(problems), [f"AC-1: {_STANDARD}."])


def test_a_claim_with_its_evidence_stands_and_charges_nothing(root):
    _claimed(root, _CLAIM)
    lines = _evidence(root)
    assert lines and _STANDARD in lines[0]
    assert product_at_fault.settled(root, lines) == {
        "suite_repairs": 1, "suite_repaired_tests": ["earlier"], "suite_reclassified_tests": ["earlier"],
    }


def test_the_same_test_is_claimed_once_in_a_run(root):
    _claimed(root, _CLAIM)
    product_at_fault.settled(root, _evidence(root))
    assert product_at_fault.offered(_STATE, root, [_TEST]) == []
    assert product_at_fault.take_claims(root, [_CLAIM]) == []
    assert _evidence(root) == []


@pytest.mark.parametrize("claim", [
    f"{product_at_fault.MARK}: {_TEST}",
    f'{product_at_fault.MARK}: {_TEST}: the standard says "an invented sentence nobody wrote"; the run shows "{_FAILURE}"',
    f'{product_at_fault.MARK}: {_TEST}: the standard says "{_STANDARD}"; the run shows "a failure that was not measured"',
    f'{product_at_fault.MARK}: {_TEST}: the standard says "201"; the run shows "{_FAILURE}"',
    f'{product_at_fault.MARK}: another test: the standard says "{_STANDARD}"; the run shows "{_FAILURE}"',
])
def test_a_claim_without_evidence_unlocks_nothing(root, claim):
    _claimed(root, claim)
    assert _evidence(root) == []
    assert product_at_fault.settled(root, []) == {}


def test_a_changed_suite_is_a_repair(root):
    _claimed(root, _CLAIM)
    (Path(root) / "acceptance" / "api.spec.js").write_text("// changed\n")
    assert _evidence(root) == []


def test_a_harness_check_outranks_the_claim(root):
    _claimed(root, _CLAIM)
    assert _evidence(root, problems=["the test's own code throws"]) == []


def test_a_test_that_passes_is_not_the_product_s_failure(root):
    _claimed(root, _CLAIM)
    assert _evidence(root, _result("passed")) == []


def test_every_test_sent_must_be_claimed(root):
    product_at_fault.offered(_STATE, root, [_TEST, "[AC-2] another"])
    product_at_fault.take_claims(root, [_CLAIM])
    assert _evidence(root) == []


def test_off_nothing_is_offered_or_upheld(root, monkeypatch):
    _claimed(root, _CLAIM)
    monkeypatch.setenv("QA_SAYS_THE_PRODUCT_IS_AT_FAULT", "off")
    assert product_at_fault.offered(_STATE, root, [_TEST]) == []
    assert _evidence(root) == []


def _reopen(monkeypatch, tmp_path, *, reclassifying: bool):
    monkeypatch.setattr(acceptance_nodes, "_decide", lambda *_a, **_k: None)
    state = {"repository": SimpleNamespace(root_path=str(tmp_path)), "suite_repairs": 0}
    return acceptance_nodes.reopen_the_suite_for(
        state, [f"`{_TEST}` cannot pass: a reason here"], reclassifying=reclassifying)


def test_a_dispute_s_repair_offers_the_answer(root, monkeypatch, tmp_path):
    assert product_at_fault.RULE in _reopen(monkeypatch, tmp_path, reclassifying=True)["acceptance_feedback"]


def test_a_repair_a_harness_check_sent_does_not(root, monkeypatch, tmp_path):
    assert product_at_fault.RULE not in _reopen(monkeypatch, tmp_path, reclassifying=False)["acceptance_feedback"]


def test_the_switch_ships_off_and_is_registered():
    assert "QA_SAYS_THE_PRODUCT_IS_AT_FAULT" in switches.EXPERIMENTS
    assert "QA_SAYS_THE_PRODUCT_IS_AT_FAULT" not in switches.EXPERIMENTS_ON
    assert provenance.SWITCHES["QA_SAYS_THE_PRODUCT_IS_AT_FAULT"] == "app.graph.product_at_fault"
    compose = (Path(__file__).parent.parent / "docker-compose.yml").read_text(encoding="utf-8")
    assert "QA_SAYS_THE_PRODUCT_IS_AT_FAULT: ${QA_SAYS_THE_PRODUCT_IS_AT_FAULT:-off}" in compose
    assert product_at_fault.ON_BY_DEFAULT is False


def test_the_rule_bans_the_words():
    assert not _BANNED.search(product_at_fault.RULE)
