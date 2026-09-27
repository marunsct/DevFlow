"""The check for a document's bad instruction could not read product documents.

`_documented_commands_that_cannot_run` reports documentation telling a reader to
run a file the project does not have. It scanned `root/docs` only - which is the
*workflow's* directory, holding the nine documents it renders from structured
responses, and the one directory every agent is refused a write to. The writing
rules tell them documentation that ships with the product "goes inside the
project folder beside the code it describes".

So a product README was the one place this could never look, and a README is what
its own evidence is about: run-3da8dd91 "shipped the same shape - a README citing
`npm run build-static`".

Found by sweeping all 37 checks over the 77 stored workspaces: this was the only
check with no test that also fired on nothing. Those workspaces hold
`workspace-run-3faaa89b/README.md`, `.../task-manager/README.md` and
`.../simple-to-do-list-app/README.md`, none of which it read.

Honest about what this buys: none of the 77 stored workspaces documents a command
naming a missing file - their READMEs cite `node --test` and `npx serve .`, which
are fine - so the sweep shows 0 findings before and 0 after. What changed is that
the check can now see the artefact it was written for. The fault is real and
recorded twice in its own docstring; the workspaces holding those two runs are no
longer retained.
"""

from __future__ import annotations

import pytest

from app.analysis.integration_checks import (
    _documented_commands_that_cannot_run,
    _source_files,
)

#: run-cbb1a5fc's `docs/deployment.md`, which four milestone reviews read.
A_DOCUMENT_NAMING_A_MISSING_FILE = (
    "## Running\n\nRun with `node server.js`, then open http://localhost:3000\n"
)


@pytest.fixture
def a_project(tmp_path):
    """A project whose files are the ones run-cbb1a5fc actually had."""

    def _build(document_at: str):
        project = tmp_path / "todo-app"
        project.mkdir(parents=True, exist_ok=True)
        (project / "app.js").write_text("export const add = (t) => t;\n")
        (project / "app.test.mjs").write_text("test('x', () => {});\n")
        (project / "index.html").write_text("<html></html>")
        (project / "package.json").write_text('{"type": "module"}')
        (project / "style.css").write_text("body { margin: 0; }\n")
        target = (tmp_path / document_at).resolve()
        target.mkdir(parents=True, exist_ok=True)
        (target / "README.md").write_text(A_DOCUMENT_NAMING_A_MISSING_FILE)
        return tmp_path

    return _build


def _findings(root):
    return _documented_commands_that_cannot_run(
        _source_files(root), root, root / "docs"
    )


class TestWhereProductDocumentationActuallyLands:
    @pytest.mark.parametrize(
        "where",
        [
            "todo-app",          # beside the code, which the writing rules require
            ".",                 # the workspace root
            "todo-app/docs",     # the project's own docs folder
            "docs",              # the workflow's, which was the only one read
        ],
    )
    def test_the_bad_instruction_is_found(self, a_project, where):
        root = a_project(where)

        problems = _findings(root)

        assert len(problems) == 1, problems
        assert "server.js" in problems[0]

    def test_the_finding_names_the_document(self, a_project):
        """"docs/README.md" for a file in the project folder named the wrong one."""
        root = a_project("todo-app")

        assert "todo-app/README.md" in _findings(root)[0]


class TestNotReportingWhatIsFine:
    def test_a_command_naming_a_file_that_exists_is_silent(self, a_project, tmp_path):
        root = a_project("todo-app")
        (tmp_path / "todo-app" / "README.md").write_text(
            "Run with `node app.js` to start.\n"
        )

        assert _findings(root) == []

    def test_the_commands_the_stored_readmes_really_use_are_silent(
        self, a_project, tmp_path
    ):
        """`node --test` and `npx serve .` - what the 77 workspaces document."""
        root = a_project("todo-app")
        (tmp_path / "todo-app" / "README.md").write_text(
            "Run the suite with `node --test`. Serve it with `npx serve .`.\n"
        )

        assert _findings(root) == []

    def test_prose_about_a_server_is_silent(self, a_project, tmp_path):
        """Only a bare filename in a code span, as the docstring says."""
        root = a_project("todo-app")
        (tmp_path / "todo-app" / "README.md").write_text(
            "In production you would put this behind a server.js of some kind.\n"
        )

        assert _findings(root) == []

    def test_a_test_runner_s_own_markdown_is_skipped(self, a_project, tmp_path):
        """Playwright writes `test-results/<case>/error-context.md`, which records
        a run rather than telling anybody to do anything."""
        root = a_project("todo-app/test-results/some-case")

        assert _findings(root) == []

    @pytest.mark.parametrize("skipped", ["playwright-report", "coverage", "htmlcov"])
    def test_other_runner_output_is_skipped(self, a_project, skipped):
        root = a_project(f"todo-app/{skipped}")

        assert _findings(root) == []

    def test_a_dependency_s_readme_is_skipped(self, a_project):
        root = a_project("todo-app/node_modules/thing")

        assert _findings(root) == []

    def test_a_workspace_with_no_documents_is_silent(self, tmp_path):
        (tmp_path / "app.js").write_text("export const a = 1;\n")

        assert _findings(tmp_path) == []

    def test_an_unreadable_workspace_does_not_raise(self, tmp_path):
        assert _documented_commands_that_cannot_run([], tmp_path / "gone", tmp_path) == []


class TestTheTierIsUnchanged:
    """Widening what the check reads is a separate question from how it grades.

    It grades untidy, and that is defensible: the BREAKS bucket's heading is "a
    feature DOES NOT WORK ... the code path is simply never reached", and a
    product with a wrong README works perfectly - it is the instruction that is
    broken, not a code path. Pinned rather than changed, so that if the tier is
    ever revisited it is a decision somebody made rather than a side effect of
    this fix.
    """

    def test_it_still_grades_as_it_did(self, a_project):
        from app.analysis.integration_checks import _severity_of

        root = a_project("todo-app")

        assert _severity_of(_findings(root)[0]) == "untidy"

    def test_it_is_not_silently_promoted_by_a_declared_floor(self):
        from app.analysis.integration_checks import _CHECKS, _floor_of

        for entry in _CHECKS:
            if "commands the documents tell a reader to run" in entry[0]:
                assert _floor_of(entry) == ""
