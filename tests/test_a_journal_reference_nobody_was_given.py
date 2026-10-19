"""A tool description must not hand the model an identifier it cannot use.

`read_command_output` reads back output too large for the conversation, keyed by
a reference the truncation pointer supplies. The reference ends in eight random
characters, so it cannot be written from the command that produced it - and the
`Args:` description carried a complete, copyable example of one:

    reference: the name from the truncation pointer, e.g.
        `1717171717-backend-specialist-pytest-stdout-a1b2c3d4.log`.

Across the 24 current-generation runs that exact string was the single
most-passed value: 9 of 28 failed calls, from stages that had never been shown a
pointer. A worked example of an identifier that cannot be constructed is an
invitation to construct one.

An earlier fix made the refusal list what exists, which turned a dead end into
one more call. It left the cause in the description above it.

A second 6 of the 28 passed a workspace path - `todo-app/app.js`,
`todo-app/index.html` - which is this tool being mistaken for `read_file`. Those
got an explanation of the journal at a stage that was not asking about the
journal.
"""

from __future__ import annotations

import pytest

from app.tools.agent_toolkit import _and_a_path_is_read_with_read_file


class TestTheDescriptionNoLongerSuppliesOne:
    def _description(self):
        from app.tools.agent_toolkit import build_journal_read_tool

        import inspect

        return inspect.getsource(build_journal_read_tool)

    def test_the_fabricated_example_is_gone(self):
        """The single most-passed value across the current generation of runs."""
        assert "1717171717-backend-specialist-pytest-stdout-a1b2c3d4.log" not in (
            self._description().split("# What the refusal used to be")[0]
        )

    def test_it_says_the_reference_cannot_be_written(self):
        assert "no way to write one" in self._description()

    def test_it_says_not_to_construct_one(self):
        assert "Do not construct" in self._description()

    def test_it_says_this_is_not_how_to_read_a_file(self):
        """6 of 28 calls passed a workspace path."""
        assert "not a way to read a file" in self._description()
        assert "`read_file`" in self._description()


class TestRedirectingAPath:
    @pytest.mark.parametrize(
        "reference",
        [
            "todo-app/app.js",
            "todo-app/index.html",
            "todo-app/app.test.mjs",
            "simple-to-do-list-app/playwright.config.ts",
            "170a88bbee3c48e6b5ee1315580e3ed7.md",
        ],
    )
    def test_a_path_that_is_there_is_sent_to_read_file(self, tmp_path, reference):
        """With the file present, the note names where it is and which tool reads it."""
        import os

        target = tmp_path / reference
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x")

        note = _and_a_path_is_read_with_read_file(reference, str(tmp_path))

        assert "`read_file`" in note
        assert reference in note
        assert os.path.basename(reference) in note

    @pytest.mark.parametrize(
        "reference",
        [
            "todo-app/app.js",
            "case/error-context.md",
        ],
    )
    def test_a_path_that_is_not_there_is_not_sent_anywhere(self, tmp_path, reference):
        """Measured on one run: told to use `read_file` 14 times for a
        Playwright artefact Playwright had already deleted. Suggesting a tool
        that cannot work is one more round trip."""
        note = _and_a_path_is_read_with_read_file(reference, str(tmp_path))

        assert "no file of that name anywhere in the workspace" in note
        assert "`read_file`" not in note

    def test_with_no_workspace_it_still_names_the_tool(self):
        """A caller without a root cannot look, and the old advice is the best left.

        It must not say "there is no file of that name anywhere in the workspace":
        that is a claim about a workspace it never saw.
        """
        note = _and_a_path_is_read_with_read_file("todo-app/app.js")

        assert "looks like a path" in note
        assert "`read_file`" in note
        assert "no file of that name anywhere" not in note

    def test_a_real_reference_is_left_alone(self):
        """The eight random characters are what says a reference is one."""
        assert _and_a_path_is_read_with_read_file(
            "1790418892-run-a000000f-testing_specialist-npm-stdout-43b36066.log"
        ) == ""

    @pytest.mark.parametrize(
        "reference",
        ["npm-test-output", "", "output", "stdout"],
    )
    def test_a_bare_name_gets_no_path_advice(self, reference):
        """It is not a path either, and telling it to use `read_file` would mislead."""
        assert _and_a_path_is_read_with_read_file(reference) == ""

    def test_the_invented_example_is_not_called_a_path(self):
        """It has the journal's shape, so the journal explanation is the right one."""
        assert _and_a_path_is_read_with_read_file(
            "1717171717-backend-specialist-pytest-stdout-a1b2c3d4.log"
        ) == ""

    def test_it_never_raises(self):
        assert _and_a_path_is_read_with_read_file(None) == ""  # type: ignore[arg-type]


class TestTheRefusalsCarryIt:
    def test_an_empty_journal_redirects_a_path(self, tmp_path, monkeypatch):
        from app.tools import agent_toolkit, journal

        (tmp_path / "todo-app").mkdir()
        (tmp_path / "todo-app" / "app.js").write_text("x")
        monkeypatch.setattr(journal, "read_entry", lambda name: None)
        monkeypatch.setattr(journal, "list_entries", lambda scope="", limit=10: [])
        tool = agent_toolkit.build_journal_read_tool(str(tmp_path))

        result = tool.invoke({"reference": "todo-app/app.js"})

        assert "`read_file`" in result["error"]
        assert "todo-app/app.js" in result["error"]

    def test_an_empty_journal_says_when_the_file_is_gone_too(self, tmp_path, monkeypatch):
        from app.tools import agent_toolkit, journal

        monkeypatch.setattr(journal, "read_entry", lambda name: None)
        monkeypatch.setattr(journal, "list_entries", lambda scope="", limit=10: [])
        tool = agent_toolkit.build_journal_read_tool(str(tmp_path))

        result = tool.invoke({"reference": "case/error-context.md"})

        assert "no file of that name anywhere in the workspace" in result["error"]

    def test_a_populated_journal_redirects_a_path(self, tmp_path, monkeypatch):
        from app.tools import agent_toolkit, journal

        monkeypatch.setattr(journal, "read_entry", lambda name: None)
        monkeypatch.setattr(
            journal,
            "list_entries",
            lambda scope="", limit=10: ["1790418892-run-x-npm-stdout-43b36066.log"],
        )
        tool = agent_toolkit.build_journal_read_tool(str(tmp_path))

        (tmp_path / "todo-app").mkdir()
        (tmp_path / "todo-app" / "app.js").write_text("x")

        result = tool.invoke({"reference": "todo-app/app.js"})

        assert "`read_file`" in result["error"]
        # A file of the workspace was meant: the saved outputs are not listed
        # in front of the sentence that helps (they were, until a fixer missed it).
        assert "1790418892-run-x-npm-stdout-43b36066.log" not in result["error"]

    def test_a_path_found_nowhere_still_lists_what_was_saved(self, tmp_path, monkeypatch):
        from app.tools import agent_toolkit, journal

        monkeypatch.setattr(journal, "read_entry", lambda name: None)
        monkeypatch.setattr(journal, "list_entries", lambda scope="", limit=10: ["1790418892-run-x-npm-stdout-43b36066.log"])
        tool = agent_toolkit.build_journal_read_tool(str(tmp_path))

        result = tool.invoke({"reference": "todo-app/missing.js"})

        assert "1790418892-run-x-npm-stdout-43b36066.log" in result["error"]

    def test_a_search_of_a_workspace_file_leads_with_grep(self, tmp_path, monkeypatch):
        from app.tools import agent_toolkit, journal

        monkeypatch.setattr(journal, "read_entry", lambda name: None)
        monkeypatch.setattr(journal, "list_entries", lambda scope="", limit=10: [f"17904188{i:02d}-run-x-npm-stdout-43b36066.log" for i in range(30)])
        tool = agent_toolkit.build_journal_read_tool(str(tmp_path))
        (tmp_path / "svc").mkdir()
        (tmp_path / "svc" / "service.py").write_text("def list_items(): ...\n")

        result = tool.invoke({"reference": "svc/service.py", "search": "list_items"})

        assert result["error"].startswith("No journalled output named 'svc/service.py'.")
        assert 'call `grep` with pattern "list_items"' in result["error"]
        assert len(result["error"]) < 400

    def test_a_real_reference_still_reads(self, tmp_path, monkeypatch):
        """The tool must keep doing its job."""
        from app.tools import agent_toolkit, journal

        monkeypatch.setattr(journal, "read_entry", lambda name: "the full output\n")
        tool = agent_toolkit.build_journal_read_tool(str(tmp_path))

        assert "the full output" in tool.invoke(
            {"reference": "1790418892-run-x-npm-stdout-43b36066.log"}
        )

    def test_a_wrong_reference_is_still_a_recoverable_result(self, tmp_path, monkeypatch):
        """Not an exception: a wrong guess must not crash the run."""
        from app.tools import agent_toolkit, journal

        monkeypatch.setattr(journal, "read_entry", lambda name: None)
        monkeypatch.setattr(journal, "list_entries", lambda scope="", limit=10: [])
        tool = agent_toolkit.build_journal_read_tool(str(tmp_path))

        assert "error" in tool.invoke({"reference": "whatever"})


class TestAReferenceThatIsAPathWithSomethingAfterIt:
    """The commonest failing reference is the harness's own listing, copied.

    Splitting every `read_command_output` error across the stored runs by kind:

        56  reference not found
        14  refused as a repeat
         5  the search term was not in the file

    and of those 56, the dominant shapes are the harness's own workspace listing
    copied verbatim - `task-manager/app.js (188 lines)`, 18 occurrences - and a
    description like `app.spec.js lines 315-340`. `os.path.basename` reads those
    as `(188` and `315-340`, so the file was never found and the note said no such
    file existed while `task-manager/app.js` sat right there.

    The harness prints `path (N lines)` itself, in the workspace listing it injects
    with "This is what is there - you do not need to list the directories to find
    out". An agent copying that string back is using the format it was given.
    """

    @pytest.fixture
    def a_project(self, tmp_path):
        (tmp_path / "task-manager" / "e2e").mkdir(parents=True)
        (tmp_path / "task-manager" / "app.js").write_text("x")
        (tmp_path / "task-manager" / "e2e" / "app.spec.js").write_text("x")
        return tmp_path

    @pytest.mark.parametrize(
        "reference,expected",
        [
            ("task-manager/app.js (188 lines)", "task-manager/app.js"),
            ("task-manager/app.js (299 lines)", "task-manager/app.js"),
            ("app.spec.js lines 315-340", "task-manager/e2e/app.spec.js"),
            ("task-manager/app.js", "task-manager/app.js"),
            ("see app.js for the handler", "task-manager/app.js"),
        ],
    )
    def test_the_real_path_is_named(self, a_project, reference, expected):
        note = _and_a_path_is_read_with_read_file(reference, str(a_project))

        assert expected in note, note
        assert "`read_file`" in note

    def test_a_filename_that_is_not_there_still_says_so(self, a_project):
        note = _and_a_path_is_read_with_read_file(
            "case/error-context.md", str(a_project)
        )

        assert "no file of that name anywhere in the workspace" in note

    def test_a_reference_naming_no_file_stays_silent(self, a_project):
        """`npm-test-output` is neither a path nor a reference, and guessing is worse."""
        assert _and_a_path_is_read_with_read_file("npm-test-output", str(a_project)) == ""

    def test_a_real_journal_reference_is_still_left_alone(self, a_project):
        assert _and_a_path_is_read_with_read_file(
            "1790497387-run-a0000003-testing_specialist-npx-stdout-328ba6e2.log",
            str(a_project),
        ) == ""

    def test_the_filenames_are_pulled_out_of_the_string(self):
        from app.tools.agent_toolkit import _the_files_a_reference_names

        assert _the_files_a_reference_names("task-manager/app.js (188 lines)") == ["app.js"]
        assert _the_files_a_reference_names("app.spec.js lines 315-340") == ["app.spec.js"]
        assert _the_files_a_reference_names("nothing here") == []


class TestASearchOfAWorkspaceFile:
    """One run's `specialist_backend_0` passed a file path as the reference with
    `search: "toggle-btn"`, was told to use `read_file`, and sent the identical
    call again: it was searching, not reading."""

    def test_the_note_names_the_grep_call_it_wanted(self, tmp_path):
        target = tmp_path / "task-manager/tests/e2e/todo.spec.ts"
        target.parent.mkdir(parents=True)
        target.write_text("x")

        note = _and_a_path_is_read_with_read_file(
            "task-manager/tests/e2e/todo.spec.ts", str(tmp_path), "toggle-btn"
        )

        assert "`grep`" in note
        assert '"toggle-btn"' in note
        assert "task-manager/tests/e2e/todo.spec.ts" in note
        assert "`read_file`" not in note

    def test_without_a_search_it_is_still_a_read(self, tmp_path):
        target = tmp_path / "app.js"
        target.write_text("x")

        assert "`read_file`" in _and_a_path_is_read_with_read_file("app.js", str(tmp_path), "")

    def test_a_missing_file_is_still_missing(self, tmp_path):
        note = _and_a_path_is_read_with_read_file("app.js", str(tmp_path), "needle")

        assert "no file of that name" in note
        assert "`grep`" not in note
