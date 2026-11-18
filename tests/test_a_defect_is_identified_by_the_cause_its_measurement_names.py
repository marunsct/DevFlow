"""A defect raised from a measurement is identified by the cause that measurement names, not by its wording.

Deep review 2026-11-18, item 1.1: a defect had no kind, no evidence and no stable id. Whether two were one problem was
decided by overlapping words (`recurrence_of`), by a hash of scrubbed wording (the defect ledger) and by the first
sentence (`_refreshed_by_the_round`). Two criteria raised from one template ("[AC-3] ... - the acceptance suite says
this does not work yet") share nearly every word, so a criterion raised after another was fixed counted as that one
coming back - one more failed try charged to a problem nobody had tried.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.sprint import Defect, recurrence_of


def _criterion(cid: str, text: str, tests: list[str], status: str = "open") -> Defect:
    return Defect(
        description=f"[{cid}] {text} - the acceptance suite says this does not work yet.",
        severity="major", reproduction_steps="run the suite", expected_behavior=text,
        actual_behavior="it does not", owner="backend", status=status, source="acceptance suite",
        kind="failing_test", evidence=[{"test": name, "criterion": cid} for name in tests],
        cause_key="failing_test:" + "|".join(sorted(f"test:{name.lower()}" for name in tests)),
    )


def test_a_criterion_raised_after_another_was_fixed_is_not_that_one_coming_back():
    fixed = _criterion("AC-3", "A person can add a note", ["adds a note"], status="fixed")
    raised = _criterion("AC-4", "A person can remove a note", ["removes a note"])

    assert recurrence_of(raised, [fixed]) is None


def test_the_same_failing_test_raised_again_in_other_words_is_the_fixed_defect_coming_back():
    fixed = _criterion("AC-3", "A person can add a note", ["adds a note"], status="fixed")
    again = _criterion("AC-3", "Notes are kept when added", ["adds a note"])
    again = again.model_copy(update={"description": "Adding fails with a server error"})

    assert recurrence_of(again, [fixed]) is fixed


def test_defects_without_evidence_are_still_compared_by_their_words():
    fixed = Defect(description="Regression test fails due to missing y18n module import", severity="major",
                   reproduction_steps="r", expected_behavior="e", actual_behavior="a", owner="testing", status="fixed")
    again = Defect(description="Regression tests fail due to y18n module import issues.", severity="major",
                   reproduction_steps="r", expected_behavior="e", actual_behavior="a", owner="testing")

    assert recurrence_of(again, [fixed]) is fixed


def test_a_defect_saved_before_kinds_existed_still_loads():
    old = {"description": "d", "severity": "major", "reproduction_steps": "r", "expected_behavior": "e",
           "actual_behavior": "a", "owner": "backend", "status": "open"}

    loaded = Defect.model_validate(old)

    assert (loaded.kind, loaded.evidence, loaded.cause_key) == ("", [], "")


def test_the_ledger_follows_one_cause_whatever_its_wording_and_tells_two_alike_worded_causes_apart():
    from app.observability.defect_ledger import defect_id

    first = _criterion("AC-3", "A person can add a note", ["adds a note"])
    reworded = first.model_copy(update={"description": "Notes cannot be added: 500 from the server"})
    other = _criterion("AC-3", "A person can add a note", ["adds a note with a title"])

    assert defect_id(first) == defect_id(reworded)
    assert defect_id(first) != defect_id(other)


def test_the_cause_key_does_not_depend_on_the_order_or_the_place_of_its_evidence():
    from app.sprint import cause

    one = cause.cause_key("compile_error", [
        {"file": "src/a.rs", "line": 10, "code": "E0425"}, {"file": "src/b.rs", "line": 3, "code": "E0433"}])
    moved = cause.cause_key("compile_error", [
        {"file": "src/b.rs", "line": 9, "code": "E0433"}, {"file": "src/a.rs", "line": 12, "code": "E0425"}])

    assert one and one == moved
    assert cause.cause_key("compile_error", []) == ""


def test_criteria_carried_by_the_same_measured_failing_tests_are_one_defect_without_the_suite_s_result():
    from app.agents.specialists import ReportedDefect
    from app.graph import workflow

    def reported(cid, text, tests):
        return ReportedDefect(
            description=f"[{cid}] {text} - the acceptance suite says this does not work yet.",
            severity="major", reproduction_steps="run the suite", expected_behavior=text,
            actual_behavior="fails", owner="backend", kind="failing_test",
            evidence=[{"test": name, "criterion": cid} for name in tests],
        )

    merged = workflow._one_defect_per_failing_tests([
        reported("AC-16", "The interface answers as described", ["status codes"]),
        reported("AC-17", "Invalid records are refused", ["status codes"]),
        reported("AC-15", "Records can be saved", ["saves a record"]),
    ], {})

    assert [d.description.split(" ")[0] for d in merged] == ["[AC-16][AC-17]", "[AC-15]"]


def test_an_open_defect_raised_again_for_the_same_cause_in_new_words_is_refreshed_not_queued_twice():
    from app.graph import workflow
    from app.sprint import RemediationCycle

    open_one = _criterion("AC-3", "A person can add a note", ["adds a note"])
    again = _criterion("AC-3", "A person can add a note", ["adds a note"]).model_copy(
        update={"description": "Adding a note answers 500. The server logged a missing table."})
    cycle = RemediationCycle(sprint_goal="g", defects=[open_one])

    refreshed, repeated = workflow._refreshed_by_the_round(cycle, [again], 2)

    assert repeated == [again]
    assert refreshed.defects[0].description.startswith("Adding a note answers 500")
    assert refreshed.defects[0].found_in_round == 2


def _round(monkeypatch, tmp_path, saved, failing, compiler=("", [])):
    from app.acceptance import suite
    from app.graph import acceptance_nodes
    from app.stacks import compiler_errors

    monkeypatch.setattr(acceptance_nodes, "_failing_due", lambda state: (failing, "npm run test:acceptance"))
    monkeypatch.setattr(suite, "last_result", lambda root: saved)
    monkeypatch.setattr(acceptance_nodes, "_root", lambda state: str(tmp_path))
    monkeypatch.setattr(acceptance_nodes, "_stack", lambda state: SimpleNamespace(product_kind="http_api"))
    monkeypatch.setattr(compiler_errors, "the_errors_found", lambda root, runner=None: compiler)
    return acceptance_nodes.failing_due_defects({}, [])


def test_a_failing_criterion_is_raised_with_the_tests_that_failed_as_its_evidence(monkeypatch, tmp_path):
    failing = [{"id": "AC-2", "text": "A note can be read", "tests": [
        {"name": "[AC-2] reads a note", "outcome": "failed", "message": "expected 200, got 404"},
        {"name": "[AC-2] lists notes", "outcome": "passed", "message": ""}]}]

    defects = _round(monkeypatch, tmp_path, {"ran": True, "runtime_problems": []}, failing)

    criterion = next(d for d in defects if d.description.startswith("[AC-2]"))
    assert criterion.kind == "failing_test"
    assert [e["test"] for e in criterion.evidence] == ["[AC-2] reads a note"]


def test_a_product_that_does_not_start_is_raised_with_its_error_and_the_compiler_s_errors_as_evidence(
        monkeypatch, tmp_path):
    from app.acceptance import suite

    saved = {"ran": True, "runtime_problems": [], "problem": suite.the_product_did_not_start(
        "Compiling notes\nerror[E0425]: cannot find value `pool` in this scope\n --> src/main.rs:32:5\n"
        "Error: Process from config.webServer was not able to start. Exit code: 101")}
    compiler = ("\n\nThe compiler also reports: X", [("src/main.rs", 32, 2304, "Cannot find name 'pool'.")])

    defects = _round(monkeypatch, tmp_path, saved, [{"id": "AC-1", "text": "x", "tests": []}], compiler)

    start = defects[0]
    assert start.kind == "start_failure"
    assert any("E0425" in e.get("error", "") for e in start.evidence)
    assert any(e.get("file") == "src/main.rs" and e.get("code") == "2304" for e in start.evidence)
