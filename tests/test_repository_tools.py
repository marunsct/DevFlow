"""Tests for the safe repository inspection tool layer.

The core idea is simple: tools may inspect a repository, but only inside a
trusted boundary. These tests make that contract explicit by proving that reads,
searches, and writes stay inside the repository or approved artifact directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.repository import (
    RepositoryToolError,
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
