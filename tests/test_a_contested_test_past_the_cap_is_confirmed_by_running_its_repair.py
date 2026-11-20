"""Behind `CONTESTED_TESTS_CONFIRMED`: a ruling past the reclassification cap counts only when the harness confirms it.

Measured on one run: two locked tests sent the whole sign-in answer as the bearer token, the dispute rightly called
them wrong, but six earlier rulings quoting the same inline call had each taken a place under the cap, and the sprint
sat at 20 of 21 criteria for about an hour. A model's word alone must still never unlock a test: past the cap the
harness runs the locked test alone (it must fail), a corrected copy beside it (it must pass) and the copy against a
deliberately broken product (it must fail), and only then sends the test to QA's repair. Rulings quoting identical
code at fault are one cause for the cap.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

SWITCH = "CONTESTED_TESTS_CONFIRMED"

LOCKED = '''import requests


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _signup_and_signin(client):
    client.post("/signup", json={"name": "a"})
    signin_resp = client.post("/signin", json={"name": "a"})
    return "a", signin_resp.json()


def test_ac2_lists_notes(client):
    resp = client.get("/notes", headers=_auth(_signup_and_signin(client)[1]))
    assert resp.status_code == 200


def test_ac3_reads_a_note(client):
    resp = client.get("/notes/1", headers=_auth(_signup_and_signin(client)[1]))
    assert resp.status_code == 200


def test_ac4_health(client):
    resp = client.get("/health", headers=_auth(_signup_and_signin(client)[0]))
    assert resp.status_code == 200
'''

PRODUCT = '''def authorised(header, token):
    return header == f"Bearer {token}"
'''

FAULTY = "_signup_and_signin(client)[1]"
RIGHT = '_signup_and_signin(client)[1]["token"]'

RECORD = {"project": "", "acceptance_dir": "tests/acceptance", "acceptance_pattern": "test_*.py",
          "acceptance_test": ["pytest", "tests/acceptance"], "acceptance_report": "report.xml"}


def _workspace(tmp_path: Path) -> Path:
    suite_file = tmp_path / "tests" / "acceptance" / "test_suite.py"
    suite_file.parent.mkdir(parents=True, exist_ok=True)
    suite_file.write_text(LOCKED, encoding="utf-8")
    (tmp_path / "app").mkdir(exist_ok=True)
    (tmp_path / "app" / "auth.py").write_text(PRODUCT, encoding="utf-8")
    return suite_file


def _product_runner(tmp_path: Path, ran: list[str]):
    """The project's runner, simulated: a test sending the sign-in object as its token is refused; a test sending the
    token passes while the product compares headers rightly; `CannedAnswer(200)` passes whatever the product does."""

    def run(argv, category, working_directory):
        file = argv[-1]
        ran.append(file)
        text = (tmp_path / file).read_text(encoding="utf-8")
        product_right = "header == f" in (tmp_path / "app" / "auth.py").read_text(encoding="utf-8")
        cases = []
        for name in re.findall(r"def (test_\w+)", text):
            body = text.split(f"def {name}", 1)[1].split("\ndef ", 1)[0]
            if "CannedAnswer(200)" in body or "[0]" in body:
                passed = True
            elif '[1]["token"]' in body:
                passed = product_right
            else:
                passed = False
            cases.append(f'<testcase classname="x" name="{name}"/>' if passed else
                         f'<testcase classname="x" name="{name}"><failure message="assert 401 == 200"/></testcase>')
        (tmp_path / "report.xml").write_text(f"<testsuite>{''.join(cases)}</testsuite>", encoding="utf-8")
        return {"returncode": 0 if all("failure" not in c for c in cases) else 1, "stdout": ""}

    return run


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    from app.acceptance import suite
    from app.graph import contested_tests

    suite_file = _workspace(tmp_path)
    monkeypatch.setattr(suite, "suite_files", lambda root: [suite_file])
    monkeypatch.setattr(contested_tests, "_the_record", lambda root: dict(RECORD))
    monkeypatch.setattr(contested_tests, "_the_product", lambda root: (tmp_path, set()))
    return suite_file


def _confirm(tmp_path, repair, ran):
    from app.graph import contested_tests

    runs = contested_tests._Run(tmp_path, dict(RECORD), _product_runner(tmp_path, ran))
    return contested_tests.confirm(tmp_path, ["test_ac2_lists_notes"], repair, runs)


def test_a_repair_that_passes_and_still_catches_a_broken_product_is_confirmed(tmp_path, workspace):
    from app.graph.contested_tests import Repair

    ran: list[str] = []
    assert _confirm(tmp_path, Repair("test_ac2_lists_notes", FAULTY, RIGHT), ran) == ""
    # The locked file alone, then the copy, then the copy against a deliberate change.
    assert ran[0] == "tests/acceptance/test_suite.py" and len(ran) >= 3
    assert all("contested_copy" in file for file in ran[1:])
    # The locked file is untouched, the copy is gone, the product is as it was.
    assert workspace.read_text(encoding="utf-8") == LOCKED
    assert list(workspace.parent.glob("*contested_copy*")) == []
    assert (tmp_path / "app" / "auth.py").read_text(encoding="utf-8") == PRODUCT


def test_a_repair_whose_copy_still_fails_stays_locked(tmp_path, workspace):
    from app.graph.contested_tests import Repair

    ran: list[str] = []
    why = _confirm(tmp_path, Repair("test_ac2_lists_notes", FAULTY, '_signup_and_signin(client)[1]["name"]'), ran)
    assert why == "the corrected copy does not pass against the product as it is"


def test_a_repair_that_passes_against_a_broken_product_too_stays_locked(tmp_path, workspace):
    from app.graph.contested_tests import Repair

    ran: list[str] = []
    repair = Repair("test_ac2_lists_notes", 'client.get("/notes", headers=_auth(_signup_and_signin(client)[1]))',
                    "CannedAnswer(200)")
    assert _confirm(tmp_path, repair, ran) == "the corrected copy still passes against a deliberately broken product"
    assert (tmp_path / "app" / "auth.py").read_text(encoding="utf-8") == PRODUCT


@pytest.mark.parametrize("corrected", ['_signup_and_signin(client)[1] or pytest.skip("x")', "None  # ",
                                       "_signup_and_signin(client)[1]); return (None"])
def test_a_repair_that_brings_in_a_skip_a_comment_or_an_exit_is_refused_unrun(tmp_path, workspace, corrected):
    from app.graph.contested_tests import Repair

    ran: list[str] = []
    assert _confirm(tmp_path, Repair("test_ac2_lists_notes", FAULTY, corrected), ran).startswith("the correction brings in")
    assert ran == []


def _dispute(tmp_path, monkeypatch, repairs, *, causes_so_far, run=None, switch="on"):
    from workflow_nodes import a_dispute

    monkeypatch.setenv(SWITCH, switch)
    failing = [
        ("test_ac2_lists_notes", "AC-2 notes are listed", "assert 401 == 200"),
        ("test_ac3_reads_a_note", "AC-3 a note is read", "assert 401 == 200"),
        ("test_ac4_health", "AC-4 health answers", "assert 401 == 200"),
    ]
    lines = [f"`{name}` cannot pass for any product that does what its criterion says: it sends the sign-in answer"
             for name, _, _ in failing]
    answer = SimpleNamespace(repairs=[
        SimpleNamespace(test=test, the_faulty_code=faulty, the_corrected_code=corrected)
        for test, faulty, corrected in repairs])
    deferred: list = []
    patches = {
        "app.graph.workflow._run_gated_agent": lambda state, config, **kwargs: {"__suite_dispute__": answer},
        "app.graph.acceptance_nodes.defer_what_is_beyond_repair":
            lambda state, beyond, why: deferred.append((list(beyond), list(why))),
    }
    if run is not None:
        # The project's runner, its contract and its product, as `_product_runner` simulates them.
        patches.update({
            "app.stacks.scaffold.sandbox_runner": lambda root: run,
            "app.graph.contested_tests._the_record": lambda root: dict(RECORD),
            "app.graph.contested_tests._the_product": lambda root: (tmp_path, set()),
        })
    _, asked = a_dispute(tmp_path, failing, lines, suite_text=LOCKED, reopened={"stage": "acceptance_author"},
                         state={"suite_reclassified_causes": causes_so_far}, patches=patches)
    return lines, asked, deferred


def test_rulings_quoting_the_same_code_at_fault_take_one_place_under_the_cap(tmp_path, monkeypatch):
    # One place left: the two rulings on the identical inline call are one cause; the different fault waits.
    lines, asked, _ = _dispute(tmp_path, monkeypatch, [
        ("test_ac2_lists_notes", FAULTY, RIGHT), ("test_ac3_reads_a_note", FAULTY, RIGHT),
        ("test_ac4_health", "_signup_and_signin(client)[0]", RIGHT)], causes_so_far=1)

    (reopen,) = asked["reopen"]
    assert reopen["broken"] == lines[:2] and reopen["causes"] == 1


def test_identical_code_is_one_cause_and_different_code_or_prose_is_not(tmp_path, monkeypatch):
    from app.acceptance import suite
    from app.graph.contested_tests import Repair, by_shared_expression

    suite_file = _workspace(tmp_path)
    monkeypatch.setattr(suite, "suite_files", lambda root: [suite_file])
    rulings = ["`a` cannot pass: x", "`b` cannot pass: x", "`c` cannot pass: x", "`d` cannot pass: x", "`e` x"]
    repairs = [Repair("a", FAULTY, RIGHT), Repair("b", FAULTY, RIGHT), Repair("c", "_signup_and_signin(client)[0]", RIGHT),
               Repair("d", "_signup_and_signin(other)[1]", RIGHT), Repair("e", "[1]", RIGHT)]
    assert by_shared_expression([[r] for r in rulings], repairs, tmp_path) == [
        rulings[:2], [rulings[2]], [rulings[3]], [rulings[4]]]


def test_a_confirmed_ruling_past_the_cap_goes_to_qa_with_its_confirmed_repair(tmp_path, monkeypatch):
    from app.graph.contested_tests import SAYS

    ran: list[str] = []
    _workspace(tmp_path)
    lines, asked, deferred = _dispute(tmp_path, monkeypatch, [("test_ac2_lists_notes", FAULTY, RIGHT)],
                                      causes_so_far=2, run=_product_runner(tmp_path, ran))

    (reopen,) = asked["reopen"]
    (line,) = reopen["broken"]
    assert line.startswith(lines[0]) and SAYS in line and f"`{RIGHT}`" in line
    assert reopen["causes"] == 1
    # The others, called wrong with no confirmed repair, stay past the cap and are deferred as before.
    ((criteria, _),) = deferred
    assert criteria == ["AC-3", "AC-4"]


def test_a_refuted_ruling_past_the_cap_stays_locked_and_deferred(tmp_path, monkeypatch):
    ran: list[str] = []
    _workspace(tmp_path)
    _, asked, deferred = _dispute(tmp_path, monkeypatch, [("test_ac2_lists_notes", FAULTY, "CannedAnswer(200)")],
                                  causes_so_far=2, run=_product_runner(tmp_path, ran))

    assert asked["reopen"] == []
    ((criteria, _),) = deferred
    assert criteria == ["AC-2", "AC-3", "AC-4"]


def test_off_the_dispute_neither_groups_by_code_nor_runs_anything(tmp_path, monkeypatch):
    ran: list[str] = []
    _workspace(tmp_path)
    lines, asked, _ = _dispute(tmp_path, monkeypatch, [
        ("test_ac2_lists_notes", FAULTY, RIGHT), ("test_ac3_reads_a_note", FAULTY, RIGHT)],
        causes_so_far=1, run=_product_runner(tmp_path, ran), switch="off")

    (reopen,) = asked["reopen"]
    assert reopen["broken"] == lines[:1] and ran == []


def test_the_answer_asks_for_repairs_only_with_the_switch_on(monkeypatch):
    from app.agents import suite_dispute

    monkeypatch.setenv("STRUCTURED_DISPUTE_VERDICT", "on")
    monkeypatch.setenv(SWITCH, "off")
    assert "repairs" not in suite_dispute.answer_format().model_fields
    monkeypatch.setenv(SWITCH, "on")
    shape = suite_dispute.answer_format()
    assert "repairs" in shape.model_fields and "rulings" in shape.model_fields
    answer = shape.model_validate({"cannot_pass": [], "rulings": [
        {"test": "t", "the_test_is_wrong": True, "the_test_asserts": "a", "the_standard_says": "s"}],
        "repairs": [{"test": "t", "the_faulty_code": FAULTY, "the_corrected_code": RIGHT}]})
    from app.graph.contested_tests import proposed_repairs

    assert [(r.test, r.faulty, r.corrected) for r in proposed_repairs(answer)] == [("t", FAULTY, RIGHT)]


def test_its_words_avoid_the_banned_ones_and_carry_its_firing_signal():
    from app.agents import suite_dispute
    from app.graph import contested_tests
    from app.observability.switch_firing import SIGNALS

    line = contested_tests.with_the_confirmation("`t` cannot pass", contested_tests.Repair("t", FAULTY, RIGHT))
    texts = [line, suite_dispute.REPAIRS_DESCRIPTION, contested_tests.explanation,
             *(field.description or "" for field in suite_dispute.ProposedRepair.model_fields.values())]
    banned = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
    assert not any(banned.search(text) for text in texts)
    assert SIGNALS[SWITCH] in line
