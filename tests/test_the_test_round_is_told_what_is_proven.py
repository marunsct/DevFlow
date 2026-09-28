"""The stage whose job is finding defects must be told the ones already proven.

`summarise_integration` ran in exactly one place - as evidence for the milestone
reviewer. So a defect the cross-file checks can prove by reading two files could
only be raised after the test rounds had finished and a green suite had already
been reported, and fixing it then costs a whole milestone revision.

Measured on one run, which failed its first sprint in eight minutes. Its
plan delegated "Create style.css with basic responsive CSS rules", `index.html`
linked that file, and no tool call in the entire run ever touched it - checked
against the transcript, zero writes to that path. `_broken_local_references`
decides that by reading the two files. The suite was green, the test rounds
reported nothing, and the milestone reviewer raised it as blocking three times
until the run hit `MAX_MILESTONE_REVISIONS` and failed:

    [blocking] accessibility: index.html references style.css which does not
    exist in the workspace. The page is unstyled.

The test round is where a defect is supposed to be found, and it was the one
stage not told. A problem handed over here enters the remediation cycle that
already exists for defects, inside the sprint, instead of costing a revision of
it.

Only the tier `summarise_integration` itself calls breaking. The judgement ones -
a dead CSS rule, an export no test mentions - are not defects, and putting them
here would turn this stage's report into a style review.
"""

from __future__ import annotations

import pytest

from app.agents.specialists import build_test_run_request

A_PAGE_MISSING_ITS_STYLESHEET = """<!doctype html>
<html>
<head><link rel="stylesheet" href="style.css"></head>
<body><ul id="tasks"></ul><script type="module" src="./app.js"></script></body>
</html>
"""


@pytest.fixture
def a_workspace(tmp_path):
    """One run's shape: a page linking a stylesheet nobody wrote."""
    project = tmp_path / "simple-to-do-list-app"
    project.mkdir()
    (project / "index.html").write_text(A_PAGE_MISSING_ITS_STYLESHEET)
    (project / "app.js").write_text(
        "export const add = (task) => { document.getElementById('tasks').textContent = task; };\n"
    )
    return tmp_path


def _brief(root, stack="javascript"):
    request = build_test_run_request("Implement CRUD", ["index.html"], str(root), stack)
    return request["messages"][0]["content"]


class TestHandingOverWhatIsProven:
    def test_the_defect_that_cost_run_e980310b_its_sprint(self, a_workspace):
        brief = _brief(a_workspace)

        assert "style.css" in brief

    def test_it_is_marked_as_decided_rather_than_suggested(self, a_workspace):
        """This stage may argue with a suite. It may not argue with the filesystem."""
        brief = _brief(a_workspace)

        assert "Already proven by reading the files" in brief
        assert "not by judgement" in brief

    def test_it_asks_for_them_as_defects(self, a_workspace):
        """Prose in this stage's report is not something the controller can route."""
        brief = _brief(a_workspace)

        assert "Report every one as a defect" in brief

    def test_it_says_a_passing_suite_does_not_clear_them(self, a_workspace):
        """The suite was green while the page was unstyled. That is the whole point."""
        brief = _brief(a_workspace)

        assert "passing suite" in brief

    def test_the_section_comes_before_the_instruction_to_run_tests(self, a_workspace):
        """Read as context for the round, not as an afterthought to it."""
        brief = _brief(a_workspace)

        assert brief.index("Already proven") < brief.index("Run the unit, integration")


class TestSayingNothingWhenThereIsNothing:
    def test_a_sound_workspace_adds_no_section(self, a_workspace):
        """A round with nothing proven against it must read as it always did."""
        (a_workspace / "simple-to-do-list-app" / "style.css").write_text(
            "#tasks { padding: 1rem; }\n"
        )

        assert "Already proven by reading the files" not in _brief(a_workspace)

    def test_an_empty_workspace_adds_no_section(self, tmp_path):
        assert "Already proven" not in _brief(tmp_path)

    def test_a_workspace_that_cannot_be_read_still_builds_a_brief(self, tmp_path):
        """A brief is better without this than absent: the round must still run."""
        brief = _brief(tmp_path / "does-not-exist")

        assert "Run the unit, integration" in brief

    def test_the_judgement_tier_is_left_out(self, a_workspace):
        """A dead rule is not a defect, and this stage's report is not a style review."""
        project = a_workspace / "simple-to-do-list-app"
        (project / "style.css").write_text("#tasks { padding: 1rem; }\n")
        (project / "orphan.js").write_text("export const unused = 1;\n")

        brief = _brief(a_workspace)

        assert "is never loaded by a page" not in brief
        assert "no test mentions" not in brief


class TestTheRestOfTheBriefIsIntact:
    def test_the_stage_is_still_told_not_to_install_anything(self, a_workspace):
        """The constraint this stage breaks most often, and it must survive."""
        brief = _brief(a_workspace)

        assert "Do not install a test framework" in brief

    def test_the_milestone_and_changed_files_are_still_there(self, a_workspace):
        brief = _brief(a_workspace)

        assert "Milestone under test" in brief
        assert "Files changed in this milestone" in brief

    def test_the_defect_fields_are_still_demanded(self, a_workspace):
        brief = _brief(a_workspace)

        assert "`defects`" in brief
