"""Tests for the safe repository inspection tool layer.

The core idea is simple: tools may inspect a repository, but only inside a
trusted boundary. These tests make that contract explicit by proving that reads,
searches, and writes stay inside the repository or approved artifact directory.
"""

from __future__ import annotations

import re
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
    assert "setFilter(btn.id)" in message, "the real line must be quoted back"
    # Named, not just shown. run-0deeb8bf sent a passage that differed from the
    # file by a leading `// `, was handed the correct passage three times, and
    # ended the stage reporting it could not locate the code.
    assert "These lines differ" in message
    assert "you sent:" in message and "file has:" in message
    assert "(line 5)" in message, "line numbers make it copyable"


APP_JS = """const STORAGE_KEY = 'todoTasks';
let tasks = [];

function loadTasks() {
  const raw = localStorage.getItem(STORAGE_KEY);
  tasks = raw ? JSON.parse(raw) : [];
}

function saveTasks() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(tasks));
}
"""


DUPLICATED = """import test from 'node:test';
// renders both tasks when the input is valid
const validTasks = [{ id: 1 }, { id: 2 }];
renderTasks(validTasks);
assert.strictEqual(listEl.children.length, 2);

// duplicate block left behind by an earlier edit
const validTasks = [{ id: 1 }, { id: 2 }];
renderTasks(validTasks);
assert.strictEqual(listEl.children.length, 2);
console.log('done');
"""

AMBIGUOUS = (
    "const validTasks = [{ id: 1 }, { id: 2 }];\n"
    "renderTasks(validTasks);\n"
    "assert.strictEqual(listEl.children.length, 2);"
)


def test_the_same_document_twice_is_unchanged_whatever_the_final_newline(
    tmp_path: Path,
) -> None:
    """run-130deeef's `specialist_backend_8`, one cycle before it was stopped.

    It wrote `docs/blocker.md` with a trailing newline, then wrote the same 600
    characters without one. That counted as a real change, so the second write
    reported "written" instead of "unchanged", and the "do not write it again"
    signal - and the no-op refusal behind it - both arrived a cycle late.
    """
    body = "# Blocker\nThe task requires a shell script."

    assert write_approved_artifact(tmp_path, "docs/blocker.md", body + "\n")["status"] == "written"
    assert write_approved_artifact(tmp_path, "docs/blocker.md", body)["status"] == "unchanged"
    assert (
        write_approved_artifact(tmp_path, "docs/blocker.md", body + "\n\n\n")["status"]
        == "unchanged"
    )
    assert (tmp_path / "docs" / "blocker.md").read_text().endswith("script.\n")


def test_an_empty_file_stays_empty(tmp_path: Path) -> None:
    """A newline added to nothing is a file with a blank line in it."""
    write_approved_artifact(tmp_path, "docs/empty.md", "")

    assert (tmp_path / "docs" / "empty.md").read_text() == ""


BLANK_LINE_FILE = """test('CRUD operations persist in localStorage', async () => {
  // Reset storage
  mockLocalStorage._data = {};

  // Add a task
  addTask({ title: 'Persisted', status: 'todo' });

  // Simulate module reload by re-importing app.js
  const { loadTasks } = await import('./app.js');
});
"""


def test_a_passage_remembered_without_its_blank_lines_still_matches(
    tmp_path: Path,
) -> None:
    """run-499c771a's `specialist_testing_3`, two of four failed edits.

    Every line it sent is in the file, in that order, character for character.
    The only difference is a blank line between the second and third that it
    did not remember.
    """
    (tmp_path / "app.test.mjs").write_text(BLANK_LINE_FILE)

    result = edit_approved_artifact(
        tmp_path,
        "app.test.mjs",
        "  // Reset storage\n  mockLocalStorage._data = {};\n"
        "  // Add a task\n  addTask({ title: 'Persisted', status: 'todo' });",
        "  // replaced",
    )

    assert "ignoring blank lines" in (result.get("detail") or "")
    assert "// replaced" in (tmp_path / "app.test.mjs").read_text()


def test_a_line_remembered_with_a_blank_line_around_it_still_matches(
    tmp_path: Path,
) -> None:
    """The other two. It sent one line wrapped in newlines it had invented."""
    (tmp_path / "app.test.mjs").write_text(BLANK_LINE_FILE)

    result = edit_approved_artifact(
        tmp_path,
        "app.test.mjs",
        "\nconst { loadTasks } = await import('./app.js');\n",
        "  const { loadTasks } = await import('./app.mjs');",
    )

    assert result["status"] == "edited"
    assert "./app.mjs" in (tmp_path / "app.test.mjs").read_text()


def test_a_short_line_is_not_matched_by_ignoring_blank_lines(tmp_path: Path) -> None:
    """`}` is in every file several times; matching one of them is a guess."""
    (tmp_path / "x.js").write_text("function a() {\n}\n\nfunction b() {\n}\n")

    with pytest.raises(RepositoryToolError):
        edit_approved_artifact(tmp_path, "x.js", "\n}\n", "}  // end")


def test_blank_line_matching_still_requires_one_place(tmp_path: Path) -> None:
    """The uniqueness guarantee is the whole safety property of this tool.

    Both copies here are spaced the same way, so neither is reachable by
    ignoring indentation alone - only by ignoring the blank lines, which finds
    two and must therefore refuse.
    """
    body = "a();\nb();\n\nc();\nx();\na();\nb();\n\nc();\n"
    (tmp_path / "x.js").write_text(body)

    with pytest.raises(RepositoryToolError):
        edit_approved_artifact(tmp_path, "x.js", "a();\nb();\nc();", "d();")

    assert (tmp_path / "x.js").read_text() == body


def test_an_ambiguous_edit_is_shown_what_differs(tmp_path: Path) -> None:
    """"Include a line from above or below" is advice, not information.

    run-d3965815's model wrote `app.test.mjs` with the same block at lines 52
    and 73, hit the ambiguity, and sent the byte-identical failing call again
    rather than guess - it does not have the file in front of it, and the two
    copies are near-identical or it would not have collided with both. Six of
    that run's thirteen edit failures were this.
    """
    (tmp_path / "app.test.mjs").write_text(DUPLICATED)

    with pytest.raises(RepositoryToolError) as caught:
        edit_approved_artifact(tmp_path, "app.test.mjs", AMBIGUOUS, "X")

    message = str(caught.value)
    assert "appears 2 times" in message
    assert "lines 3 and 8" in message
    # The lines that actually tell the copies apart, both of them.
    assert "// renders both tasks when the input is valid" in message
    assert "// duplicate block left behind by an earlier edit" in message


def test_the_surroundings_do_not_run_off_the_ends_of_the_file(tmp_path: Path) -> None:
    (tmp_path / "x.js").write_text("const a = 1;\nconst a = 1;\n")

    with pytest.raises(RepositoryToolError) as caught:
        edit_approved_artifact(tmp_path, "x.js", "const a = 1;", "const b = 2;")

    message = str(caught.value)
    assert "(start of file)" in message
    assert "(end of file)" in message


@pytest.mark.parametrize("path", ["docs", "docs/"])
def test_writing_to_a_directory_says_what_to_do(tmp_path: Path, path: str) -> None:
    """run-08acb1ee's `specialist_ui_ux_1` wrote to `docs/` and got

        Could not write artifact to docs/: [Errno 21] Is a directory:
        '/app/data/workspaces/t64-run-08acb1ee-.../docs'

    an errno and a host path, naming neither the problem nor the fix. Every
    other failure in this module is a sentence the agent can act on.
    """
    write_approved_artifact(tmp_path, "docs/notes.md", "# notes\n")
    write_approved_artifact(tmp_path, "docs/plan.md", "# plan\n")

    with pytest.raises(RepositoryToolError) as caught:
        write_approved_artifact(tmp_path, path, "# oops\n")

    message = str(caught.value)
    assert "that is a directory, not a file" in message
    assert "notes.md" in message, "say what is already in there"
    assert "/something.md" in message, "and name the shape of a path that works"
    assert "Errno" not in message


def test_an_empty_directory_still_gets_a_usable_message(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()

    with pytest.raises(RepositoryToolError, match="that is a directory, not a file"):
        write_approved_artifact(tmp_path, "empty", "x\n")


def test_an_ordinary_write_is_unaffected(tmp_path: Path) -> None:
    assert write_approved_artifact(tmp_path, "docs/spec.md", "# spec\n")["status"]


def test_an_edit_says_where_it_landed(tmp_path: Path) -> None:
    """A model that has just edited a file reads the whole file back.

    Measured on run-a7150a6c's `specialist_testing_1`: five full reads of a
    96-line `app.test.mjs`, one after each single-line edit, in a stage of
    twenty-six calls. None is a repeat the notices can catch - the file
    genuinely changed each time, because the model had just changed it. The
    re-read asks a reasonable question the result did not answer.
    """
    body = "".join(f"const line{index} = {index};\n" for index in range(12))
    (tmp_path / "a.js").write_text(body)

    result = edit_approved_artifact(tmp_path, "a.js", "const line5 = 5;", "const line5 = 500;")

    context = result.get("context") or ""
    assert "Now reads" in context
    assert ">    6 | const line5 = 500;" in context, "the changed line, marked and numbered"
    assert "const line3 = 3;" in context, "with context above"
    assert "const line8 = 8;" in context, "and below"


def test_a_deletion_has_no_passage_to_show(tmp_path: Path) -> None:
    (tmp_path / "a.js").write_text("const a = 1;\nconst b = 2;\n")

    result = edit_approved_artifact(tmp_path, "a.js", "const a = 1;\n", "")

    assert "context" not in result
    assert result["status"] == "edited"


def test_the_context_does_not_run_off_the_file(tmp_path: Path) -> None:
    (tmp_path / "a.js").write_text("const a = 1;\nconst b = 2;\n")

    result = edit_approved_artifact(tmp_path, "a.js", "const a = 1;", "const a = 11;")

    assert ">    1 | const a = 11;" in (result.get("context") or "")


def test_an_edit_sent_twice_is_told_it_already_landed(tmp_path: Path) -> None:
    """run-0deeb8bf's `defect_fix_2_0`, four model calls and a failed stage.

    At 14:15:33 it made this edit and was told "edited". At 14:15:51, 14:16:19,
    14:16:36 and 14:16:46 it sent the byte-identical call again and was told
    "could not find that text" - true, because its own edit had removed it -
    and the nearest passage quoted back was its own new code, which reads like
    a near miss. The stage ended reporting the fix could not be applied.
    """
    (tmp_path / "app.js").write_text(APP_JS)
    find = (
        "function saveTasks() {\n"
        "  localStorage.setItem(STORAGE_KEY, JSON.stringify(tasks));\n"
        "}"
    )
    replace = (
        "function saveTasks() {\n"
        "  const storage = global.localStorage || localStorage;\n"
        "  storage.setItem(STORAGE_KEY, JSON.stringify(tasks));\n"
        "}"
    )
    assert edit_approved_artifact(tmp_path, "app.js", find, replace)["status"] == "edited"

    with pytest.raises(RepositoryToolError) as caught:
        edit_approved_artifact(tmp_path, "app.js", find, replace)

    message = str(caught.value)
    assert "already been applied" in message
    assert "at line 9" in message
    assert "These lines differ" not in message, "the one fact that matters, alone"


def test_a_deletion_is_not_mistaken_for_an_edit_already_made(tmp_path: Path) -> None:
    """An empty `replace` is in every file; it proves nothing."""
    (tmp_path / "app.js").write_text(APP_JS)

    with pytest.raises(RepositoryToolError) as caught:
        edit_approved_artifact(tmp_path, "app.js", "function nosuchthing() {}", "")

    assert "already been applied" not in str(caught.value)


def test_a_short_replacement_is_not_mistaken_for_one_either(tmp_path: Path) -> None:
    """`}` is already in the file and says nothing about what was done."""
    (tmp_path / "app.js").write_text(APP_JS)

    with pytest.raises(RepositoryToolError) as caught:
        edit_approved_artifact(tmp_path, "app.js", "function nosuchthing() {}", "}")

    assert "already been applied" not in str(caught.value)


def test_a_comment_marker_the_model_added_is_named(tmp_path: Path) -> None:
    """The three characters that cost run-0deeb8bf a defect fix.

    `defect_fix_2_0` sent the `saveTasks` body with `// ` on the first line -
    it was trying to comment the function out and put the result in `find`.
    The tool quoted the correct passage back three times; the model could not
    see what differed, and ended the stage reporting "Unable to locate exact
    saveTasks function code for editing; cannot apply fix."
    """
    (tmp_path / "app.js").write_text(APP_JS)

    with pytest.raises(RepositoryToolError) as caught:
        edit_approved_artifact(
            tmp_path,
            "app.js",
            "// function saveTasks() {\n"
            "  localStorage.setItem(STORAGE_KEY, JSON.stringify(tasks));\n"
            "}",
            "",
        )

    message = str(caught.value)
    assert "you sent:  // function saveTasks() {" in message
    assert "file has:  function saveTasks() {" in message
    assert "(line 9)" in message


def test_a_passage_that_is_merely_indented_differently_still_just_works(
    tmp_path: Path,
) -> None:
    """The forgiving path runs first, so this never reaches the difference report."""
    (tmp_path / "app.js").write_text(APP_JS)

    result = edit_approved_artifact(
        tmp_path,
        "app.js",
        "    function saveTasks() {\n"
        "      localStorage.setItem(STORAGE_KEY, JSON.stringify(tasks));\n"
        "    }",
        "function saveTasks() {}",
    )

    assert result["status"]
    assert "function saveTasks() {}" in (tmp_path / "app.js").read_text()


def test_a_different_passage_is_not_diffed_line_by_line(tmp_path: Path) -> None:
    """Two unrelated passages compared line by line read as noise."""
    (tmp_path / "app.js").write_text(APP_JS)

    with pytest.raises(RepositoryToolError) as caught:
        edit_approved_artifact(
            tmp_path, "app.js", "def totally_other():\n    return 1\n", "x"
        )

    assert "These lines differ" not in str(caught.value)


def test_an_unrelated_find_is_not_given_a_misleading_hint(tmp_path: Path) -> None:
    """Quoting the 'closest' line when nothing is close sends the agent astray.

    That protection still holds, and a short file now does better than silence:
    it is quoted whole, which cannot mislead because there is nothing else in
    it. Run-36eb1260 was stopped as a loop after a five-line file answered three
    failed edits with "Read the section first" and nothing more.
    """
    (tmp_path / "script.js").write_text(SCRIPT)

    with pytest.raises(RepositoryToolError) as excinfo:
        edit_approved_artifact(tmp_path, "script.js", "SELECT * FROM invoices", "X")

    message = str(excinfo.value)
    # No false claim that any line here resembles the find.
    assert "closest text in the file" not in message
    assert "marks the nearest line" not in message
    # The file is short, so it is simply shown.
    assert "This is the entire file:" in message
    assert "const tasks = [];" in message


def test_an_unrelated_find_in_a_long_file_still_says_nothing(tmp_path: Path) -> None:
    """Above the short-file threshold the original protection is all there is."""
    body = "\n".join(f"const line{i} = {i};" for i in range(80)) + "\n"
    (tmp_path / "long.js").write_text(body)

    with pytest.raises(RepositoryToolError) as excinfo:
        edit_approved_artifact(tmp_path, "long.js", "SELECT * FROM invoices", "X")

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
    """Two directories that share no slug are not a fork of one another, and
    refusing the second would block real work.

    The example used to be `frontend` beside `backend`. Those are now refused
    one level up, as tiers of a product rather than products - whichever was
    written first was pinned as the whole project and the other could never be
    written at all. The fork check itself is unchanged, so this tests it with
    two directories inside a project, which is where components actually live.
    """
    write_approved_artifact(tmp_path, "task-dashboard/frontend/App.jsx", "// ui")

    result = write_approved_artifact(tmp_path, "task-dashboard/backend/server.js", "code")

    assert result["path"] == "task-dashboard/backend/server.js"


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
    assert (tmp_path / "app" / "src" / "lib" / "util.js").read_text() == "code\n"


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
    assert (tmp_path / "med2-app/app/__init__.py").read_text() == "x = 1\n"


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


def test_the_refusal_names_where_to_write_instead(tmp_path):
    """A refusal that says only "not here" is a dead end.

    The agent has read the rule and cannot apply it: it does not know which of
    the directories it has seen is the project one. On run-2bfa5e6e the testing
    specialist was refused `docs/tests/playwright.config.js`, concluded "the
    requirement conflicts, so we have a blocker", and shipped the milestone
    with no UI tests - the review then failed the run for missing them. Naming
    the destination is what `_tests_outside_the_project` already does.
    """
    from app.tools.repository import RepositoryToolError, write_approved_artifact

    # Pin a project directory first, so the refusal has a destination to name.
    write_approved_artifact(str(tmp_path), "todo-app/index.html", "<html></html>")

    with pytest.raises(RepositoryToolError) as exc:
        write_approved_artifact(
            str(tmp_path), "docs/tests/playwright.config.js", "// config"
        )

    message = str(exc.value)
    assert "Write 'todo-app/tests/playwright.config.js' instead." in message


def test_the_refusal_names_the_workspace_root_before_any_project_is_pinned(
    tmp_path,
):
    """With no project pinned yet, the destination is the workspace root.

    The pin is written by the first code write, so this refusal can be the very
    first one. Naming `tests/...` rather than a project it cannot know keeps
    the guidance true instead of invented.
    """
    from app.tools.repository import RepositoryToolError, write_approved_artifact

    with pytest.raises(RepositoryToolError) as exc:
        write_approved_artifact(str(tmp_path), "docs/run.sh", "echo hi")

    assert "Write 'run.sh' instead." in str(exc.value)


@pytest.mark.parametrize("name", ["helper.py", "style.css", "index.html", "run.sh"])
def test_every_code_kind_is_refused_there(tmp_path, name):
    from app.tools.repository import RepositoryToolError, write_approved_artifact

    with pytest.raises(RepositoryToolError):
        write_approved_artifact(str(tmp_path), f"docs/{name}", "x")


@pytest.mark.parametrize(
    ("name", "body"),
    [
        ("spec.md", "x"),
        ("notes.txt", "x"),
        ("diagram.svg", "x"),
        # This case is about *where* a .json may go, so it needs content that
        # passes the structural check - which judges JSON everywhere.
        ("data.json", '{"x": 1}'),
    ],
)
def test_documents_are_still_welcome_there(tmp_path, name, body):
    from app.tools.repository import write_approved_artifact

    assert write_approved_artifact(str(tmp_path), f"docs/{name}", body)["status"]


def test_code_elsewhere_is_unaffected(tmp_path):
    from app.tools.repository import write_approved_artifact

    assert write_approved_artifact(str(tmp_path), "app/test_suite.js", "// t")["status"]


# --- a test belongs with the code it tests --------------------------------


def test_a_test_at_the_workspace_root_is_refused_once_a_project_exists(repo_root: Path) -> None:
    """The runner is invoked inside the project, so a suite outside it is one
    the project's own `npm test` will never collect.

    Measured on run-2b5def74, which completed with two test directories -
    `tests/` and `simple-to-do-list-app/tests/` - holding three files of the
    same names, reconciled by nothing and counted twice by the reviewer.
    """
    from app.tools.repository import PROJECT_MARKER

    (repo_root / "todo-app").mkdir()
    (repo_root / PROJECT_MARKER).write_text("todo-app", encoding="utf-8")

    with pytest.raises(RepositoryToolError, match="its test runner only collects"):
        write_approved_artifact(repo_root, "tests/logic.test.js", "// suite")


def test_the_refusal_names_where_it_should_go(repo_root: Path) -> None:
    from app.tools.repository import PROJECT_MARKER

    (repo_root / "todo-app").mkdir()
    (repo_root / PROJECT_MARKER).write_text("todo-app", encoding="utf-8")

    with pytest.raises(RepositoryToolError) as caught:
        write_approved_artifact(repo_root, "tests/logic.test.js", "// suite")

    assert "todo-app/tests/logic.test.js" in str(caught.value)


def test_a_test_inside_the_project_is_allowed(repo_root: Path) -> None:
    from app.tools.repository import PROJECT_MARKER

    (repo_root / "todo-app").mkdir()
    (repo_root / PROJECT_MARKER).write_text("todo-app", encoding="utf-8")

    result = write_approved_artifact(repo_root, "todo-app/tests/logic.test.js", "// suite")

    assert result["path"] == "todo-app/tests/logic.test.js"


def test_before_a_project_is_pinned_a_test_has_nowhere_better_to_go(repo_root: Path) -> None:
    """The first stage to write one cannot be told to put it somewhere that
    does not exist yet."""
    result = write_approved_artifact(repo_root, "tests/logic.test.js", "// suite")

    assert result["path"] == "tests/logic.test.js"


def test_a_document_is_not_a_test(repo_root: Path) -> None:
    from app.tools.repository import PROJECT_MARKER

    (repo_root / "todo-app").mkdir()
    (repo_root / PROJECT_MARKER).write_text("todo-app", encoding="utf-8")

    result = write_approved_artifact(repo_root, "docs/plan.md", "# Plan")

    assert result["path"] == "docs/plan.md"


# --- one project directory, and it is not the stylesheets ------------------


def test_a_stylesheet_folder_never_becomes_the_project(repo_root: Path) -> None:
    """Measured on run-7b11cb67: the UI specialist wrote `css/style.css` before
    anything else, the pin took `css`, and every later stage would have built
    the application inside a directory named after its stylesheets."""
    from app.tools.repository import pinned_project_directory

    write_approved_artifact(repo_root, "todo-app/index.html", "<html>")
    write_approved_artifact(repo_root, "todo-app/css/style.css", "body{}")

    assert pinned_project_directory(repo_root) == "todo-app"


@pytest.mark.parametrize(
    "folder", ["css", "js", "assets", "static", "public", "img", "styles", "scripts"]
)
def test_conventional_asset_folders_are_not_projects(folder: str) -> None:
    from app.tools.repository import _is_project_directory

    assert not _is_project_directory(folder)


def test_a_source_file_at_the_workspace_root_is_refused(repo_root: Path) -> None:
    """Every prompt says to build inside one top-level directory; until now
    nothing enforced it, and the product ended up scattered."""
    with pytest.raises(RepositoryToolError, match="one top-level"):
        write_approved_artifact(repo_root, "index.html", "<html>")


def test_the_refusal_shows_the_shape_of_the_fix(repo_root: Path) -> None:
    with pytest.raises(RepositoryToolError) as caught:
        write_approved_artifact(repo_root, "app.js", "// app")

    message = str(caught.value)
    assert "lowercase-with-hyphens" in message
    assert "my-app/app.js" in message


def test_a_source_file_in_an_asset_folder_at_the_root_is_refused(repo_root: Path) -> None:
    with pytest.raises(RepositoryToolError, match="one top-level"):
        write_approved_artifact(repo_root, "css/style.css", "body{}")


def test_documents_are_unaffected(repo_root: Path) -> None:
    """`docs/` has its own rule and its own reason."""
    assert write_approved_artifact(repo_root, "docs/plan.md", "# Plan")["path"] == "docs/plan.md"


def test_a_project_directory_is_exactly_what_is_wanted(repo_root: Path) -> None:
    from app.tools.repository import pinned_project_directory

    result = write_approved_artifact(repo_root, "todo-app/index.html", "<html>")

    assert result["path"] == "todo-app/index.html"
    assert pinned_project_directory(repo_root) == "todo-app"


def test_once_pinned_the_rule_never_contradicts_the_pin(repo_root: Path) -> None:
    """A run that already has a project must not be told it has none."""
    write_approved_artifact(repo_root, "todo-app/index.html", "<html>")

    assert write_approved_artifact(repo_root, "todo-app/css/a.css", "body{}")["path"]


def test_src_is_where_a_project_keeps_its_source_not_a_project(repo_root: Path) -> None:
    """Left off the list it pinned as readily as `css` did."""
    with pytest.raises(RepositoryToolError, match="one top-level"):
        write_approved_artifact(repo_root, "src/index.html", "<html>")


def test_a_source_file_at_the_root_is_refused_after_a_project_exists(repo_root: Path) -> None:
    """The other half of the same mistake: on run-7b11cb67 `index.html` sat at
    the workspace root beside the `css/` that had been pinned, belonging to
    neither. Guarding only the unpinned case left that open."""
    write_approved_artifact(repo_root, "todo-app/index.html", "<html>")

    with pytest.raises(RepositoryToolError, match="source files belong inside it"):
        write_approved_artifact(repo_root, "app.js", "// app")


def test_that_refusal_names_the_project_and_the_path(repo_root: Path) -> None:
    write_approved_artifact(repo_root, "todo-app/index.html", "<html>")

    with pytest.raises(RepositoryToolError) as caught:
        write_approved_artifact(repo_root, "app.js", "// app")

    assert "todo-app/app.js" in str(caught.value)


def test_an_asset_folder_inside_the_project_is_untouched(repo_root: Path) -> None:
    write_approved_artifact(repo_root, "todo-app/index.html", "<html>")

    result = write_approved_artifact(repo_root, "todo-app/css/style.css", "body{}")

    assert result["path"] == "todo-app/css/style.css"


def test_documents_stay_out_of_it_either_way(repo_root: Path) -> None:
    write_approved_artifact(repo_root, "todo-app/index.html", "<html>")

    assert write_approved_artifact(repo_root, "docs/plan.md", "# Plan")["path"] == "docs/plan.md"


# --- the host path, written verbatim --------------------------------------


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        # The host path exactly as a prompt or tool result quoted it.
        ("/ROOT/index.html", "index.html"),
        # Refused once, the agent drops the leading slash and tries again. That
        # is a real path inside the workspace, so it used to be created - a
        # mirror of the host layout nested inside the workspace it describes.
        ("app/data/workspaces/RUNDIR/index.html", "index.html"),
        # Refused again, it drops another component.
        ("data/workspaces/RUNDIR/index.html", "index.html"),
        ("workspaces/RUNDIR/todo/app.js", "todo/app.js"),
        ("RUNDIR/index.html", "index.html"),
        # Anchored on the workspace directory's own name, so a project with a
        # real `data/` folder of its own is untouched.
        ("todo-app/data/config.json", "todo-app/data/config.json"),
        ("data/seed.json", "data/seed.json"),
        ("index.html", "index.html"),
        ("docs/plan.md", "docs/plan.md"),
    ],
)
def test_a_host_path_resolves_to_the_workspace(given: str, expected: str) -> None:
    """Measured on run-2f252e4e, which created
    `app/data/workspaces/<run>/index.html` inside its own workspace and pinned
    `app` as the project directory along the way."""
    from pathlib import Path

    from app.tools.repository import _repo_relative_path

    root = Path("/app/data/workspaces/t12-run-abc")
    given = given.replace("/ROOT/", f"{root}/").replace("RUNDIR", root.name)

    assert str(_repo_relative_path(root, given)) == expected


def test_the_host_path_does_not_become_a_project_directory(repo_root: Path) -> None:
    """It pinned `app`, from `/app/data/...`, and every later stage would have
    built into it."""
    from app.tools.repository import pinned_project_directory

    write_approved_artifact(repo_root, "todo-app/index.html", "<html>")
    write_approved_artifact(repo_root, f"{repo_root}/todo-app/app.js", "// app")

    assert pinned_project_directory(repo_root) == "todo-app"
    assert (repo_root / "todo-app/app.js").exists()


# --- a product with more than one tier ------------------------------------


def test_a_backend_folder_at_the_root_cannot_be_the_project(repo_root: Path) -> None:
    """`brief_medium` asks for a backend and a frontend. Whichever was written
    first was pinned as the whole project, and the other was then refused as a
    second one - so the run could never write both."""
    with pytest.raises(RepositoryToolError, match="one top-level"):
        write_approved_artifact(repo_root, "backend/main.py", "# api")


def test_one_project_can_hold_both_tiers(repo_root: Path) -> None:
    from app.tools.repository import pinned_project_directory

    write_approved_artifact(repo_root, "task-dashboard/backend/main.py", "# api")
    write_approved_artifact(repo_root, "task-dashboard/frontend/App.jsx", "// ui")
    write_approved_artifact(repo_root, "task-dashboard/api/routes.py", "# routes")

    assert pinned_project_directory(repo_root) == "task-dashboard"
    assert (repo_root / "task-dashboard/frontend/App.jsx").exists()


@pytest.mark.parametrize(
    "folder",
    ["backend", "frontend", "client", "server", "api", "web", "ui", "services",
     "apps", "packages"],
)
def test_a_tier_is_not_a_project(folder: str) -> None:
    """Each is a part of a product, never the product."""
    from app.tools.repository import _is_project_directory

    assert not _is_project_directory(folder)


def test_a_real_product_name_still_is_one() -> None:
    from app.tools.repository import _is_project_directory

    for name in ("task-dashboard", "todo-app", "task-manager", "simple-to-do-list-app"):
        assert _is_project_directory(name), name


def test_an_edit_that_would_change_nothing_is_refused(repo_root: Path) -> None:
    """The failure that killed run-b61df271.

    Its `specialist_backend_3` sent three edits to `to-do-app/app.js` whose
    `find` and `replace` were the same 848 characters. Each was answered with
    `"status": "edited"`. The agent re-read the file between them, saw the same
    73 lines every time, concluded the edit had failed, and sent it again - the
    fifth identical request tripped the run-level loop guard and the run failed.

    Reporting "edited" for a no-op is a lie the agent cannot see through, and
    re-reading is exactly the right thing for it to do about a suspect write.
    """
    write_approved_artifact(repo_root, "docs/spec.md", "status: OPEN\n")

    with pytest.raises(RepositoryToolError, match="would leave"):
        edit_approved_artifact(repo_root, "docs/spec.md", "status: OPEN", "status: OPEN")

    assert (repo_root / "docs" / "spec.md").read_text(encoding="utf-8") == "status: OPEN\n"


def test_the_refusal_says_the_file_is_not_broken(repo_root: Path) -> None:
    """The agent's next move is the whole point of the message.

    It had been looping because it believed the file still needed changing.
    Naming both ways out - make `replace` differ, or stop editing and move on -
    is what the loop needs to hear.
    """
    write_approved_artifact(repo_root, "docs/spec.md", "a\nb\nc\n")

    with pytest.raises(RepositoryToolError) as caught:
        edit_approved_artifact(repo_root, "docs/spec.md", "b\n", "b\n")

    message = str(caught.value)
    assert "still has 3 lines" in message
    assert "Nothing is wrong with the file or the tool" in message
    assert "stop editing it and move on" in message


def test_a_no_op_arriving_through_a_forgiving_match_is_also_refused(repo_root: Path) -> None:
    """The reason the check sits on the content, not on the arguments.

    The fallbacks that forgive line numbers, JSON escaping and indentation each
    replace a *candidate* rather than `find`, so comparing the two arguments
    would let a no-op through any of them.
    """
    write_approved_artifact(repo_root, "docs/spec.md", "alpha\nbeta\ngamma\n")

    # `find` carries the line-number prefix that `read_file` prints; the text
    # it actually matches is "beta", and `replace` is that same text.
    with pytest.raises(RepositoryToolError, match="would leave"):
        edit_approved_artifact(repo_root, "docs/spec.md", "2\tbeta", "beta")

    assert (repo_root / "docs" / "spec.md").read_text(encoding="utf-8") == "alpha\nbeta\ngamma\n"


def test_a_no_op_edit_does_not_touch_the_file(repo_root: Path) -> None:
    """A rewrite with identical bytes still moves mtime.

    The repeat-read notice keys on size and mtime, so a no-op that rewrote the
    file would clear the very notice that tells the agent it is going in
    circles - which is how the loop stayed invisible for five rounds.
    """
    write_approved_artifact(repo_root, "docs/spec.md", "keep\n")
    target = repo_root / "docs" / "spec.md"
    before = target.stat().st_mtime_ns

    with pytest.raises(RepositoryToolError):
        edit_approved_artifact(repo_root, "docs/spec.md", "keep\n", "keep\n")

    assert target.stat().st_mtime_ns == before


def test_a_real_edit_still_succeeds(repo_root: Path) -> None:
    write_approved_artifact(repo_root, "docs/spec.md", "status: OPEN\n")

    result = edit_approved_artifact(repo_root, "docs/spec.md", "status: OPEN", "status: CLOSED")

    assert result["status"] == "edited"
    assert (repo_root / "docs" / "spec.md").read_text(encoding="utf-8") == "status: CLOSED\n"


def _js_lines(count: int) -> str:
    """`count` lines of valid JavaScript.

    `"const x = 1;\\n" * 900` was the old filler and is a real syntax error -
    `Identifier 'x' has already been declared` - which `node --check` now
    refuses, correctly. Line budgets need lines, not a broken file.
    """
    return "".join(f"const x{index} = {index};\n" for index in range(count))


def _project_with_a_budget(root: Path, app_lines: int) -> None:
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs/product_intake.md").write_text(
        "Total source code stays within the 500-line limit.\n" * 3, encoding="utf-8"
    )
    write_approved_artifact(
        root, "app/index.html", '<html><script src="app.js"></script></html>\n'
    )
    return write_approved_artifact(root, "app/app.js", _js_lines(app_lines))


def test_a_write_that_goes_over_the_declared_budget_says_so(repo_root: Path) -> None:
    """The budget was only ever checked at review time, which costs a cycle.

    run-fa7b7286 spent three milestone cycles on it and went the wrong way: the
    review that first raised it counted 671 lines against a stated 500, and the
    next cycle produced 859. The cap is in the brief, the intake and the
    specification, and was exceeded anyway - the corrections that work on this
    model arrive in the result of the call that caused the problem.
    """
    result = _project_with_a_budget(repo_root, 600)

    assert result["status"] == "written"
    assert "limit of 500 lines" in result["note"]
    assert re.search(r"holds \d+ - \d+ over", result["note"])
    # It must name where the weight is, or "you are over" is not actionable.
    assert "app/app.js" in result["note"]


def test_a_project_inside_its_budget_is_not_nagged(repo_root: Path) -> None:
    result = _project_with_a_budget(repo_root, 50)

    assert "note" not in result


def test_a_project_that_declares_no_budget_is_not_judged(repo_root: Path) -> None:
    """The number comes from the project's own documents or not at all."""
    write_approved_artifact(
        repo_root, "app/index.html", '<html><script src="app.js"></script></html>\n'
    )
    result = write_approved_artifact(repo_root, "app/app.js", _js_lines(900))

    assert "note" not in result


def test_writing_a_document_is_not_told_about_the_code_budget(repo_root: Path) -> None:
    """Writing prose does not move the number, and a note there reads as a
    complaint about the wrong file."""
    _project_with_a_budget(repo_root, 600)

    result = write_approved_artifact(repo_root, "docs/notes.md", "# Notes\n")

    assert "note" not in result


def test_the_write_still_succeeds_when_over_budget(repo_root: Path) -> None:
    """It never refuses. A write that fails leaves the agent nowhere to put its
    work, and the cap is the project's stated preference, not a sandbox rule."""
    _project_with_a_budget(repo_root, 600)

    assert (repo_root / "app/app.js").read_text(encoding="utf-8").count("\n") == 600


def test_an_edit_that_goes_over_the_budget_says_so_too(repo_root: Path) -> None:
    (repo_root / "docs").mkdir(exist_ok=True)
    (repo_root / "docs/product_intake.md").write_text(
        "Total source code stays within the 500-line limit.\n" * 3, encoding="utf-8"
    )
    write_approved_artifact(
        repo_root, "app/index.html", '<html><script src="app.js"></script></html>\n'
    )
    write_approved_artifact(repo_root, "app/app.js", "const only = 'here';\n")

    result = edit_approved_artifact(
        repo_root, "app/app.js", "const only = 'here';\n", _js_lines(600)
    )

    assert result["status"] == "edited"
    assert "limit of 500 lines" in result["note"]


def test_the_budget_note_does_not_count_the_test_suite(repo_root: Path) -> None:
    """The bug the first version of this note shipped with.

    `_measure_sizes` splits application from tests for a stated reason - a
    brief capping "lines of code" almost never means the test suite - and
    `_over_the_declared_budget` sums only the application half. The note summed
    every entry instead, so on run-44653bd2 it would have said 1,533 where the
    reviewer says 628, because one 797-line `Task.test.mjs` was in the total.

    Warning an agent it is 1,033 over when it is 128 over does not merely
    overstate. The cheapest way to close a gap that size is to delete tests.
    """
    (repo_root / "docs").mkdir(exist_ok=True)
    (repo_root / "docs/product_intake.md").write_text(
        "Total source code stays within the 500-line limit.\n" * 3, encoding="utf-8"
    )
    write_approved_artifact(
        repo_root, "app/index.html", '<html><script src="app.js"></script></html>\n'
    )
    write_approved_artifact(repo_root, "app/app.js", _js_lines(300))

    result = write_approved_artifact(repo_root, "app/app.test.mjs", "test(1);\n" * 900)

    # This test is about the *budget* note specifically. The file also earns
    # the "imports nothing from the project" note, which is correct - it is
    # 900 bare `test(1);` calls - and is a different check.
    assert "limit of 500 lines" not in (result.get("note") or "")
    assert "over" not in (result.get("note") or "")


def test_the_note_and_the_reviewer_report_the_same_number(repo_root: Path) -> None:
    """They are judged on one number, so they must be warned about that one."""
    from app.analysis.integration_checks import (
        _orphans_quietly,
        _over_the_declared_budget,
        _source_files,
        budget_note_for_a_write,
    )

    (repo_root / "docs").mkdir(exist_ok=True)
    (repo_root / "docs/product_intake.md").write_text(
        "Total source code stays within the 500-line limit.\n" * 3, encoding="utf-8"
    )
    write_approved_artifact(
        repo_root, "app/index.html", '<html><script src="app.js"></script></html>\n'
    )
    write_approved_artifact(repo_root, "app/app.js", _js_lines(700))
    write_approved_artifact(repo_root, "app/app.test.mjs", "test(1);\n" * 900)

    note = budget_note_for_a_write(repo_root, "app/app.js")
    files = _source_files(Path(repo_root))
    findings = _over_the_declared_budget(files, Path(repo_root), _orphans_quietly(files, Path(repo_root)))

    assert note and findings
    total = re.search(r"it now holds ([\d,]+)", note).group(1).replace(",", "")
    assert f"{int(total):,} lines of code" in findings[0]


def test_a_write_carrying_the_models_own_tokens_is_refused(repo_root: Path) -> None:
    """The failure that killed run-44653bd2, on North-Mini-Code-1.0.

    `Task.test.mjs` was written ending `");<|END_THINKING|><|START_ACTION|>[{`
    - a syntax error on line 963 that broke the entire 963-line suite. A model
    does not read its own control tokens as foreign text, so `defect_fix_1_0`
    spent the rest of the run editing `TaskManager.js`, which was never the
    broken file, and the run died on the repeat guard at 1,098 events.

    Content carrying these is not a document with a formatting problem. It is a
    turn that was cut off mid-way, so what would be saved is a truncated
    transcript rather than the file the model meant to write.
    """
    with pytest.raises(RepositoryToolError, match="your own special tokens"):
        write_approved_artifact(
            repo_root, "app/a.test.mjs", '});\n\n");<|END_THINKING|><|START_ACTION|>[{'
        )

    assert not (repo_root / "app/a.test.mjs").exists()


def test_every_family_of_control_token_is_caught(repo_root: Path) -> None:
    for marker in ("<|im_start|>", "<|im_end|>", "<|eot_id|>", "<|endoftext|>", "<|START_THINKING|>"):
        with pytest.raises(RepositoryToolError, match="your own special tokens"):
            write_approved_artifact(repo_root, "app/x.js", f"const a = 1;\n{marker}\n")


def test_ordinary_code_that_merely_looks_similar_is_written(repo_root: Path) -> None:
    """The pattern has to be the full `<|name|>` spelling, or a comparison
    operator beside a pipe would be refused as a control token.

    Valid JavaScript, because `node --check` refuses the rest - and a fixture
    that is not the language it claims to be tests nothing about this rule.
    """
    write_approved_artifact(
        repo_root, "app/b.js", "const c = a < b | 1;\nconst d = x || y;\n"
    )

    assert (repo_root / "app/b.js").is_file()


def test_an_edit_cannot_smuggle_one_in_either(repo_root: Path) -> None:
    write_approved_artifact(repo_root, "app/c.js", "const only = 1;\n")

    with pytest.raises(RepositoryToolError, match="your own special tokens"):
        edit_approved_artifact(
            repo_root, "app/c.js", "const only = 1;\n", "const only = 2;<|im_end|>\n"
        )

    assert (repo_root / "app/c.js").read_text(encoding="utf-8") == "const only = 1;\n"


def test_the_refusal_says_nothing_was_written(repo_root: Path) -> None:
    """An agent that thinks a partial file landed will try to patch it."""
    with pytest.raises(RepositoryToolError) as caught:
        write_approved_artifact(repo_root, "app/d.js", "x<|eot_id|>")

    message = str(caught.value)
    assert "Nothing was written" in message
    assert "Send the file again, complete" in message


def test_an_ambiguous_edit_says_where_the_copies_are(repo_root: Path) -> None:
    """"Include more surrounding text" is advice; line numbers are information.

    Measured on run-e37a2bd8: 7 of 24 `edit_artifact` failures were ambiguity,
    on a test file whose blocks the model had duplicated. It cannot see where
    the copies are, so it guesses at more context and collides with the other
    copy again.
    """
    write_approved_artifact(
        repo_root, "p/a.mjs",
        "run(() => {\n  loadTasks();\n  assert(ok);\n});\n"
        "run(() => {\n  loadTasks();\n  assert(ok);\n});\n",
    )

    with pytest.raises(RepositoryToolError) as caught:
        edit_approved_artifact(repo_root, "p/a.mjs", "  assert(ok);\n", "  assert(better);\n")

    message = str(caught.value)
    assert "lines 3 and 7" in message
    assert "whichever of these surrounding lines differs" in message
    # And the way out that cannot be ambiguous, named with the numbers in hand.
    assert "replace_lines" in message
    # And the surroundings themselves, which is what makes it actable.
    assert "the copy at line 3:" in message
    assert "loadTasks();" in message


def test_three_copies_are_all_listed(repo_root: Path) -> None:
    write_approved_artifact(repo_root, "p/b.mjs", "x();\ny();\nx();\nz();\nx();\n")

    with pytest.raises(RepositoryToolError, match=r"lines 1, 3 and 5"):
        edit_approved_artifact(repo_root, "p/b.mjs", "x();\n", "w();\n")


def test_a_failed_edit_on_a_short_file_is_shown_the_whole_file(repo_root: Path) -> None:
    """The fuzzy match refuses to guess below 0.6, which strands a small file.

    Measured on run-36eb1260: `specialist_backend_2` edited a five-line
    `test-json.cjs`, missed, and was told only "Read the section first and copy
    the passage from what you read". It read the file twice more and missed
    twice more, and the run was stopped as a loop at 1,137 events. The five
    lines it needed were available every time.

    Refusing to guess is right for a large file - a "closest" line sharing one
    keyword sends the agent somewhere unrelated - but a five-line file has
    nowhere unrelated to send it.
    """
    write_approved_artifact(
        repo_root, "p/test-json.cjs",
        "const fs = require('fs');\ntry {\n  const d = JSON.parse(x);\n} catch (e) {}\n",
    )

    with pytest.raises(RepositoryToolError) as caught:
        edit_approved_artifact(
            repo_root, "p/test-json.cjs", "const totally = 'different thing';\n", "x"
        )

    message = str(caught.value)
    assert "This is the entire file:" in message
    for line in ("const fs = require('fs');", "} catch (e) {}"):
        assert line in message
    # It must not claim a marker it did not print.
    assert "marks the nearest line" not in message
    assert "Read the section first" not in message


def test_a_large_file_still_gets_the_nearest_passage(repo_root: Path) -> None:
    """Quoting a 900-line file at an agent is not help, it is a wall of text."""
    body = "\n".join(f"const line{i} = {i};" for i in range(80)) + "\n"
    write_approved_artifact(repo_root, "p/big.cjs", body)

    with pytest.raises(RepositoryToolError) as caught:
        edit_approved_artifact(repo_root, "p/big.cjs", "const line40 = 99;\n", "x")

    message = str(caught.value)
    assert "This is the entire file" not in message
    assert "const line0 = 0;" not in message
    # And it points at the line that is actually nearest. `max` over
    # (ratio, index) broke ties toward the highest index, so every line here
    # scored alike and the pointer landed on line 50.
    assert "(line 41)" in message
    assert "const line40 = 40;" in message
