"""Tests for the safe repository inspection tool layer.

The core idea is simple: tools may inspect a repository, but only inside a
trusted boundary. These tests make that contract explicit by proving that reads,
searches, and writes stay inside the repository or approved artifact directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.repository import (
    PROJECT_MARKER,
    RepositoryToolError,
    pinned_project_directory,
    build_repository_context,
    list_repository_files,
    read_dependency_metadata,
    read_text_file,
    run_approved_validation,
    search_text,
    edit_approved_artifact,
    read_text_lines,
    write_approved_artifact,
)


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    # Build a tiny, controlled repository so the tests exercise the tool behavior
    # without relying on the real workspace structure.
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "docs/generated").mkdir()
    (root / ".git").mkdir()
    (root / "node_modules").mkdir()

    (root / "pyproject.toml").write_text(
        "[project]\nname = \"demo-app\"\nversion = \"0.1.0\"\n",
        encoding="utf-8",
    )
    (root / "src" / "main.py").write_text("print('hello')\n", encoding="utf-8")
    (root / "docs" / "brief.md").write_text("# Product\n\nKeep this note.\n", encoding="utf-8")
    (root / "docs" / "generated" / "artifact.md").write_text("draft\n", encoding="utf-8")
    return root


def test_list_repository_files_skips_ignored_directories(repo_root: Path) -> None:
    files = list_repository_files(repo_root)

    assert "src/main.py" in files
    assert "docs/brief.md" in files
    assert ".git" not in "\n".join(files)
    assert "node_modules" not in "\n".join(files)


def test_read_text_file_requires_repo_boundary(repo_root: Path) -> None:
    result = read_text_file(repo_root, "docs/brief.md")

    assert "Keep this note" in result

    with pytest.raises(RepositoryToolError):
        read_text_file(repo_root, "../outside.txt")


def test_search_text_finds_matching_content(repo_root: Path) -> None:
    matches = search_text(repo_root, "Keep this note")

    assert matches
    assert "docs/brief.md" in matches[0]["path"]


def test_read_dependency_metadata_reads_project_file(repo_root: Path) -> None:
    metadata = read_dependency_metadata(repo_root)

    assert metadata["project"]["name"] == "demo-app"


# ---------------------------------------------------------------------------
# Changing part of a file, instead of replacing all of it
# ---------------------------------------------------------------------------
#
# A whole-file overwrite was the only way an agent could change anything. To
# correct one contradictory sentence in a 71KB specification it had to reproduce
# the entire document in a single tool call, and rather than do that it wrote a
# shorter second file called `technical_specification_v2.md`. The reviewer then
# read both and reported the differences between them as contradictions in the
# design, and the run stopped unresolved.


def test_one_passage_can_be_changed_without_touching_the_rest(repo_root: Path) -> None:
    original = "# Spec\n\n## Deletion\nDrafts are soft-deleted.\n\n## Storage\nS3 with encryption.\n"
    write_approved_artifact(repo_root, "docs/spec.md", original)

    result = edit_approved_artifact(
        repo_root, "docs/spec.md", "Drafts are soft-deleted.", "Drafts are hard-deleted."
    )

    assert result["status"] == "edited"
    updated = (repo_root / "docs" / "spec.md").read_text(encoding="utf-8")
    assert "Drafts are hard-deleted." in updated
    # Everything the agent did not name is byte-for-byte intact.
    assert "## Storage\nS3 with encryption.\n" in updated
    assert updated.startswith("# Spec\n")


def test_an_edit_can_delete_a_passage(repo_root: Path) -> None:
    write_approved_artifact(repo_root, "docs/spec.md", "keep this\nremove this\nkeep this too\n")

    edit_approved_artifact(repo_root, "docs/spec.md", "remove this\n", "")

    assert (repo_root / "docs" / "spec.md").read_text(encoding="utf-8") == "keep this\nkeep this too\n"


def test_an_edit_that_matches_nothing_is_refused(repo_root: Path) -> None:
    """Silence here would be the worst outcome: the agent believes it fixed something."""
    write_approved_artifact(repo_root, "docs/spec.md", "Drafts are soft-deleted.\n")

    with pytest.raises(RepositoryToolError, match="Could not find"):
        edit_approved_artifact(repo_root, "docs/spec.md", "Drafts are archived.", "x")

    assert (repo_root / "docs" / "spec.md").read_text(encoding="utf-8") == "Drafts are soft-deleted.\n"


def test_an_ambiguous_edit_is_refused_rather_than_guessing(repo_root: Path) -> None:
    """Replacing the first of several matches corrupts the document silently."""
    write_approved_artifact(repo_root, "docs/spec.md", "status: OPEN\nstatus: OPEN\n")

    with pytest.raises(RepositoryToolError, match="appears 2 times"):
        edit_approved_artifact(repo_root, "docs/spec.md", "status: OPEN", "status: CLOSED")

    assert (repo_root / "docs" / "spec.md").read_text(encoding="utf-8") == "status: OPEN\nstatus: OPEN\n"


def test_editing_a_file_that_does_not_exist_points_at_the_write_tool(repo_root: Path) -> None:
    with pytest.raises(RepositoryToolError, match="write_artifact"):
        edit_approved_artifact(repo_root, "docs/missing.md", "a", "b")


def test_an_edit_cannot_escape_the_repository(repo_root: Path) -> None:
    with pytest.raises(RepositoryToolError):
        edit_approved_artifact(repo_root, "../outside.md", "a", "b")


# ---------------------------------------------------------------------------
# Reading part of a file
# ---------------------------------------------------------------------------


def test_a_slice_of_a_file_can_be_read(repo_root: Path) -> None:
    write_approved_artifact(repo_root, "docs/long.md", "".join(f"line {n}\n" for n in range(1, 21)))

    page = read_text_lines(repo_root, "docs/long.md", start_line=5, line_count=3)

    assert page["content"] == "line 5\nline 6\nline 7"
    assert (page["start_line"], page["end_line"]) == (5, 7)
    assert page["total_lines"] == 20
    # So the agent knows to ask for the next slice rather than assuming it is done.
    assert page["has_more"] is True


def test_the_last_slice_reports_that_nothing_follows(repo_root: Path) -> None:
    write_approved_artifact(repo_root, "docs/long.md", "a\nb\nc\n")

    page = read_text_lines(repo_root, "docs/long.md", start_line=2)

    assert page["content"] == "b\nc"
    assert page["has_more"] is False


def test_reading_past_the_end_says_how_long_the_file_is(repo_root: Path) -> None:
    write_approved_artifact(repo_root, "docs/short.md", "a\nb\n")

    with pytest.raises(RepositoryToolError, match="has 2 lines"):
        read_text_lines(repo_root, "docs/short.md", start_line=99)


@pytest.mark.parametrize(("start", "count"), [(0, None), (-1, None), (1, 0)])
def test_nonsense_slice_bounds_are_refused(repo_root: Path, start: int, count: int | None) -> None:
    write_approved_artifact(repo_root, "docs/short.md", "a\nb\n")

    with pytest.raises(RepositoryToolError):
        read_text_lines(repo_root, "docs/short.md", start_line=start, line_count=count)


def test_a_second_version_of_an_existing_document_is_refused(repo_root: Path) -> None:
    """Forking a document is what stopped a real run.

    The architect wrote `docs/technical_specification_v2.md` while
    `docs/technical_specification.md` already existed. The reviewer then had two
    specifications to read and reported the differences between them as
    contradictions in the design - a blocking finding that existed only because
    the second file did. The run spent its last two revisions on it and stopped
    with it unresolved.
    """
    write_approved_artifact(repo_root, "docs/spec.md", "# Spec\n\nsoft delete\n")

    with pytest.raises(RepositoryToolError, match="already exists"):
        write_approved_artifact(repo_root, "docs/spec_v2.md", "# Spec\n\nhard delete\n")

    assert not (repo_root / "docs" / "spec_v2.md").exists()
    # The original is untouched, so the refusal costs nothing.
    assert (repo_root / "docs" / "spec.md").read_text(encoding="utf-8").endswith("soft delete\n")


@pytest.mark.parametrize(
    "variant",
    ["docs/spec-v2.md", "docs/spec.v3.md", "docs/spec_final.md", "docs/spec copy.md", "docs/spec_REVISED.md"],
)
def test_every_shape_of_second_copy_is_refused(repo_root: Path, variant: str) -> None:
    write_approved_artifact(repo_root, "docs/spec.md", "# Spec\n")

    with pytest.raises(RepositoryToolError, match="already exists"):
        write_approved_artifact(repo_root, variant, "# Spec\n")


def test_a_numbered_series_is_not_mistaken_for_a_second_copy(repo_root: Path) -> None:
    """The guard must not block a document set that is genuinely numbered.

    `adr_1.md` and `adr_2.md` are two decision records, not two copies of one.
    Only an explicit version marker counts, and only when the file it would fork
    actually exists.
    """
    assert write_approved_artifact(repo_root, "docs/adr_1.md", "# ADR 1\n")["status"] == "written"
    assert write_approved_artifact(repo_root, "docs/adr_2.md", "# ADR 2\n")["status"] == "written"

    # And a version-marked name is fine when there is nothing to fork.
    assert write_approved_artifact(repo_root, "docs/plan_v2.md", "# Plan\n")["status"] == "written"


def test_rewriting_the_canonical_document_is_still_allowed(repo_root: Path) -> None:
    """The point is to send revisions back to the original, so that must work."""
    write_approved_artifact(repo_root, "docs/spec.md", "# Spec\n\nfirst\n")

    result = write_approved_artifact(repo_root, "docs/spec.md", "# Spec\n\nrevised\n")

    assert result["status"] == "written"
    assert "revised" in (repo_root / "docs" / "spec.md").read_text(encoding="utf-8")


def test_a_prose_artifact_refuses_a_serialized_structured_response(repo_root: Path) -> None:
    """Saving the answer schema as the document destroys the document.

    Observed live: the architect wrote a good Markdown specification, then
    overwrote it twice with a JSON dump of its own structured response. The
    run's headline artifact ended up unreadable. Refusing turns a silent
    corruption into a correction the model can act on.
    """
    good = "# Technical Specification\n\nThe Hub stores decision records.\n"
    assert write_approved_artifact(repo_root, "spec.md", good)["status"] == "written"

    with pytest.raises(RepositoryToolError, match="Markdown"):
        write_approved_artifact(repo_root, "spec.md", '{"product_scope": "The Hub"}')

    # The refusal must not have damaged what was already there.
    assert (repo_root / "spec.md").read_text(encoding="utf-8") == good


def test_markdown_containing_a_json_example_is_still_allowed(repo_root: Path) -> None:
    """Only content that is *entirely* JSON is refused; a fenced sample is fine."""
    doc = '# API\n\nRequest body:\n\n```json\n{"id": 1}\n```\n'

    assert write_approved_artifact(repo_root, "api.md", doc)["status"] == "written"
    assert (repo_root / "api.md").read_text(encoding="utf-8") == doc


def test_a_json_artifact_with_a_json_extension_is_allowed(repo_root: Path) -> None:
    """The guard is about prose documents, not about JSON as such."""
    assert write_approved_artifact(repo_root, "data.json", '{"a": 1}')["status"] == "written"


def test_rewriting_identical_content_is_reported_as_unchanged(repo_root: Path) -> None:
    """A repeat write must tell the agent it was a repeat.

    Models re-issue the same write to confirm it landed. The result used to look
    identical to a first write, so they kept repeating it - and every repeat is
    a model call plus an approval gate, which is what trips
    WORKFLOW_MAX_GATES_PER_STAGE. One observed run wrote the same intake three
    times and the same specification twice.
    """
    first = write_approved_artifact(repo_root, "notes.md", "same text\n")
    assert first["status"] == "written"

    second = write_approved_artifact(repo_root, "notes.md", "same text\n")
    assert second["status"] == "unchanged"
    assert second["path"] == first["path"]
    assert (repo_root / "notes.md").read_text(encoding="utf-8") == "same text\n"

    changed = write_approved_artifact(repo_root, "notes.md", "different text\n")
    assert changed["status"] == "written"
    assert (repo_root / "notes.md").read_text(encoding="utf-8") == "different text\n"


def test_write_approved_artifact_only_allows_in_artifact_directory(repo_root: Path) -> None:
    result = write_approved_artifact(repo_root, "new-note.md", "hello from artifact\n")

    assert result["path"].endswith("new-note.md")
    assert (repo_root / "new-note.md").read_text(encoding="utf-8") == "hello from artifact\n"

    with pytest.raises(RepositoryToolError):
        write_approved_artifact(repo_root, "../not-allowed.txt", "bad")


def test_run_approved_validation_is_contained(repo_root: Path, monkeypatch) -> None:
    """Validation is no longer a host shell.

    It used to run directly on the host, allowlisting only argv[0] - which let
    `python -c` through. It now routes through the sandbox, so a disallowed
    executable is reported as data rather than executed.
    """
    monkeypatch.setenv("ALLOW_COMMAND_EXECUTION", "false")

    result = run_approved_validation(repo_root, ["pytest", "-q"])
    assert result["returncode"] != 0
    assert "disabled" in result["stderr"]

    rejected = run_approved_validation(repo_root, ["rm", "-rf", "/tmp/evil"])
    assert rejected["returncode"] != 0


def test_run_approved_validation_rejects_a_string_command(repo_root: Path) -> None:
    with pytest.raises(RepositoryToolError, match="must be a list"):
        run_approved_validation(repo_root, "pytest -q")


def test_run_approved_validation_rejects_an_empty_command(repo_root: Path) -> None:
    with pytest.raises(RepositoryToolError):
        run_approved_validation(repo_root, [])


def test_repository_context_reports_the_current_git_revision() -> None:
    """The workflow's own repo is a git checkout, so branch and commit resolve."""
    context = build_repository_context(Path(__file__).resolve().parents[1])

    assert context.branch != "unknown"
    assert len(context.commit) == 40, "expected a full commit sha"
    assert "pyproject.toml" in context.dependency_files


def test_repository_context_does_not_report_an_unknown_repo_as_clean(tmp_path: Path) -> None:
    """A non-git directory must not look like a clean, stable checkout.

    Reporting "clean" here would be a false stability signal: downstream roles
    treat a clean repo as safe to build on, so an unknown state must say so.
    """
    context = build_repository_context(tmp_path)

    assert context.branch == "unknown"
    assert context.commit == "unknown"
    assert "unknown" in context.status
    assert context.status != "clean"


def test_repository_context_rejects_a_missing_root() -> None:
    with pytest.raises(RepositoryToolError):
        build_repository_context("/does/not/exist/anywhere")


# ---------------------------------------------------------------------------
# Paths as a model writes them, and edits as a turn issues them
# ---------------------------------------------------------------------------


def test_a_leading_slash_means_the_workspace_root_not_the_filesystem_root(tmp_path: Path) -> None:
    """`/docs/spec.md` addresses the same file as `docs/spec.md`.

    `write_approved_artifact` always stripped the anchor, so writes with a
    leading slash worked. Reads and edits did not, and `root / Path("/docs/x")`
    discards the root entirely in pathlib. A live agent created
    `docs/technical_specification_v2.md` and then failed every edit to the file
    it had just made, because it addressed it identically both times and only
    one of the two tools understood it.
    """
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "spec.md").write_text("one\ntwo\nthree\n")

    assert read_text_file(tmp_path, "/docs/spec.md") == "one\ntwo\nthree\n"

    sliced = read_text_lines(tmp_path, "/docs/spec.md", start_line=2, line_count=1)
    assert sliced["content"] == "two"
    # Reported back workspace-relative, never as it was typed: the dashboard
    # labels the row from this value.
    assert sliced["path"] == "docs/spec.md"

    edit_approved_artifact(tmp_path, "/docs/spec.md", "two", "TWO")
    assert (tmp_path / "docs" / "spec.md").read_text() == "one\nTWO\nthree\n"


def test_an_absolute_path_inside_the_workspace_is_understood(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text("body")
    assert read_text_file(tmp_path, str(tmp_path / "notes.md")) == "body"


def test_a_path_outside_the_workspace_still_cannot_be_read(tmp_path: Path) -> None:
    """Re-rooting must not become a way out of the workspace."""
    outside = tmp_path.parent / "secret-outside.txt"
    outside.write_text("classified")
    try:
        with pytest.raises(RepositoryToolError):
            read_text_file(tmp_path, "../secret-outside.txt")
        with pytest.raises(RepositoryToolError):
            read_text_file(tmp_path, str(outside))
    finally:
        outside.unlink()


def test_parallel_edits_to_one_file_all_survive(tmp_path: Path) -> None:
    """Every edit in a turn must land, because every one of them reports success.

    LangGraph runs the tool calls of a single turn concurrently, and an edit is a
    read-modify-write over the whole file. Unsynchronised, each call replaces its
    passage in its own copy and the last writer discards the rest - while every
    call still returns `status: edited`. A real turn asked for seven edits to one
    specification; the agent would have been told all seven applied when one had.
    """
    import concurrent.futures

    # Zero-padded so no passage is a prefix of another: `line-1` would appear
    # inside `line-10` too, and the tool rightly refuses an ambiguous `find`.
    names = [f"line-{index:02d}" for index in range(24)]
    (tmp_path / "spec.md").write_text("\n".join(names) + "\n")

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(
                lambda name: edit_approved_artifact(
                    tmp_path, "spec.md", name, name.replace("line", "EDITED")
                ),
                names,
            )
        )

    assert all(result["status"] == "edited" for result in results)
    final = (tmp_path / "spec.md").read_text()
    assert "line-" not in final
    for name in names:
        assert name.replace("line", "EDITED") in final


def test_editing_a_missing_fork_points_at_the_document_that_exists(tmp_path: Path) -> None:
    """The refusal must name the real file, not send the agent to recreate the fork.

    A pause left holding edits to `spec_v2.md` outlives the deletion of that
    file. Told only "use write_artifact to create it", the agent writes the fork
    back and `_supersedes_existing` refuses that too - so it takes two model
    calls to learn what one message can say.
    """
    (tmp_path / "spec.md").write_text("body")

    with pytest.raises(RepositoryToolError) as excinfo:
        edit_approved_artifact(tmp_path, "spec_v2.md", "body", "new body")

    message = str(excinfo.value)
    assert "spec.md" in message
    assert "write_artifact" not in message


def test_editing_a_genuinely_new_file_still_says_how_to_create_it(tmp_path: Path) -> None:
    with pytest.raises(RepositoryToolError, match="write_artifact"):
        edit_approved_artifact(tmp_path, "notes.md", "a", "b")


# ---------------------------------------------------------------------------
# A failed edit has to say how it failed
#
# An exact-match edit tool is only usable if the refusal shows the difference.
# Told only that the text is absent, the agent's sole move is to read again and
# guess again: on run-0b55ad49 `specialist_ui_ux_0` issued the identical failing
# edit five times, re-reading between each, and was stopped as a loop. Every
# attempt was a model call spent discovering something the file could show it.
# ---------------------------------------------------------------------------


SCRIPT = """// Simple Todo List JS
const tasks = [];

// Filter navigation
document.querySelectorAll('.filter-nav button').forEach(btn=>{setFilter(btn.id);});

// Delete handler
"""


def test_a_near_miss_quotes_the_real_text(tmp_path: Path) -> None:
    (tmp_path / "script.js").write_text(SCRIPT)

    with pytest.raises(RepositoryToolError) as excinfo:
        edit_approved_artifact(
            tmp_path,
            "script.js",
            # Same line, reconstructed slightly wrong - the usual failure.
            "document.querySelectorAll('.filter-nav button').forEach(btn=>{if(btn.id){}});",
            "X",
        )

    message = str(excinfo.value)
    assert "closest text in the file" in message
    assert "setFilter(btn.id)" in message, "the real line must be quoted back"
    assert ">" in message, "the nearest line must be marked"
    assert "| 5 |" in message.replace("    5 |", "| 5 |"), "line numbers make it copyable"


def test_an_unrelated_find_is_not_given_a_misleading_hint(tmp_path: Path) -> None:
    """Quoting the 'closest' line when nothing is close sends the agent astray."""
    (tmp_path / "script.js").write_text(SCRIPT)

    with pytest.raises(RepositoryToolError) as excinfo:
        edit_approved_artifact(tmp_path, "script.js", "SELECT * FROM invoices", "X")

    message = str(excinfo.value)
    assert "closest text in the file" not in message
    assert "Read the section first" in message


def test_an_empty_file_does_not_break_the_hint(tmp_path: Path) -> None:
    (tmp_path / "empty.md").write_text("")

    with pytest.raises(RepositoryToolError, match="Could not find"):
        edit_approved_artifact(tmp_path, "empty.md", "anything", "X")


def test_an_ambiguous_find_is_still_refused_without_a_hint(tmp_path: Path) -> None:
    """Two matches is a different failure: the fix is more context, not a quote."""
    (tmp_path / "d.md").write_text("same\nsame\n")

    with pytest.raises(RepositoryToolError, match="appears 2 times"):
        edit_approved_artifact(tmp_path, "d.md", "same", "X")


def test_a_successful_edit_is_unaffected(tmp_path: Path) -> None:
    (tmp_path / "script.js").write_text(SCRIPT)

    result = edit_approved_artifact(tmp_path, "script.js", "const tasks = [];", "const tasks = load();")

    assert result["status"] == "edited"
    assert "const tasks = load();" in (tmp_path / "script.js").read_text()


# ---------------------------------------------------------------------------
# One project, one directory
#
# The shared prompt told every agent to put code in a folder named after the
# product, and every agent derived that name itself. Sprint 1 of run-0b55ad49
# built `simple-todo-list-app`; sprint 2 derived `simple_todo_list_app` and
# rebuilt the application beside it. The project existed twice and neither copy
# was finished.
# ---------------------------------------------------------------------------


def test_a_directory_differing_only_in_separators_is_refused(tmp_path: Path) -> None:
    (tmp_path / "simple-todo-list-app").mkdir()

    with pytest.raises(RepositoryToolError) as excinfo:
        write_approved_artifact(tmp_path, "simple_todo_list_app/script.js", "code")

    message = str(excinfo.value)
    assert "simple-todo-list-app" in message, "the refusal must name the folder to use"
    assert "differs only in spelling" in message


def test_a_directory_differing_only_in_case_is_refused(tmp_path: Path) -> None:
    (tmp_path / "myapp").mkdir()

    with pytest.raises(RepositoryToolError, match="differs only in spelling"):
        write_approved_artifact(tmp_path, "MyApp/index.js", "code")


def test_writing_into_the_existing_directory_is_allowed(tmp_path: Path) -> None:
    (tmp_path / "simple-todo-list-app").mkdir()

    result = write_approved_artifact(tmp_path, "simple-todo-list-app/new.js", "code")

    assert result["path"] == "simple-todo-list-app/new.js"


def test_a_genuinely_different_component_is_allowed(tmp_path: Path) -> None:
    """`frontend` and `backend` share no slug; refusing them would block real work."""
    (tmp_path / "frontend").mkdir()

    result = write_approved_artifact(tmp_path, "backend/server.js", "code")

    assert result["path"] == "backend/server.js"


def test_a_file_at_the_workspace_root_forks_nothing(tmp_path: Path) -> None:
    (tmp_path / "myapp").mkdir()

    assert write_approved_artifact(tmp_path, "README.md", "text")["path"] == "README.md"


def test_the_first_project_directory_is_allowed(tmp_path: Path) -> None:
    result = write_approved_artifact(tmp_path, "my-app/index.js", "code")

    assert result["path"] == "my-app/index.js"


def test_an_existing_fork_nominates_the_established_directory(tmp_path: Path) -> None:
    """Refusing both copies would leave the agent unable to write anywhere.

    A fork made before this guard existed - as run-0b55ad49's workspace has -
    must still be recoverable: writes go to the copy that has been built in,
    and only the thin one is refused.
    """
    established = tmp_path / "simple-todo-list-app"
    established.mkdir()
    for name in ("app.js", "index.html", "styles.css", "test.html"):
        (established / name).write_text("x")
    thin = tmp_path / "simple_todo_list_app"
    thin.mkdir()
    (thin / "script.js").write_text("x")

    # The established copy stays writable.
    assert write_approved_artifact(tmp_path, "simple-todo-list-app/new.js", "code")["path"] == (
        "simple-todo-list-app/new.js"
    )

    # The fork is refused, and told where to go.
    with pytest.raises(RepositoryToolError, match="simple-todo-list-app"):
        write_approved_artifact(tmp_path, "simple_todo_list_app/other.js", "code")


def test_the_larger_copy_wins_whichever_way_round_it_is(tmp_path: Path) -> None:
    """Nomination must follow the work, not the spelling."""
    thin = tmp_path / "my-app"
    thin.mkdir()
    (thin / "a.js").write_text("x")
    established = tmp_path / "my_app"
    established.mkdir()
    for name in ("a.js", "b.js", "c.js"):
        (established / name).write_text("x")

    assert write_approved_artifact(tmp_path, "my_app/d.js", "code")["path"] == "my_app/d.js"
    with pytest.raises(RepositoryToolError, match="my_app"):
        write_approved_artifact(tmp_path, "my-app/d.js", "code")


# ---------------------------------------------------------------------------
# Indentation is the difference agents get wrong
#
# It is the part of a line a model reconstructs rather than copies. Twice on
# run-0b55ad49 a stage was stopped as a loop for re-issuing the same edit; the
# second time the file was indented with two spaces and every attempt used four,
# and the agent re-read the region four times without seeing it.
# ---------------------------------------------------------------------------


TWO_SPACE = '''// 2) escapeHtml(s)
function escapeHtml(s){
  if(typeof s!="string") return "";
  return s.replace(/&/g,"&amp;");
}
const after = 1;
'''


def test_a_passage_indented_differently_still_matches(tmp_path: Path) -> None:
    (tmp_path / "app.js").write_text(TWO_SPACE)

    result = edit_approved_artifact(
        tmp_path,
        "app.js",
        # Four spaces, as the agent wrote it; the file has two.
        'function escapeHtml(s){\n    if(typeof s!="string") return "";\n    return s.replace(/&/g,"&amp;");',
        'function escapeHtml(s){\n  if(typeof s!="string") return "";\n  return String(s).replace(/&/g,"&amp;");',
    )

    assert result["status"] == "edited"
    assert "indentation" in result["detail"], "the agent must be told why it matched"
    assert 'String(s).replace' in (tmp_path / "app.js").read_text()


def test_the_line_after_the_edit_is_not_pulled_onto_it(tmp_path: Path) -> None:
    """Swallowing the terminator put a closing brace on the end of a return."""
    (tmp_path / "app.js").write_text(TWO_SPACE)

    edit_approved_artifact(
        tmp_path,
        "app.js",
        'function escapeHtml(s){\n    if(typeof s!="string") return "";\n    return s.replace(/&/g,"&amp;");',
        'function escapeHtml(s){\n  return "x";',
    )

    text = (tmp_path / "app.js").read_text()
    assert '\n}\n' in text, "the brace must stay on its own line"
    assert "const after = 1;" in text


def test_an_ambiguous_indentation_match_is_still_refused(tmp_path: Path) -> None:
    """Relaxing whitespace must not relax uniqueness."""
    (tmp_path / "d.js").write_text("  a();\n  b();\n\n    a();\n    b();\n")

    with pytest.raises(RepositoryToolError, match="Could not find"):
        edit_approved_artifact(tmp_path, "d.js", "a();\nb();", "c();")


def test_text_inside_the_line_must_still_match_exactly(tmp_path: Path) -> None:
    """Only the margins are ignored - never the code itself."""
    (tmp_path / "d.js").write_text("  const total = subtotal + tax;\n")

    with pytest.raises(RepositoryToolError, match="Could not find"):
        edit_approved_artifact(tmp_path, "d.js", "const total = subtotal - tax;", "x")


def test_an_exact_match_is_preferred_and_unchanged(tmp_path: Path) -> None:
    (tmp_path / "d.js").write_text("  a();\n")

    result = edit_approved_artifact(tmp_path, "d.js", "  a();", "  b();")

    assert result["status"] == "edited"
    assert "detail" not in result, "an exact match needs no explanation"
    assert (tmp_path / "d.js").read_text() == "  b();\n"


# ---------------------------------------------------------------------------
# `read_file` decorates; `edit_artifact` demands exactness
#
# The read tool prefixes every line with its number, and an agent that copies a
# passage out of a read is copying something the file does not contain. It shows
# as a `find` whose first line is clean - the visible prefix got stripped - and
# whose later lines each begin `27  ` or `124      `.
#
# Three of four consecutive failed edits on run-0b55ad49 were exactly this,
# across index.html, styles.css and app.js. Nothing about the intent was wrong;
# the agent was quoting our own output back at us.
# ---------------------------------------------------------------------------


NUMBERED_TARGET = '''<div id="filters">
<button data-action="filter" data-value="all">All</button>
</div>
<ul class="task-list">
</ul>
'''


def test_line_numbers_copied_from_a_read_are_forgiven(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text(NUMBERED_TARGET)

    result = edit_approved_artifact(
        tmp_path,
        "index.html",
        '<div id="filters">\n22  <button data-action="filter" data-value="all">All</button>',
        '<div id="filters" role="group">\n<button data-action="filter" data-value="all">All</button>',
    )

    assert result["status"] == "edited"
    assert "line numbers" in result["detail"], "the agent must learn to strip them"
    assert 'role="group"' in (tmp_path / "index.html").read_text()


def test_line_numbers_and_indentation_together_are_forgiven(tmp_path: Path) -> None:
    (tmp_path / "app.js").write_text("function f(){\n  const a = 1;\n  return a;\n}\n")

    result = edit_approved_artifact(
        tmp_path,
        "app.js",
        # Numbered continuation *and* the wrong margin.
        "function f(){\n124      const a = 1;\n125      return a;",
        "function f(){\n  const a = 2;\n  return a;",
    )

    assert result["status"] == "edited"
    assert "const a = 2;" in (tmp_path / "app.js").read_text()


def test_stripping_numbers_cannot_create_an_ambiguous_match(tmp_path: Path) -> None:
    """Every fallback still requires a unique match; only transcription is forgiven."""
    (tmp_path / "d.txt").write_text("alpha\nbravo\n\nalpha\nbravo\n")

    with pytest.raises(RepositoryToolError, match="Could not find"):
        edit_approved_artifact(tmp_path, "d.txt", "alpha\n2  bravo", "x")


def test_content_that_genuinely_starts_with_a_number_is_not_mangled(tmp_path: Path) -> None:
    """A line beginning with digits is real content, not a prefix."""
    (tmp_path / "d.md").write_text("Steps:\n1  Preheat the oven\n2  Add flour\n")

    result = edit_approved_artifact(
        tmp_path, "d.md", "Steps:\n1  Preheat the oven", "Steps:\n1  Preheat to 200C"
    )

    assert result["status"] == "edited"
    assert "Preheat to 200C" in (tmp_path / "d.md").read_text()
    assert "2  Add flour" in (tmp_path / "d.md").read_text()


def test_a_find_with_no_numbers_is_unaffected(tmp_path: Path) -> None:
    (tmp_path / "d.txt").write_text("hello world\n")

    result = edit_approved_artifact(tmp_path, "d.txt", "hello world", "goodbye")

    assert result["status"] == "edited"
    assert "detail" not in result


# ---------------------------------------------------------------------------
# One project directory, pinned for the life of the run
#
# run-0b55ad49 built the same to-do application three times - in
# `simple-todo-list-app`, `simple_todo_list_app` and `thehub` - because each
# stage derived a directory name for itself and nothing carried the first choice
# forward. None of the three was ever finished.
#
# A marker on disk rather than graph state, because what it has to survive is a
# process: agents are constructed per stage and none can see what an earlier one
# decided.
# ---------------------------------------------------------------------------


def test_the_first_code_write_pins_the_project_directory(tmp_path: Path) -> None:
    write_approved_artifact(tmp_path, "my-app/index.js", "code")

    assert pinned_project_directory(tmp_path) == "my-app"


def test_a_later_stage_cannot_choose_a_different_directory(tmp_path: Path) -> None:
    write_approved_artifact(tmp_path, "my-app/index.js", "code")

    with pytest.raises(RepositoryToolError) as excinfo:
        write_approved_artifact(tmp_path, "thehub/app.js", "code")

    assert "my-app" in str(excinfo.value), "the refusal must name the pinned directory"


def test_the_pinned_directory_stays_fully_writable(tmp_path: Path) -> None:
    write_approved_artifact(tmp_path, "my-app/index.js", "code")

    deep = write_approved_artifact(tmp_path, "my-app/src/lib/util.js", "code")

    assert deep["path"] == "my-app/src/lib/util.js"


def test_documents_and_root_files_are_never_pinned(tmp_path: Path) -> None:
    """`docs/` and a root README are not the project and must not claim the pin."""
    write_approved_artifact(tmp_path, "docs/spec.md", "text")
    write_approved_artifact(tmp_path, "README.md", "text")

    assert pinned_project_directory(tmp_path) is None

    write_approved_artifact(tmp_path, "my-app/index.js", "code")
    assert pinned_project_directory(tmp_path) == "my-app"


def test_the_pin_survives_a_new_process(tmp_path: Path) -> None:
    """The marker is on disk precisely so a later stage in a later process sees it."""
    write_approved_artifact(tmp_path, "my-app/index.js", "code")

    # Nothing in memory is shared here; this is exactly what a later stage does.
    assert (tmp_path / PROJECT_MARKER).read_text().strip() == "my-app"
    assert pinned_project_directory(tmp_path) == "my-app"


def test_the_first_choice_is_the_one_that_lasts(tmp_path: Path) -> None:
    """A second write must not quietly re-pin to whatever asked last."""
    write_approved_artifact(tmp_path, "my-app/index.js", "code")
    with pytest.raises(RepositoryToolError):
        write_approved_artifact(tmp_path, "other-app/index.js", "code")

    assert pinned_project_directory(tmp_path) == "my-app"


# ---------------------------------------------------------------------------
# One project manifest, in the project
#
# run-0b55ad49 ended with two npm projects: `package.json` at the workspace root
# declaring jest 30, another in the project declaring jest 29, two
# `jest.config.js`, two `jestSetup.js`, two `node_modules`. `npm test` ran the
# root's jest against the project's tests and failed with "Identifier 'jest' has
# already been declared". Three remediation rounds chased that and never had a
# chance.
# ---------------------------------------------------------------------------


def test_a_manifest_at_the_root_is_refused_once_a_project_exists(tmp_path: Path) -> None:
    write_approved_artifact(tmp_path, "my-app/index.js", "code")

    for manifest in ("package.json", "jest.config.js", "tsconfig.json", "requirements.txt"):
        with pytest.raises(RepositoryToolError) as excinfo:
            write_approved_artifact(tmp_path, manifest, "{}" if manifest.endswith("json") else "x")
        assert "my-app" in str(excinfo.value), f"{manifest}: refusal must name where it belongs"


def test_a_manifest_inside_the_project_is_allowed(tmp_path: Path) -> None:
    write_approved_artifact(tmp_path, "my-app/index.js", "code")

    result = write_approved_artifact(tmp_path, "my-app/package.json", '{"name":"x"}')

    assert result["path"] == "my-app/package.json"


def test_ordinary_root_files_are_untouched(tmp_path: Path) -> None:
    """A README or .gitignore at the root is normal and must stay allowed."""
    write_approved_artifact(tmp_path, "my-app/index.js", "code")

    assert write_approved_artifact(tmp_path, "README.md", "# Title\n\ntext")["path"] == "README.md"
    assert write_approved_artifact(tmp_path, ".gitignore", "node_modules\n")["path"] == ".gitignore"


def test_a_manifest_is_allowed_before_any_project_is_pinned(tmp_path: Path) -> None:
    """Nothing to conflict with yet; refusing would block a legitimate layout."""
    assert write_approved_artifact(tmp_path, "package.json", '{"name":"x"}')["path"] == "package.json"


# ---------------------------------------------------------------------------
# Over-escaping, and finds too short to identify anything
#
# A model writing a tool call in JSON has to escape a backslash, and one already
# thinking about escaping tends to escape it twice. On run-0b55ad49 a specialist
# was stopped as a loop after five identical attempts to delete a literal
# backslash-n from a test file: it searched for three characters where two
# existed, every time.
# ---------------------------------------------------------------------------


def test_a_doubled_backslash_still_matches(tmp_path: Path) -> None:
    literal_backslash_n = chr(92) + "n"
    (tmp_path / "t.js").write_text(
        f"// header\n{literal_backslash_n}const x = require('jsdom');\nconst y = 1;\n"
    )

    result = edit_approved_artifact(
        tmp_path,
        "t.js",
        # As the agent sent it: the backslash escaped twice.
        chr(92) + chr(92) + "nconst x = require('jsdom');",
        "const x = require('jsdom');",
    )

    assert result["status"] == "edited"
    assert "doubled backslashes" in result["detail"]
    assert literal_backslash_n not in (tmp_path / "t.js").read_text()


def test_a_find_too_short_to_identify_a_passage_says_so(tmp_path: Path) -> None:
    """Two characters cannot name a passage, and a near-match hint cannot help."""
    (tmp_path / "t.js").write_text("const a = 1;\nconst b = 2;\n")

    with pytest.raises(RepositoryToolError) as excinfo:
        edit_approved_artifact(tmp_path, "t.js", chr(92) + chr(92) + "n", "")

    message = str(excinfo.value)
    assert "rarely identifies one passage" in message
    assert "whole line" in message


def test_collapsing_backslashes_cannot_create_an_ambiguous_match(tmp_path: Path) -> None:
    esc = chr(92)
    (tmp_path / "d.txt").write_text(f"{esc}nalpha\n{esc}nalpha\n")

    with pytest.raises(RepositoryToolError):
        edit_approved_artifact(tmp_path, "d.txt", esc + esc + "nalpha", "x")


def test_text_with_no_backslashes_is_unaffected(tmp_path: Path) -> None:
    (tmp_path / "d.txt").write_text("hello world\n")

    result = edit_approved_artifact(tmp_path, "d.txt", "hello world", "goodbye world")

    assert result["status"] == "edited"
    assert "detail" not in result


# ---------------------------------------------------------------------------
# A file standing where a directory must go
#
# `mkdir(exist_ok=True)` tolerates an existing *directory* and nothing else.
# When a plain file occupies the path, it raises FileExistsError - and on
# run-95ca3f72 that escaped as an unhandled exception and killed the stage,
# rather than becoming a tool result the agent could act on.
# ---------------------------------------------------------------------------


def test_a_file_where_a_directory_belongs_is_a_readable_refusal(tmp_path: Path) -> None:
    (tmp_path / "todo-app").write_text("placeholder")

    with pytest.raises(RepositoryToolError) as excinfo:
        write_approved_artifact(tmp_path, "todo-app/index.html", "<html></html>")

    message = str(excinfo.value)
    assert "already exists as a file" in message
    assert "todo-app" in message, "the refusal must name what is in the way"


def test_the_blocker_is_found_at_any_depth(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "src").write_text("a file, not a directory")

    with pytest.raises(RepositoryToolError, match="already exists as a file"):
        write_approved_artifact(tmp_path, "app/src/deep/index.js", "code")


def test_an_ordinary_nested_write_still_creates_its_directories(tmp_path: Path) -> None:
    result = write_approved_artifact(tmp_path, "app/src/lib/util.js", "code")

    assert result["path"] == "app/src/lib/util.js"
    assert (tmp_path / "app" / "src" / "lib" / "util.js").read_text() == "code"


def test_the_refusal_is_recoverable_not_a_crash(tmp_path: Path) -> None:
    """Every other failure here is a RepositoryToolError; this one was not."""
    from app.tools.agent_toolkit import build_artifact_write_tool

    (tmp_path / "todo-app").write_text("placeholder")
    write = build_artifact_write_tool(str(tmp_path))

    result = write.invoke({"relative_path": "todo-app/index.html", "content": "<html>"})

    assert "error" in result, "the agent must get a result it can act on"
    assert "already exists as a file" in result["error"]


def test_an_edit_escaped_as_json_still_matches(tmp_path):
    r"""A `find` carrying \n and \" against a file with a newline and a quote.

    Observed on run-95ca3f72 at 10:28: the agent read `todo-app/package.json`
    and then issued the identical edit three times, each with
    `'"devDependencies": {\n    \"jest\": ...'` - its payload escaped one level
    too deep, as if it were writing the JSON string by hand. Collapsing doubled
    backslashes does nothing here because there are none, so every existing
    fallback missed and the agent got no signal that its transcription rather
    than its intent was wrong.
    """
    from app.tools.repository import edit_approved_artifact

    manifest = tmp_path / "package.json"
    manifest.write_text('{\n  "devDependencies": {\n    "jest": "^29.7.0"\n  }\n}\n')

    result = edit_approved_artifact(
        str(tmp_path),
        "package.json",
        '"devDependencies": {\\n    \\"jest\\": \\"^29.7.0\\"',
        '"devDependencies": {\n    "jest": "^30.0.0"',
    )

    assert result["status"] == "edited"
    assert "JSON escapes" in result["detail"]
    assert '"jest": "^30.0.0"' in manifest.read_text()


def test_a_file_holding_the_literal_escape_is_not_disturbed(tmp_path):
    r"""The opposite case still works: a file that really contains backslash-n."""
    from app.tools.repository import edit_approved_artifact

    source = tmp_path / "broken.js"
    source.write_text('const message = "line one\\nline two";\n')

    result = edit_approved_artifact(
        str(tmp_path), "broken.js", 'line one\\nline two', "line one line two"
    )

    assert result["status"] == "edited"
    assert "line one line two" in source.read_text()


def test_json_unescaping_is_only_offered_when_it_is_unique(tmp_path):
    """The uniqueness requirement is the safety property and is not relaxed."""
    from app.tools.repository import RepositoryToolError, edit_approved_artifact

    source = tmp_path / "two.txt"
    source.write_text('say "hi"\nsay "hi"\n')

    with pytest.raises(RepositoryToolError):
        edit_approved_artifact(str(tmp_path), "two.txt", 'say \\"hi\\"', "say hello")


def test_unknown_escapes_are_left_alone():
    r"""`\d` in a regex is not an escape to interpret."""
    from app.tools.repository import _without_json_escaping

    assert _without_json_escaping(r"const re = /\d+/;") is None
    assert _without_json_escaping("plain text") is None


def test_a_rejected_write_does_not_pin_a_project_directory(tmp_path):
    """The pin is permanent, so only a write that landed may set it.

    Observed on run-64df2b20: the technical lead wrote a 1-byte file named
    `med2`. A specialist then wrote `med2/app/__init__.py`, which pinned `med2`
    and *then* failed, because `med2` was a file and could not also be a
    directory. The specialist deleted the file, created `med2-app`, and every
    write into it was refused for not being `med2` - as were `med2-app-1` and
    `med2-application`. There was no directory the run was allowed to use.
    """
    from app.tools.repository import (
        RepositoryToolError,
        pinned_project_directory,
        write_approved_artifact,
    )

    (tmp_path / "med2").write_text("#")

    with pytest.raises(RepositoryToolError) as exc:
        write_approved_artifact(str(tmp_path), "med2/app/__init__.py", "x = 1")

    assert "already exists as a file" in str(exc.value)
    assert pinned_project_directory(tmp_path) is None


def test_the_run_can_still_choose_a_directory_after_a_rejected_write(tmp_path):
    """The recovery the deadlocked run attempted and was refused."""
    from app.tools.repository import (
        RepositoryToolError,
        pinned_project_directory,
        write_approved_artifact,
    )

    (tmp_path / "med2").write_text("#")
    with pytest.raises(RepositoryToolError):
        write_approved_artifact(str(tmp_path), "med2/app/__init__.py", "x = 1")

    (tmp_path / "med2").unlink()
    write_approved_artifact(str(tmp_path), "med2-app/app/__init__.py", "x = 1")

    assert pinned_project_directory(tmp_path) == "med2-app"
    assert (tmp_path / "med2-app/app/__init__.py").read_text() == "x = 1"


def test_a_successful_write_still_pins(tmp_path):
    from app.tools.repository import pinned_project_directory, write_approved_artifact

    write_approved_artifact(str(tmp_path), "todo-app/index.html", "<html></html>")

    assert pinned_project_directory(tmp_path) == "todo-app"


def test_code_is_refused_in_the_documents_directory(tmp_path):
    """`docs/` is read as documentation by every reviewer.

    Measured on run-304add54: the testing specialist wrote
    `/docs/test_suite.js` and then edited it five times running, fighting JSDOM
    scope problems in a file no test runner would ever collect - the project's
    runner looks in the project directory. The repeat guard stopped the stage;
    the file had been in the wrong place since the first write.
    """
    from app.tools.repository import RepositoryToolError, write_approved_artifact

    with pytest.raises(RepositoryToolError) as exc:
        write_approved_artifact(str(tmp_path), "docs/test_suite.js", "// tests")

    message = str(exc.value)
    assert "`docs/` is for documents" in message
    assert "belongs in the project directory" in message


@pytest.mark.parametrize("name", ["helper.py", "style.css", "index.html", "run.sh"])
def test_every_code_kind_is_refused_there(tmp_path, name):
    from app.tools.repository import RepositoryToolError, write_approved_artifact

    with pytest.raises(RepositoryToolError):
        write_approved_artifact(str(tmp_path), f"docs/{name}", "x")


@pytest.mark.parametrize("name", ["spec.md", "notes.txt", "diagram.svg", "data.json"])
def test_documents_are_still_welcome_there(tmp_path, name):
    from app.tools.repository import write_approved_artifact

    assert write_approved_artifact(str(tmp_path), f"docs/{name}", "x")["status"]


def test_code_elsewhere_is_unaffected(tmp_path):
    from app.tools.repository import write_approved_artifact

    assert write_approved_artifact(str(tmp_path), "app/test_suite.js", "// t")["status"]
