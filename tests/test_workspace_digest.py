"""Stop every stage rediscovering the same workspace.

An agent is built per stage and none can see what an earlier one learned, so
each opens the same way: list the root, list the project, read the same files.
Measured on one run: 257 `read_file` calls over 22 distinct files, and the
opening moves of `technical_lead`, `test_round_0`, `milestone_review`,
`security_review` and every specialist were near-identical.

A digest does not replace reading a file. It replaces finding out what there is
to read - the part that was rediscovered twenty-five times.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agents.workspace_digest import (
    build_workspace_digest_middleware,
    render_workspace_digest,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "todo-app").mkdir()
    (tmp_path / "todo-app/app.js").write_text(
        "function createTask(t){}\nconst toggleTask = (id) => {}\nclass Store {}\n",
        encoding="utf-8",
    )
    (tmp_path / "todo-app/index.html").write_text("<html></html>\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/plan.md").write_text("# Plan\n" * 20, encoding="utf-8")
    return tmp_path


def test_the_digest_names_every_file_with_its_size(workspace: Path) -> None:
    digest = render_workspace_digest(workspace)

    assert "todo-app/app.js" in digest
    assert "docs/plan.md (21 lines)" in digest


def test_the_digest_names_what_a_code_file_defines(workspace: Path) -> None:
    """So an agent can go straight to the file holding the function it needs."""
    digest = render_workspace_digest(workspace)

    assert "createTask" in digest
    assert "toggleTask" in digest
    assert "Store" in digest


def test_the_agent_s_own_package_cache_is_not_the_workspace(workspace: Path) -> None:
    """The sandbox points HOME inside the workspace, so npm's cache lands there.

    Measured on one run: one `npm install` left 26 `_cacache` blobs with
    sha512 filenames, and they filled the listing ahead of the application.
    """
    cache = workspace / ".agent-home/.npm/_cacache/content-v2/sha512/0c/6f"
    cache.mkdir(parents=True)
    (cache / "deadbeef").write_text("cached\n", encoding="utf-8")

    digest = render_workspace_digest(workspace)

    assert "_cacache" not in digest
    assert "agent-home" not in digest


def test_the_project_survives_the_cut(workspace: Path) -> None:
    """Alphabetical order put dotfiles first, so the cut fell on the application."""
    from app.tools.repository import PROJECT_MARKER

    (workspace / PROJECT_MARKER).write_text("todo-app\n", encoding="utf-8")
    for index in range(60):
        (workspace / f"aaa_{index:02d}.txt").write_text("x\n", encoding="utf-8")

    digest = render_workspace_digest(workspace, max_files=10)

    assert "todo-app/app.js" in digest
    assert "... and" in digest


def test_an_unreadable_workspace_produces_no_digest_rather_than_an_error() -> None:
    """A digest that fails a stage costs far more than the calls it saves."""
    assert render_workspace_digest("/definitely/not/here") == ""


def _seen(request, repo_root):
    captured = {}

    def handler(final):
        captured["messages"] = final.messages
        return SimpleNamespace(result=[])

    build_workspace_digest_middleware(str(repo_root)).wrap_model_call(request, handler)
    return captured["messages"]


class _Request:
    def __init__(self, count):
        self.messages = [{"role": "user", "content": f"m{i}"} for i in range(count)]
        self.response_format = "schema"

    def override(self, **changes):
        clone = _Request(0)
        clone.messages = changes.get("messages", self.messages)
        return clone


def test_the_digest_arrives_on_the_opening_call(workspace: Path) -> None:
    messages = _seen(_Request(1), workspace)

    assert "The workspace as it stands" in str(messages[-1])


def test_it_is_given_on_later_calls_too(workspace: Path) -> None:
    """The reverse of what this file asserted until one run.

    The old rule was "by the second call the agent has the digest". It does
    not: `override` applies to one call and is never written to stored
    history, so from the second call the agent has no map and goes looking.
    Measured on one run's `principal_architect` - six identical
    `ls {'path': '/'}` and four `ls` of a project directory that did not exist
    yet, in one stage, against a digest that had already said what was there.
    """
    messages = _seen(_Request(12), workspace)

    assert any("The workspace as it stands" in str(m) for m in messages)


def test_it_still_never_accumulates(workspace: Path) -> None:
    """The property the old rule was protecting, which survives the change.

    Re-injecting is safe precisely because it does not build up: each request
    carries exactly one copy however many calls have gone before, because the
    override is discarded with the call.
    """
    request = _Request(12)
    before = list(request.messages)

    seen = _seen(request, workspace)

    assert sum("The workspace as it stands" in str(m) for m in seen) == 1
    assert request.messages == before


def test_the_opening_history_is_not_modified(workspace: Path) -> None:
    request = _Request(1)
    before = list(request.messages)

    _seen(request, workspace)

    assert request.messages == before


def test_it_can_be_switched_off(workspace: Path, monkeypatch) -> None:
    monkeypatch.setenv("WORKSPACE_DIGEST", "0")

    messages = _seen(_Request(1), workspace)

    assert all("The workspace as it stands" not in str(m) for m in messages)


def test_every_role_agent_gets_it() -> None:
    """Thirteen request builders; reaching twelve of thirteen is the mistake
    this codebase has made four times."""
    import inspect

    from app.agents.role_agent import create_role_agent

    assert "build_workspace_digest_middleware(resolved_repo_root)" in inspect.getsource(
        create_role_agent
    )


def test_an_empty_workspace_says_so_rather_than_saying_nothing(tmp_path: Path) -> None:
    """Silence reads as "go and find out", and the stage spends a call doing it."""
    digest = render_workspace_digest(tmp_path)

    assert "empty" in digest.lower()
    assert "readme" in digest.lower()


def test_a_workspace_holding_only_its_seed_files_says_nothing_is_built_yet(
    tmp_path: Path,
) -> None:
    """The case that actually happens - a run's workspace is never truly empty.

    It is created with a `.gitignore`, so the empty branch above is not the one
    `product_manager` reaches. It is handed a listing of one dotfile, which is
    a listing and not an answer, and its prompt tells it to ground every
    conclusion in repository evidence.

    One run is the proof. Its first model call carried the digest

        The workspace as it stands. This is what is there ...
          .gitignore (9 lines)

    and its first tool call was `read_repository_file('README.md')`. Across the
    transcripts: four runs, four such calls, all for README.md.
    """
    (tmp_path / ".gitignore").write_text("node_modules\n", encoding="utf-8")

    digest = render_workspace_digest(tmp_path)

    assert "Nothing has been built yet" in digest
    assert "no README" in digest
    # The listing is still there; the sentence is what was missing.
    assert ".gitignore" in digest


def test_the_sentence_goes_away_once_something_is_built(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("node_modules\n", encoding="utf-8")
    (tmp_path / "todo").mkdir()
    (tmp_path / "todo" / "app.js").write_text("export function a() {}\n", encoding="utf-8")

    digest = render_workspace_digest(tmp_path)

    assert "Nothing has been built yet" not in digest
    assert "todo/app.js" in digest


def test_an_unreadable_workspace_still_says_nothing_at_all() -> None:
    """Not there and empty are different facts; only one of them is known."""
    assert render_workspace_digest("/definitely/not/here") == ""


def test_documents_without_code_say_nothing_is_built_yet(tmp_path: Path) -> None:
    """The state every stage before the first specialist is in.

    One run's `architecture_review` was handed a digest of four `docs/`
    files and `.gitignore`. It spent a `read_file` on `/app.test.mjs` - a file
    its own specification plans - and then recorded a finding: "Specification
    references a test file 'app.test.mjs' but the repository does not contain
    it ... it is missing from the current repo." At that stage nothing has been
    built by design, so that is a design document marked down for not being an
    implementation.
    """
    (tmp_path / ".gitignore").write_text("node_modules\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "technical_specification.md").write_text(
        "# Spec\n" * 10, encoding="utf-8"
    )

    digest = render_workspace_digest(tmp_path)

    assert "No application code has been written yet" in digest
    assert "planned, not present" in digest
    assert "docs/technical_specification.md" in digest


def test_the_sentence_goes_once_any_code_exists(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("node_modules\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "spec.md").write_text("# Spec\n", encoding="utf-8")
    (tmp_path / "todo").mkdir()
    (tmp_path / "todo" / "app.js").write_text("export function a() {}\n", encoding="utf-8")

    digest = render_workspace_digest(tmp_path)

    assert "No application code has been written yet" not in digest


def test_a_seeded_only_workspace_keeps_its_own_wording(tmp_path: Path) -> None:
    """The two states are different and must not collapse into one message."""
    (tmp_path / ".gitignore").write_text("node_modules\n", encoding="utf-8")

    digest = render_workspace_digest(tmp_path)

    assert "nothing but the files it was created with" in digest
    assert "No application code has been written yet" not in digest
