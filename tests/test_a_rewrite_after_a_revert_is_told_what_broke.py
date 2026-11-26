"""A fix after a revert is told what the reverted change broke; a rewrite reverted twice for one test is not asked a
third time; a schema finding whose fix broke a passing test is set aside as doubtful (LF.1547).

Measured on two runs. A schema-conformance finding ("Token lacks field(s) signin") was rewritten alone three times;
each rewrite of the same file broke the same unit test, was reverted, and the next made the same change, until the
defect went to a person. The later requests carried the broken test's name only - never what its runner said, nor the
change that broke it. On the other run, a fix of two files was reverted twice for the same two criteria's tests.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import the_fix_stage
from the_fix_stage import a_defect, a_state

from app.agents.specialists import SpecialistOutput

CAPTURED = Path(__file__).parent / "captured"
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

#: The concurrent-writes defect of the second run, as its ledger recorded it.
WRITES_AT_ONCE = ("Writes made at the same moment are not each kept: `POST /notes` was sent 16 creates at once, each "
                  "with the body `{\"title\": \"test title\", \"body\": \"test body\"}`: they answered 201 x2, 500 x14.")
#: A unit test of the captured Go report that failed, as the fix guard names what a fix broke.
BROKE_UNIT = "unit: notes_api › notes_api › TestContentTypeAllHandlers/DeleteNote"
#: What its runner said (`captured/gotestsum-junit-failing-http.xml`).
ITS_RUNNER_SAID = 'handlers_test.go:619: Content-Type = ""; want "application/json"'
#: The line the reverted change added.
THE_CHANGE = 'w.Header().Set("Content-Type", "text/plain")'


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", *args], check=True,
                   capture_output=True)


def _a_workspace(root: Path) -> Path:
    """A Go service's workspace committed as the fix finds it, its commit tagged `base` (what the stubbed
    `engineering.before_a_fix` answers)."""
    (root / ".harness").mkdir(parents=True)
    (root / ".harness" / "stack-pack.json").write_text(json.dumps({"pack": "go-http-api", "project": "notes-api"}))
    (root / ".gitignore").write_text(".harness/\nnotes-api/test-results/\n")
    (root / "notes-api").mkdir()
    (root / "notes-api" / "handlers.go").write_text(
        "package main\n\nimport \"net/http\"\n\nfunc deleteNote(w http.ResponseWriter, r *http.Request) {\n"
        "\tw.Header().Set(\"Content-Type\", \"application/json\")\n\tw.WriteHeader(http.StatusNoContent)\n}\n")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "before the fix")
    _git(root, "tag", "base")
    return root


def _a_rewrite_that_breaks_the_test(root: Path):
    """The rewrite as the fix stage gets it: it writes the file, and the unit run after it leaves its report."""
    def rewrite(defect, **kwargs):
        path = root / "notes-api" / "handlers.go"
        path.write_text(path.read_text().replace('"application/json"', '"text/plain"'))
        (root / "notes-api" / "test-results").mkdir(exist_ok=True)
        shutil.copy(CAPTURED / "gotestsum-junit-failing-http.xml", root / "notes-api" / "test-results" / "unit.xml")
        return SpecialistOutput(changed_files=["notes-api/handlers.go"], decisions=["Rewrote notes-api/handlers.go"])
    return rewrite


def _a_rewrite_adding_the_field(root: Path):
    """The measured case's rewrite: it adds the field the finding asks for to the record's table."""
    def rewrite(defect, **kwargs):
        path = root / "tasks-api" / "tasks_api" / "database.py"
        path.write_text(path.read_text().replace("token_hash TEXT PRIMARY KEY,", "token_hash TEXT PRIMARY KEY,\n"
                                                 "                    signin TEXT,"))
        return SpecialistOutput(changed_files=["tasks-api/tasks_api/database.py"])
    return rewrite


def _the_fix_guard(broke: list[str], root: Path):
    """`engineering.after_a_fix` at its edge: what the fix broke is handed to `on_revert` while the fix is in the
    workspace, then the workspace is put back."""
    def measure(root_, base, stage, description, contested="", on_revert=None, repair_forward=None):
        if on_revert is not None:
            on_revert(list(broke))
        _git(root, "reset", "-q", "--hard", "base")
        return list(broke)
    return measure


def _a_round(root: Path, state: dict, test_round: int, broke: list[str], rewrite=None):
    return the_fix_stage.run(root, {**state, "test_round": test_round}, fast=True,
                             rewrite=rewrite or _a_rewrite_that_breaks_the_test(root), measure=_the_fix_guard(broke, root))


def test_a_rewrite_after_a_revert_is_told_the_test_it_broke_its_runner_s_words_and_the_change(tmp_path):
    root = _a_workspace(tmp_path)
    defect = a_defect(WRITES_AT_ONCE, affected_files=["notes-api/handlers.go"])
    _a_round(root, a_state(root, defect), 1, [BROKE_UNIT])

    from app.graph.rewritten_fixes import fix_request

    asked = fix_request(root, "notes-api/handlers.go", defect, "they answered 201 x2, 500 x14", None, None, [], [])

    assert "TestContentTypeAllHandlers/DeleteNote" in asked
    assert ITS_RUNNER_SAID in asked, "what the broken test's runner said"
    assert f"+\t{THE_CHANGE}" in asked, "the line of the change that was put back"
    assert "Keep each of those tests passing" in asked


def test_a_broken_acceptance_test_is_told_with_what_the_suite_said_of_it(tmp_path):
    root = _a_workspace(tmp_path)
    shutil.copy(CAPTURED / "acceptance-result-a-foundation-sprint-fastapi.json",
                root / ".harness" / "acceptance-result.json")
    defect = a_defect(WRITES_AT_ONCE, affected_files=["notes-api/handlers.go"])
    _a_round(root, a_state(root, defect), 1, ["acceptance: auth.spec.js › [AC-1] registration creates a new user"])

    from app.graph.rewritten_fixes import fix_request

    asked = fix_request(root, "notes-api/handlers.go", defect, "they answered 201 x2, 500 x14", None, None, [], [])

    assert "[AC-1] registration creates a new user" in asked
    assert re.search(r"Expected: 201\s+Received: 500", asked), "what the suite said of it"


def test_a_defect_whose_rewrites_broke_the_same_test_twice_goes_to_the_tool_using_fixer_with_both_failures(tmp_path):
    root = _a_workspace(tmp_path)
    state = a_state(root, a_defect(WRITES_AT_ONCE, affected_files=["notes-api/handlers.go"]))
    first, _ = _a_round(root, state, 1, [BROKE_UNIT])
    second, _ = _a_round(root, {**state, "remediation": first["remediation"]}, 2, [BROKE_UNIT])

    _, seen = _a_round(root, {**state, "remediation": second["remediation"]}, 3, [BROKE_UNIT])

    assert "rewrite" not in seen.events, "not rewritten a third time"
    assert "agent loop" in seen.events
    asked = seen.requests[-1]
    assert "defect_fix_1_0" in asked and "defect_fix_2_0" in asked, "both failures in front of it"
    assert ITS_RUNNER_SAID in asked


def test_two_rewrites_that_broke_different_tests_do_not_stop_the_third(tmp_path):
    root = _a_workspace(tmp_path)
    state = a_state(root, a_defect(WRITES_AT_ONCE, affected_files=["notes-api/handlers.go"]))
    first, _ = _a_round(root, state, 1, [BROKE_UNIT])
    second, _ = _a_round(root, {**state, "remediation": first["remediation"]}, 2, ["unit: notes_api › notes_api › TestContentTypeAllHandlers"])

    _, seen = _a_round(root, {**state, "remediation": second["remediation"]}, 3, [BROKE_UNIT])

    assert "rewrite" in seen.events


def _the_tasks_api_workspace(root: Path) -> Path:
    shutil.copytree(CAPTURED / "projects" / "python-tasks-api", root, dirs_exist_ok=True)
    (root / "docs").mkdir()
    shutil.copy(CAPTURED / "technical-specification-a-token-generated-on-signin.md",
                root / "docs" / "technical_specification.md")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "before the fix")
    _git(root, "tag", "base")
    return root


def test_a_schema_finding_whose_fix_broke_a_passing_test_is_set_aside_as_doubtful_and_not_raised_again(tmp_path):
    from app.acceptance import check_findings
    from app.graph import engineering

    root = _the_tasks_api_workspace(tmp_path)
    gate = {"repository": SimpleNamespace(root_path=str(root))}
    raised = engineering.schema_differences(gate, str(root))
    assert [d.description for d in raised] == [
        "Schema conformance: Token lacks field(s) signin that the specification's domain model gives it"]
    finding = a_defect(raised[0].description, source="schema conformance", owner="database",
                       actual_behavior=raised[0].actual_behavior, affected_files=["tasks-api/tasks_api/database.py"])

    update, _ = _a_round(root, a_state(root, finding), 2,
                         ["unit: pytest › tests.test_database › test_init_db_creates_tables"],
                         rewrite=_a_rewrite_adding_the_field(root))

    after = update["remediation"].defects[0]
    assert after.status == "accepted_risk"
    assert "test_init_db_creates_tables" in after.accepted_risk_reason
    assert any(row["check"] == "schema conformance, contradicted by a passing test"
               for row in check_findings.read(root))
    assert engineering.schema_differences(gate, str(root)) == [], "not raised again"


def test_what_a_fixer_is_told_after_a_revert_holds_no_product_word(tmp_path):
    from app.graph import what_a_revert_broke

    root = _a_workspace(tmp_path)
    defect = a_defect(WRITES_AT_ONCE, affected_files=["notes-api/handlers.go"])
    state = a_state(root, defect)
    first, _ = _a_round(root, state, 1, [BROKE_UNIT])
    _a_round(root, {**state, "remediation": first["remediation"]}, 2, [BROKE_UNIT])

    said = [what_a_revert_broke.told(root, defect), what_a_revert_broke.repeated(root, defect),
            what_a_revert_broke.DOUBTFUL]

    assert said[0] and said[1]
    assert not [text for text in said if BANNED.search(text.replace(WRITES_AT_ONCE, ""))]


def test_the_effects_report_counts_rewrites_told_and_repeats_stopped():
    from app.graph import what_a_revert_broke
    from app.graph.rewritten_fixes import WHOLE_FILE_SYSTEM

    records = [
        {"kind": "model_request", "messages": [{"content": WHOLE_FILE_SYSTEM},
                                               {"content": what_a_revert_broke.HEADING + "\n- ..."}]},
        {"kind": "defect", "event": "rewrite skipped",
         "detail": what_a_revert_broke.STOPPED + ": its rewrites `a` and `b` were each reverted"},
    ]

    lines = what_a_revert_broke.effects_lines(records)

    assert lines[0].split()[0] == "1" and "told what broke" in lines[0]
    assert lines[1].split()[0] == "1" and "repeats stopped" in lines[1]
