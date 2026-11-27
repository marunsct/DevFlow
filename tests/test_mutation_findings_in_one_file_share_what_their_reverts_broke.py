"""The fixer of a mutation finding reads what reverted fixes of other findings in the same file broke (LF.1621); once
two of them were reverted for the same break in a sprint, the next finding there is a completion gap, not a fix stage
(LF.1622).

Measured on a C# run: three findings in one endpoints file (`==` made `!=` on line 39, `||` made `&&` on lines 39 and
54) had a fix stage each, about fifteen minutes apiece. Each wrote a test subclassing a class whose methods cannot be
overridden, the test project stopped compiling, and each was reverted for it. What a revert broke was kept by the
finding's wording, so the fixer of the `==` finding never saw what the `||` fixes had hit, and nothing stopped the
third stage after the same break came back twice.
"""
from __future__ import annotations

from app.graph import what_a_revert_broke

import the_fix_stage
from the_fix_stage import a_defect, a_state

FILE = "notes-api/src/App/Endpoints/NoteEndpoints.cs"
COMPILER = ("it wrote code the compiler rejects: `notes-api/tests/UnitTests/NoteEndpointsTests.cs` line {line}: "
            "'NoteEndpointsTests.FailingDatabaseService.CreateNoteAsync(string, string, string?)': cannot override "
            "inherited member 'DatabaseService.CreateNoteAsync(string, string, string?)' because it is not marked "
            "virtual, abstract, or override")
LOST = "unit: UnitTests.dll › UnitTests.NoteEndpointsTests › NoteEndpointsTests.Health_Returns200"


def a_finding(line: int, original: str, replacement: str, file: str = FILE):
    return a_defect(
        f"No test notices a deliberate change to `{file}` line {line}, column 63: `{original}` made `{replacement}`. "
        "The unit tests and the acceptance suite all still pass with it, so no test holds the product to that "
        "behaviour.", source="mutation", owner="testing", affected_files=[file])


def _a_fix_stage_reverted_for(root, finding, line):
    """One fix stage of `finding`, measured as breaking the build at `line` of the test file, and reverted."""
    def measure(*args, on_revert=None, **kwargs):
        broke = [COMPILER.format(line=line), LOST]
        if on_revert is not None:
            on_revert(broke)
        return broke

    return the_fix_stage.run(root, a_state(root, finding), measure=measure)


def test_the_fixer_of_another_finding_in_the_same_file_reads_what_a_revert_broke(tmp_path):
    _a_fix_stage_reverted_for(tmp_path, a_finding(39, "||", "&&"), 455)

    told = what_a_revert_broke.told(tmp_path, a_finding(39, "==", "!="))

    assert "cannot override inherited member" in told
    assert what_a_revert_broke.told(tmp_path, a_finding(12, "==", "!=", file="notes-api/src/App/Program.cs")) == ""


def test_after_the_same_break_twice_the_next_finding_in_the_file_is_a_completion_gap(tmp_path):
    _a_fix_stage_reverted_for(tmp_path, a_finding(39, "||", "&&"), 455)
    _a_fix_stage_reverted_for(tmp_path, a_finding(54, "||", "&&"), 470)

    update, seen = _a_fix_stage_reverted_for(tmp_path, a_finding(39, "==", "!="), 490)

    assert "agent loop" not in seen.events and "measured" not in seen.events, "no fix stage was spent on it"
    closed = update["remediation"].defects[0]
    assert closed.status == "accepted_risk"
    assert closed.accepted_risk_reason.startswith("No unit test was made to notice it")


def test_a_finding_in_another_file_is_still_fixed(tmp_path):
    _a_fix_stage_reverted_for(tmp_path, a_finding(39, "||", "&&"), 455)
    _a_fix_stage_reverted_for(tmp_path, a_finding(54, "||", "&&"), 470)

    _, seen = _a_fix_stage_reverted_for(tmp_path, a_finding(12, "==", "!=", file="notes-api/src/App/Program.cs"), 490)

    assert "agent loop" in seen.events


def test_two_reverts_for_different_breaks_stop_nothing(tmp_path):
    _a_fix_stage_reverted_for(tmp_path, a_finding(39, "||", "&&"), 455)

    def measure(*args, on_revert=None, **kwargs):
        broke = ["unit: UnitTests.dll › UnitTests.NoteEndpointsTests › NoteEndpointsTests.Delete_Returns204"]
        on_revert(broke)
        return broke

    the_fix_stage.run(tmp_path, a_state(tmp_path, a_finding(54, "||", "&&")), measure=measure)

    _, seen = _a_fix_stage_reverted_for(tmp_path, a_finding(39, "==", "!="), 490)

    assert "agent loop" in seen.events
