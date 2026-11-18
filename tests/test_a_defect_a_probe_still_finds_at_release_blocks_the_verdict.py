"""A defect a harness probe still finds at release is named in the completion gaps and blocks the verdict.

Deep review 2026-11-18, item B2: a product was delivered with the concurrent-write defect the harness's own probe had
raised still open, and its gap list said nothing. The release re-ran only the contract's bare checks and, of the
concurrent-write probe, named only what it had not asked.
"""
from __future__ import annotations

from types import SimpleNamespace

from app import completion_verdict
from app.acceptance import concurrent_write_probe, interface_contract, junit, suite
from app.acceptance.criteria import number
from app.graph import delivery


def _a_green_locked_suite(tmp_path, monkeypatch) -> None:
    (tmp_path / ".project-directory").write_text("notes\n")
    suite.save_criteria(tmp_path, number("# Brief\n## Features\n- Add a note\n"))
    spec = tmp_path / "notes" / "acceptance" / "notes.spec.js"
    spec.parent.mkdir(parents=True)
    spec.write_text("test('[AC-1] adds', ()=>{});\n")
    suite.lock(tmp_path)
    report = junit.Report(found=True, tests=[junit.TestResult(name="[AC-1] adds")])
    monkeypatch.setattr(suite, "run", lambda root: suite._judged(
        root, suite.AcceptanceResult(ran=True, command="npm run test:acceptance", report=report), True))
    monkeypatch.setattr("app.graph.workflow._stop_if_cancelled", lambda run_id: None)


def _release(tmp_path) -> list[str]:
    update = delivery.release({"repository": SimpleNamespace(root_path=str(tmp_path)),
                               "product_intake": SimpleNamespace(product_name="Notes")},
                              {"configurable": {"thread_id": "t"}}, None)
    return [str(gap) for gap in update.get("completion_gaps") or []]


def test_writes_lost_at_once_at_release_ship_as_a_blocking_gap_in_the_defect_s_words(tmp_path, monkeypatch) -> None:
    _a_green_locked_suite(tmp_path, monkeypatch)
    monkeypatch.setenv("CONCURRENT_WRITE_PROBE", "on")
    create = interface_contract.parse(["AC-1 POST /notes -> 201"])[0][0]
    found = [(create, {"sent": 16, "statuses": [201] * 16, "same_id": [3, 3], "body": {"title": "milk"},
                       "list": "/notes", "listed": 14, "made": 16})]
    # The probe starts the product in the sandbox: what it found is given here.
    monkeypatch.setattr(concurrent_write_probe, "concurrent_write_errors", lambda root, runner=None: found)

    gaps = _release(tmp_path)

    description = concurrent_write_probe.concurrent_write_description(found)
    carried = [gap for gap in gaps if description in gap]
    assert carried, gaps
    assert "`GET /notes` listed 14 of the 16 created" in carried[0]
    assert all(completion_verdict.is_blocking(gap) for gap in carried)
    assert completion_verdict.verdict(gaps) == completion_verdict.NOT_DELIVERABLE


def test_a_probe_that_finds_nothing_at_release_adds_no_gap(tmp_path, monkeypatch) -> None:
    _a_green_locked_suite(tmp_path, monkeypatch)
    monkeypatch.setenv("CONCURRENT_WRITE_PROBE", "on")
    monkeypatch.setattr(concurrent_write_probe, "concurrent_write_errors", lambda root, runner=None: [])

    gaps = _release(tmp_path)

    assert not any(concurrent_write_probe.CONCURRENT_WRITES_LOST in gap for gap in gaps), gaps
