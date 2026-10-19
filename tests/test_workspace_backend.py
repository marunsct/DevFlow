"""The workspace an agent sees, without the machinery that runs it.

The sandbox points HOME at `.agent-home` inside the workspace so package caches
land per-run. In container mode that is not a choice - only the workspace is
mounted, so anything a command writes must be inside it.

Measured on one run: 42 tool results across ten stages carried
`.agent-home`, every `ls /` opened with it, and one `npm install` left 26 cache
blobs with sha512 filenames. `list_repository_files` skipped it; `ls`, `glob`
and `grep` come from the deep-agent backend and did not.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agents.workspace_backend import READ_WITHHELD_MARKER, WorkspaceBackend, _is_hidden, _path_of


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    cache = tmp_path / ".agent-home/.npm/_cacache"
    cache.mkdir(parents=True)
    (cache / "sha512blob").write_text("cached\n", encoding="utf-8")
    (tmp_path / "proj").mkdir()
    (tmp_path / "proj/app.js").write_text("function createTask(){}\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules/dep.js").write_text("//\n", encoding="utf-8")
    return tmp_path


def _backend(workspace: Path) -> WorkspaceBackend:
    return WorkspaceBackend(root_dir=str(workspace), virtual_mode=True)


def test_the_run_s_own_cache_is_not_listed(workspace: Path) -> None:
    entries = _backend(workspace).ls("/").entries

    assert not any("agent-home" in _path_of(e) for e in entries)
    assert any("proj" in _path_of(e) for e in entries)


def test_glob_does_not_reach_into_it(workspace: Path) -> None:
    matches = _backend(workspace).glob("**/*").matches

    assert not any("agent-home" in _path_of(m) for m in matches)
    assert any("app.js" in _path_of(m) for m in matches)


def test_dependencies_are_hidden_by_the_same_list(workspace: Path) -> None:
    """One list, so the repository tools and the agent's tools cannot drift."""
    matches = _backend(workspace).glob("**/*").matches

    assert not any("node_modules" in _path_of(m) for m in matches)


def test_the_hidden_list_comes_from_the_repository_tools() -> None:
    import inspect

    from app.agents import workspace_backend

    source = inspect.getsource(workspace_backend)

    assert "from app.tools.repository import IGNORED_DIRECTORIES" in source


def test_reading_a_hidden_path_still_works(workspace: Path) -> None:
    """An agent that names a path inside one of these has a reason, and a read
    that silently failed would be a worse surprise than a quiet listing."""
    result = _backend(workspace).read("/.agent-home/.npm/_cacache/sha512blob")

    assert "cached" in str(getattr(result, "content", result))


def test_the_directory_is_still_there_for_the_sandbox(workspace: Path) -> None:
    """It is the agent's view that changes. Hiding it from a listing must not
    mean a command cannot write to it."""
    _backend(workspace).ls("/")

    assert (workspace / ".agent-home/.npm/_cacache/sha512blob").exists()


@pytest.mark.parametrize(
    ("entry", "hidden"),
    [
        ({"path": "/.agent-home/x", "is_dir": False}, True),
        ({"path": "/proj/app.js", "is_dir": False}, False),
        ({"path": "/proj/build/out.js", "is_dir": False}, True),
        # A file merely *named* like a hidden directory is not one.
        ({"path": "/proj/build.js", "is_dir": False}, False),
        ("/node_modules/dep.js", True),
    ],
)
def test_an_entry_is_judged_by_its_path_not_its_repr(entry, hidden) -> None:
    """Entries arrive as dicts, objects or strings. Matching the string form of
    a whole dict would work by accident and break on the first entry whose
    other fields happened to contain a directory name."""
    assert _is_hidden(entry) is hidden


def test_role_agents_use_it() -> None:
    import inspect

    from app.agents import role_agent

    source = inspect.getsource(role_agent._workspace_filesystem_middleware)

    assert "WorkspaceBackend(" in source
    assert "FilesystemBackend(" not in source


# --- "not found" that says where it actually is --------------------------


import tempfile
from pathlib import Path as _Path

import pytest

from app.agents.workspace_backend import WorkspaceBackend


@pytest.fixture
def backend(tmp_path):
    (tmp_path / "todo-app").mkdir()
    (tmp_path / "todo-app/app.js").write_text("export function a(){}\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/plan.md").write_text("# plan\n", encoding="utf-8")
    return WorkspaceBackend(str(tmp_path), virtual_mode=True)


def test_an_invented_prefix_is_served_not_refused(backend) -> None:
    """The guesses agents actually make, from the stored runs.

    On one run - the run that died of gate exhaustion - 72 reads failed
    and 56 of them (77%) named a file that was in the workspace under a
    different path. The error named only the path the agent had invented, so
    it invented another.

    Naming the real path fixed the second invention. It did not fix the cost:
    the stage still spent a model call re-asking with the path it had just been
    handed. Measured again on 2026-09-21, `technical_lead` did exactly that four
    times over `/home/user/workspace/task-manager/...`.

    So the read is now served. This supersedes the older assertion that these
    return an error - the hint was right and a hint is not what the stage
    needed. `_the_one_path_it_meant` is stricter than the hint it replaces: the
    basename must be unique in the workspace AND the path asked for must end
    with the workspace path, so the request has to agree about the directory
    too. `test_a_project_file_named_at_the_root_is_located` below covers the
    case that still gets a hint, and still does.
    """
    for invented in (
        "/home/user/docs/plan.md",
        "/workspace/docs/plan.md",
        "/app/data/workspaces/t1/docs/plan.md",
    ):
        result = backend.read(invented)
        assert not getattr(result, "error", None), (
            f"{invented} should have been served, not refused"
        )
        content = (getattr(result, "file_data", None) or {}).get("content", "")
        assert "# plan" in content, f"{invented} returned no content"


def test_a_project_file_named_at_the_root_is_located(backend) -> None:
    """`/app.js` when the file is `todo-app/app.js` - one run made this
    call 21 times and one run 87 times."""
    assert "/todo-app/app.js" in backend.read("/app.js").error


def test_a_missing_directory_is_located_too(tmp_path) -> None:
    """`ls` misses directory names, which have no extension to match on:
    One run asked for `/simple-to-do-list-app` four times."""
    (tmp_path / "nested/todo-app").mkdir(parents=True)
    backend = WorkspaceBackend(str(tmp_path), virtual_mode=True)

    assert "/nested/todo-app" in backend.ls("/todo-app").error


def test_a_file_that_is_nowhere_gets_no_suggestion(backend) -> None:
    """A genuine typo must not be answered with a guess."""
    error = backend.read("/nope.js").error

    assert "not found" in error
    assert "There is a file" not in error


def test_a_successful_read_is_untouched(backend) -> None:
    result = backend.read("/todo-app/app.js")

    assert not getattr(result, "error", None)


def test_the_agent_s_own_cache_is_never_suggested(tmp_path) -> None:
    """`.agent-home` is hidden from listings; suggesting a path inside it would
    put it back."""
    cache = tmp_path / ".agent-home/.npm/_cacache"
    cache.mkdir(parents=True)
    (cache / "plan.md").write_text("junk\n", encoding="utf-8")
    backend = WorkspaceBackend(str(tmp_path), virtual_mode=True)

    error = backend.read("/docs/plan.md").error

    assert "agent-home" not in error


# --- reading the same unchanged file over and over -----------------------


def test_an_unchanged_repeat_read_is_told_so(backend) -> None:
    """Measured on one run's `specialist_backend_1`: 39 tool calls, 17 of
    them the same `read_file` of `app.js` at the same range, in runs of six,
    five and four, two to three seconds apart, with no write between them."""
    first = backend.read("/todo-app/app.js")
    second = backend.read("/todo-app/app.js")
    third = backend.read("/todo-app/app.js")

    assert "same bytes" not in first.file_data["content"]
    assert "same bytes" not in second.file_data["content"]
    assert "same bytes" in third.file_data["content"]


def test_the_content_comes_back_while_the_note_is_only_a_note(backend) -> None:
    """Up to the escalation threshold the note is an addition, never a
    replacement: a model that had genuinely lost the text must get it back."""
    from app.agents.workspace_backend import READS_BEFORE_WITHHOLDING

    for _ in range(READS_BEFORE_WITHHOLDING):
        result = backend.read("/todo-app/app.js")
        assert "export function a" in result.file_data["content"]


def test_the_bytes_are_withheld_once_the_note_has_been_ignored(backend) -> None:
    """Hint, note, refuse - the escalation this codebase arrives at everywhere.

    Measured on one run's `specialist_backend_1`: eleven byte-identical
    reads of `/docs/architecture_review.md` in one stage, each answered with a
    note saying so and each followed by another. One run did seventeen of
    `app.js`.
    """
    from app.agents.workspace_backend import READS_BEFORE_WITHHOLDING

    # Long enough to be worth withholding. A file of a few lines is shown in
    # full even at this rung - see the test below - because withholding six
    # lines saves nothing and costs clarity.
    big = "\n".join(f"export function fn{n}() {{ return {n}; }}" for n in range(40))
    target = Path(backend._resolve_path("/todo-app/big.js"))
    target.write_text(big + "\n", encoding="utf-8")

    for _ in range(READS_BEFORE_WITHHOLDING):
        backend.read("/todo-app/big.js")

    content = backend.read("/todo-app/big.js").file_data["content"]

    assert "export function fn20" not in content, "repeating the bytes is the cost"
    assert "you already have it" in content
    assert "different line range" in content, "a model that truly lost it needs a way back"
    # And an anchor, for a stage whose earlier results were compacted away.
    assert "40 lines, unchanged" in content
    assert "export function fn0" in content, "the first lines, so it knows which file"


def test_a_short_file_is_shown_in_full_even_when_withheld(backend) -> None:
    """Withholding six lines saves nothing and costs the stage its anchor."""
    from app.agents.workspace_backend import READS_BEFORE_WITHHOLDING

    for _ in range(READS_BEFORE_WITHHOLDING + 1):
        content = backend.read("/todo-app/app.js").file_data["content"]

    assert "export function a" in content


def test_a_range_it_has_not_seen_still_returns_content(tmp_path) -> None:
    """The escape that a loop does not take.

    Withholding applies only to a request for the same bytes of an unchanged
    file, so asking for a part it has not been served still works.
    """
    from app.agents.workspace_backend import READS_BEFORE_WITHHOLDING

    lines = "".join(f"const line{i} = {i};\n" for i in range(200))
    (tmp_path / "big.js").write_text(lines, encoding="utf-8")
    backend = WorkspaceBackend(str(tmp_path), virtual_mode=True)

    for _ in range(READS_BEFORE_WITHHOLDING + 1):
        backend.read("/big.js", offset=0, limit=20)

    other = backend.read("/big.js", offset=100, limit=20)

    assert "const line100" in other.file_data["content"]


def test_an_edit_clears_the_count(tmp_path) -> None:
    """Keyed on the CONTENT, so a specialist that edits and reads back gets
    different bytes and no note - no write-tracking needed."""
    (tmp_path / "app.js").write_text("export function a(){}\n", encoding="utf-8")
    backend = WorkspaceBackend(str(tmp_path), virtual_mode=True)

    backend.read("/app.js")
    backend.read("/app.js")
    assert "same bytes" in backend.read("/app.js").file_data["content"]

    (tmp_path / "app.js").write_text("export function a(){}\nexport function b(){}\n", encoding="utf-8")

    assert "same bytes" not in backend.read("/app.js").file_data["content"]
    assert "same bytes" not in backend.read("/app.js").file_data["content"]
    assert "same bytes" in backend.read("/app.js").file_data["content"]


def test_the_text_is_read_from_the_field_that_holds_it(backend) -> None:
    """The first version of this read `result.content`, which does not exist.

    It failed safely and did nothing, so every check that asked "did it error?"
    passed while the feature was inert. A silent no-op is the quietest kind of
    broken and the one this codebase keeps finding in its own checks.
    """
    result = backend.read("/todo-app/app.js")

    assert getattr(result, "content", None) is None
    assert isinstance(result.file_data, dict)
    assert "export function a" in result.file_data["content"]


def test_different_ranges_of_one_file_are_counted_apart(tmp_path) -> None:
    """Paging through a long file is progress, not repetition."""
    (tmp_path / "big.js").write_text("\n".join(f"line {i}" for i in range(500)), encoding="utf-8")
    backend = WorkspaceBackend(str(tmp_path), virtual_mode=True)

    for offset in (0, 100, 200, 300):
        result = backend.read("/big.js", offset=offset, limit=100)
        assert "same bytes" not in result.file_data["content"]


# --- the same lines again, under different arguments ---------------------


def test_a_range_already_served_is_told_so(tmp_path) -> None:
    """The exact sequence from one run's `specialist_ui_ux_0`, reading a
    984-line index.html that had not changed since it was written:

        offset=  0 limit=100   100 new lines
        offset=310 limit= 80    80 new
        offset=320 limit=100    30 new,  70 already read
        offset=320 limit= 50     0 new,  50 already read
        offset=320 limit=100     0 new, 100 already read   <- 20 minutes later

    Five reads, 220 line-reads of already-seen content against 210 distinct
    lines. Finding 59 cannot catch it: the arguments differ every time.
    """
    (tmp_path / "index.html").write_text(
        "\n".join(f"line {i}" for i in range(1, 985)), encoding="utf-8"
    )
    backend = WorkspaceBackend(str(tmp_path), virtual_mode=True)

    def seen(offset: int, limit: int) -> bool:
        result = backend.read("/index.html", offset=offset, limit=limit)
        # The same window again is answered with where its lines are (Initiative AQ).
        content = result.file_data["content"]
        return "already read lines" in content or READ_WITHHELD_MARKER in content

    assert not seen(0, 100)
    assert not seen(310, 80)
    assert not seen(320, 100)   # 30 lines were still new
    assert seen(320, 50)        # nothing new
    assert seen(320, 100)       # nothing new


def test_a_write_clears_what_was_seen(tmp_path) -> None:
    """Keyed on the file's size and mtime, so an edit resets the record and a
    specialist that edits and reads back is never told anything."""
    import time

    page = tmp_path / "index.html"
    page.write_text("\n".join(f"line {i}" for i in range(1, 200)), encoding="utf-8")
    backend = WorkspaceBackend(str(tmp_path), virtual_mode=True)

    backend.read("/index.html", offset=0, limit=100)
    assert READ_WITHHELD_MARKER in backend.read(
        "/index.html", offset=0, limit=100
    ).file_data["content"]

    time.sleep(0.01)
    page.write_text("\n".join(f"CHANGED {i}" for i in range(1, 250)), encoding="utf-8")

    again = backend.read("/index.html", offset=0, limit=100).file_data["content"]
    assert "already read lines" not in again and READ_WITHHELD_MARKER not in again


def test_the_check_keys_on_the_file_not_the_returned_slice(tmp_path) -> None:
    """The first version digested the slice that came back.

    Two different ranges of one unchanged file produce two different digests,
    so the file never looked unchanged and the check never fired - on exactly
    the overlapping reads it was written for. It passed every "did it error?"
    test while doing nothing.
    """
    (tmp_path / "a.txt").write_text(
        "\n".join(f"line {i}" for i in range(1, 500)), encoding="utf-8"
    )
    backend = WorkspaceBackend(str(tmp_path), virtual_mode=True)

    backend.read("/a.txt", offset=0, limit=200)
    # A strictly narrower range of the same unchanged file.
    result = backend.read("/a.txt", offset=50, limit=50)

    assert "already read lines" in result.file_data["content"]


# --- guessing at the project directory ------------------------------------


def test_a_wrong_project_guess_is_told_the_real_name(tmp_path) -> None:
    """The run has already committed to a project directory and recorded it;
    the guess is the only part missing.

    Measured across six runs, 53 failed listings of a directory that never
    existed while the marker sat on disk the whole time - 16, 11, 8, 8, 5
    and 5 per run.
    One run's ui specialist asked for `task-manager-ui` eleven times and
    `task-manager` - the real one - four.
    """
    from app.tools.repository import PROJECT_MARKER

    (tmp_path / "task-manager").mkdir()
    (tmp_path / "task-manager/index.html").write_text("x", encoding="utf-8")
    (tmp_path / PROJECT_MARKER).write_text("task-manager\n", encoding="utf-8")
    backend = WorkspaceBackend(str(tmp_path), virtual_mode=True)

    for guess in ("task-manager-ui", "/task-tracker"):
        error = backend.ls(guess).error
        assert "project directory is 'task-manager'" in error


def test_a_nested_path_is_not_a_project_guess(tmp_path) -> None:
    """`ls /docs/nope` means something else entirely."""
    from app.tools.repository import PROJECT_MARKER

    (tmp_path / "task-manager").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / PROJECT_MARKER).write_text("task-manager\n", encoding="utf-8")
    backend = WorkspaceBackend(str(tmp_path), virtual_mode=True)

    assert "project directory is" not in backend.ls("docs/nope").error


def test_no_pinned_project_means_no_hint(tmp_path) -> None:
    """Before any code is written there is nothing to name, and inventing one
    would be worse than silence."""
    backend = WorkspaceBackend(str(tmp_path), virtual_mode=True)

    assert "project directory is" not in backend.ls("todo-app").error


def test_the_real_name_is_never_hinted_at_itself(tmp_path) -> None:
    from app.tools.repository import PROJECT_MARKER

    (tmp_path / "task-manager").mkdir()
    (tmp_path / PROJECT_MARKER).write_text("task-manager\n", encoding="utf-8")
    backend = WorkspaceBackend(str(tmp_path), virtual_mode=True)

    assert not getattr(backend.ls("task-manager"), "error", None)


def test_the_same_file_under_two_spellings_shares_one_count(tmp_path) -> None:
    """Measured on one run's `specialist_ui_ux_0`.

    It read one `index.html` 54 times, alternating between
    `task-manager/index.html` (36 reads) and `/task-manager/index.html` (17).
    Keyed on the text the model typed, those were two files with two
    independent counts, and each had to reach the threshold on its own.
    """
    (tmp_path / "app.js").write_text("export function a(){}\n", encoding="utf-8")
    backend = WorkspaceBackend(str(tmp_path), virtual_mode=True)

    backend.read("/app.js")
    backend.read("app.js")

    assert "same bytes" in backend.read("/app.js").file_data["content"]


def test_a_different_range_returning_the_same_bytes_is_still_a_repeat(tmp_path) -> None:
    """The other half of the same run.

    It varied `offset` and `limit` around a file smaller than the window, so
    several different ranges came back byte-identical. Five consecutive reads
    returned the same bytes and the old key noticed none of them, because each
    arrived under a different `file_path|args|kwargs`.
    """
    (tmp_path / "app.js").write_text("a\nb\nc\n", encoding="utf-8")
    backend = WorkspaceBackend(str(tmp_path), virtual_mode=True)

    backend.read("/app.js", limit=400)
    backend.read("/app.js", limit=500)
    third = backend.read("/app.js", limit=600)

    assert "same bytes" in third.file_data["content"]


def test_a_file_it_cannot_stat_is_never_called_unchanged(tmp_path) -> None:
    """Without an identity there is no evidence the file stayed put.

    Saying "it has not changed since" about a file that just did is the one
    way this note can actively mislead, so absence of evidence returns no note
    rather than a confident one.
    """
    backend = WorkspaceBackend(str(tmp_path), virtual_mode=True)

    assert backend._file_identity("/nowhere.js") == ""
    assert backend._note_if_repeated("/nowhere.js", "text") == ""
    assert backend._note_if_repeated("/nowhere.js", "text") == ""
    assert backend._note_if_repeated("/nowhere.js", "text") == ""


def test_the_notice_comes_before_the_content(tmp_path) -> None:
    """A notice after the payload is read last or not at all.

    Measured on one run: `technical_lead` read one 3,847-character
    `milestone_plan.md` seven times, and the notice fired from the second read
    onward - appended after all 3,847 characters. Six of those seven calls were
    made having already been told.

    The notice exists to change the *next* call, so it belongs where the model
    starts rather than where it stops.
    """
    body = "\n".join(f"- criterion {i}" for i in range(200))
    (tmp_path / "plan.md").write_text(body, encoding="utf-8")
    backend = WorkspaceBackend(str(tmp_path), virtual_mode=True)

    backend.read("/plan.md")
    backend.read("/plan.md")
    content = backend.read("/plan.md").file_data["content"]

    assert "same bytes" in content
    assert content.index("same bytes") < 200, "the notice must be at the top"
    # And the file is still all there.
    assert "- criterion 199" in content


def test_the_content_is_still_complete_when_a_notice_is_added(tmp_path) -> None:
    """A note adds to the result; it must never take the file away.

    Withholding is a separate, later rung and does take it away - see
    `READS_BEFORE_WITHHOLDING`, now 2 - so this checks the rung it is about.
    A file this short is shown in full even when withheld, because
    withholding six lines saves nothing.
    """
    (tmp_path / "a.js").write_text("line one\nline two\nline three\n", encoding="utf-8")
    backend = WorkspaceBackend(str(tmp_path), virtual_mode=True)

    for _ in range(4):
        content = backend.read("/a.js").file_data["content"]
        for line in ("line one", "line two", "line three"):
            assert line in content

def test_path_traversal_is_caught(tmp_path: Path) -> None:
    backend = WorkspaceBackend(str(tmp_path), virtual_mode=True)
    
    # Each operation outside the workspace should return an error result, not crash
    read = backend.read("../outside.txt")
    assert getattr(read, "error", None) and "Path traversal" in getattr(read, "error")
    
    write = backend.write("../outside.txt", "content")
    assert getattr(write, "error", None) and "Path traversal" in getattr(write, "error")
    
    ls = backend.ls("../outside")
    assert getattr(ls, "error", None) and "Path traversal" in getattr(ls, "error")
    
    glob = backend.glob("*.txt", "../outside")
    assert getattr(glob, "error", None) and "Path traversal" in getattr(glob, "error")
    
    edit = backend.edit("../outside.txt", "content", "new")
    assert getattr(edit, "error", None) and "Path traversal" in getattr(edit, "error")
    
    delete = backend.delete("../outside.txt")
    assert getattr(delete, "error", None) and "Path traversal" in getattr(delete, "error")


def test_outside_root_directory_is_caught(tmp_path: Path) -> None:
    """A path resolving outside the workspace (e.g. via symlinks created by a venv)
    must return an error result, never crash the process with an unhandled ValueError.
    """
    outside_dir = tmp_path.parent / "external_dir"
    outside_dir.mkdir(exist_ok=True)
    (outside_dir / "file.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "ext_link").symlink_to(outside_dir)

    backend = WorkspaceBackend(str(tmp_path), virtual_mode=True)

    read = backend.read("/ext_link/file.txt")
    assert getattr(read, "error", None) and "outside root directory" in getattr(read, "error")

    ls = backend.ls("/ext_link")
    assert getattr(ls, "error", None) and "outside root directory" in getattr(ls, "error")

    glob = backend.glob("*.txt", "/ext_link")
    assert getattr(glob, "error", None) and "outside root directory" in getattr(glob, "error")

    grep = backend.grep("hello", path="/ext_link")
    assert grep.matches == []

    write = backend.write("/ext_link/file.txt", "content")
    assert getattr(write, "error", None) and "outside root directory" in getattr(write, "error")

    edit = backend.edit("/ext_link/file.txt", "hello", "world")
    assert getattr(edit, "error", None) and "outside root directory" in getattr(edit, "error")

    delete = backend.delete("/ext_link/file.txt")
    assert getattr(delete, "error", None) and "outside root directory" in getattr(delete, "error")

