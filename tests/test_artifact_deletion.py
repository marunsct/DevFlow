"""Tests for the workspace delete tool and the loop that made it necessary.

On run-61c5a5b6 the UI specialist held a write tool and no delete tool, and was
told scratch files must not be kept. It obeyed the only way it could: it wrote
`_selfdestruct.mjs` to unlink a probe, then `_finalclean.mjs` to unlink that,
then `_cleanup_selfdestruct2.mjs`, for roughly fifty approval gates, because a
Node process cannot unlink its own running file. These tests pin the capability
that ends the regress and the instructions that point at it.
"""

from __future__ import annotations

import pytest

from pathlib import Path

import pytest

from app.agents.role_agent import _WRITING_RULES, describe_tool_call
from app.tools.agent_toolkit import (
    HUMAN_APPROVAL_TOOLS,
    build_artifact_delete_tool,
)
from app.tools.repository import RepositoryToolError, delete_approved_artifact


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "project").mkdir(parents=True)
    (root / "project/probe.mjs").write_text("console.log('hi')\n", encoding="utf-8")
    (root / "project/index.html").write_text("<!doctype html>\n", encoding="utf-8")
    (root / ".env").write_text("SECRET=1\n", encoding="utf-8")
    return root


def test_a_scratch_file_is_removed_in_one_call(repo_root: Path) -> None:
    result = delete_approved_artifact(repo_root, "project/probe.mjs")

    assert result["deleted"] == "project/probe.mjs"
    assert not (repo_root / "project/probe.mjs").exists()
    # Nothing else in the folder is touched.
    assert (repo_root / "project/index.html").exists()


def test_the_model_s_leading_slash_means_the_workspace_root(repo_root: Path) -> None:
    delete_approved_artifact(repo_root, "/project/probe.mjs")

    assert not (repo_root / "project/probe.mjs").exists()


def test_deleting_outside_the_workspace_is_refused(repo_root: Path) -> None:
    outside = repo_root.parent / "outside.txt"
    outside.write_text("keep me", encoding="utf-8")

    with pytest.raises(RepositoryToolError):
        delete_approved_artifact(repo_root, "../outside.txt")

    assert outside.exists()


def test_a_directory_cannot_be_deleted(repo_root: Path) -> None:
    with pytest.raises(RepositoryToolError, match="directory"):
        delete_approved_artifact(repo_root, "project")

    assert (repo_root / "project").is_dir()


def test_credential_material_cannot_be_deleted(repo_root: Path) -> None:
    with pytest.raises(RepositoryToolError, match="credential"):
        delete_approved_artifact(repo_root, ".env")

    assert (repo_root / ".env").exists()


def test_a_missing_file_says_so_instead_of_failing_silently(repo_root: Path) -> None:
    with pytest.raises(RepositoryToolError, match="does not exist"):
        delete_approved_artifact(repo_root, "project/never-existed.mjs")


def test_the_tool_returns_an_error_rather_than_crashing_the_run(repo_root: Path) -> None:
    tool = build_artifact_delete_tool(str(repo_root))

    result = tool.invoke({"relative_path": "project/never-existed.mjs"})

    assert "error" in result


def test_deletion_stops_at_the_approval_gate() -> None:
    """A delete changes the workspace, so it must be gated like a write."""
    assert "delete_artifact" in HUMAN_APPROVAL_TOOLS


def test_the_reviewer_is_shown_which_file_would_be_removed() -> None:
    """A deletion has no command; describing it as one hides the only fact
    the reviewer needs."""
    describe = describe_tool_call("/workspace", "ui_ux_specialist", "sprint_1", "delete_artifact")

    description = describe({"args": {"relative_path": "project/_selfdestruct.mjs"}}, None, None)

    assert "project/_selfdestruct.mjs" in description
    assert "Command: None" not in description


def _normalised(text: str) -> str:
    """Prompt text wraps; assertions about its wording must not depend on where."""
    return " ".join(text.split())


def test_writing_agents_are_told_how_to_clean_up() -> None:
    rules = _normalised(_WRITING_RULES)

    assert "delete_artifact" in rules


def test_writing_agents_are_told_not_to_write_a_cleanup_script() -> None:
    rules = _normalised(_WRITING_RULES)

    assert "NEVER write a script whose purpose is to delete another script" in rules


# --- the invariant, not the instance --------------------------------------


def test_create_and_remove_are_handed_out_together() -> None:
    """A role that can write can also clean up.

    Splitting these is what produced the loop: the agent had a way to make a
    file and no way to unmake one, so it made more files.
    """
    from app.agents.role_agent import writing_tools

    names = {tool.name for tool in writing_tools("/workspace")}

    assert {"write_artifact", "delete_artifact"} <= names


def test_a_role_agent_assembles_its_mutation_tools_from_that_one_list() -> None:
    """So a fourth mutation tool cannot reach some roles and not others."""
    import inspect

    from app.agents.role_agent import create_role_agent

    source = inspect.getsource(create_role_agent)

    assert "writing_tools(resolved_repo_root) if can_write else []" in source


def test_every_mutation_tool_is_gated() -> None:
    """Whatever `writing_tools` hands out must stop at the approval interrupt."""
    from app.agents.role_agent import _interrupt_config, writing_tools

    tools = writing_tools("/workspace")
    config = _interrupt_config(tools, "/workspace", "ui_ux_specialist", "sprint_1")

    assert {tool.name for tool in tools} <= set(config)


def test_a_deletion_cannot_be_edited_into_a_different_file() -> None:
    """Approving the removal of one file must not execute the removal of another."""
    from app.agents.role_agent import _interrupt_config, writing_tools

    config = _interrupt_config(writing_tools("/workspace"), "/workspace", "ui", "s1")

    assert config["delete_artifact"]["allowed_decisions"] == ["approve", "reject"]


def test_the_refusal_of_an_inline_script_no_longer_asks_for_litter() -> None:
    """`node -e` is refused, and the refusal is where the loop started: it told
    the agent to put the code in a file and said nothing about removing it."""
    import pytest as _pytest

    from app.tools.sandbox import CommandNotAllowed, validate_command

    with _pytest.raises(CommandNotAllowed) as caught:
        validate_command(["node", "-e", "console.log(1)"], role_name="ui_ux_specialist")

    message = " ".join(str(caught.value).split())
    assert "delete_artifact" in message


def test_the_project_pin_cannot_be_tidied_away(repo_root: Path) -> None:
    """It looks like dotfile clutter and is the one thing every stage shares.

    Deleting it does not fail loudly - it makes the next stage build the
    application a second time in a second directory, which is what the pin was
    added to prevent after run-0b55ad49 produced three copies of one app.
    """
    from app.tools.repository import PROJECT_MARKER

    marker = repo_root / PROJECT_MARKER
    marker.write_text("project\n", encoding="utf-8")

    with pytest.raises(RepositoryToolError, match="which directory this project lives in"):
        delete_approved_artifact(repo_root, PROJECT_MARKER)

    assert marker.exists()


# --- the complete matrix --------------------------------------------------


def test_relocating_a_file_keeps_its_exact_bytes(repo_root: Path) -> None:
    """The alternative - rewrite at the new path, delete the old - regenerates
    content that was already approved, and can come back different."""
    from app.tools.repository import move_approved_artifact

    original = (repo_root / "project/index.html").read_text(encoding="utf-8")

    result = move_approved_artifact(repo_root, "project/index.html", "project/web/index.html")

    assert result["moved"] == "project/index.html"
    assert result["to"] == "project/web/index.html"
    assert (repo_root / "project/web/index.html").read_text(encoding="utf-8") == original
    assert not (repo_root / "project/index.html").exists()


def test_a_move_will_not_silently_overwrite(repo_root: Path) -> None:
    """Overwriting here is a delete nobody was shown."""
    from app.tools.repository import move_approved_artifact

    keep = repo_root / "project/probe.mjs"

    with pytest.raises(RepositoryToolError, match="already exists"):
        move_approved_artifact(repo_root, "project/index.html", "project/probe.mjs")

    assert keep.exists()


def test_a_move_cannot_carry_a_file_out_of_the_workspace(repo_root: Path) -> None:
    from app.tools.repository import move_approved_artifact

    with pytest.raises(RepositoryToolError):
        move_approved_artifact(repo_root, "project/index.html", "../escaped.html")

    assert (repo_root / "project/index.html").exists()
    assert not (repo_root.parent / "escaped.html").exists()


def test_the_project_pin_cannot_be_moved_either(repo_root: Path) -> None:
    """Moving it points every later stage at the wrong directory."""
    from app.tools.repository import PROJECT_MARKER, move_approved_artifact

    (repo_root / PROJECT_MARKER).write_text("project\n", encoding="utf-8")

    with pytest.raises(RepositoryToolError, match="which directory this project lives in"):
        move_approved_artifact(repo_root, PROJECT_MARKER, "project/pin.txt")

    assert (repo_root / PROJECT_MARKER).exists()


def test_every_file_operation_has_a_tool() -> None:
    """Create, read, change, cut, remove, relocate.

    The gap that mattered was remove: an agent with create-but-not-remove
    improvises, and the improvisation is another file. Pinning the whole set
    means the next gap is a failing test rather than a fifty-gate loop.
    """
    from app.agents.role_agent import _WORKSPACE_READ_TOOLS, writing_tools

    mutating = {tool.name for tool in writing_tools("/workspace")}

    assert mutating == {
        "write_artifact", "edit_artifact", "delete_artifact", "move_artifact"
    }
    assert {"ls", "read_file", "glob", "grep"} <= set(_WORKSPACE_READ_TOOLS)


def test_the_prompt_names_a_tool_for_every_case() -> None:
    """An agent that cannot find the tool reports it missing and stops."""
    from app.agents.role_agent import _WRITING_RULES

    rules = _normalised(_WRITING_RULES)

    for operation in ("list", "search", "read all", "read part", "create",
                      "replace", "change", "cut", "remove", "relocate"):
        assert operation in rules, operation
    assert "move_artifact" in rules


# --- a test is evidence, not clutter --------------------------------------


def test_a_test_file_cannot_be_deleted(repo_root: Path) -> None:
    """The delete tool was added to end a cleanup loop. Without this guard it
    also hands an agent a way to throw away the proof the product works.

    Measured on run-2b5def74: the test round wrote four suites, ran them - 27
    assertions passing against the real application - then deleted three of
    them as "temporary helper scripts", leaving only the suite that tested a
    copy of the code.
    """
    (repo_root / "project/test-contract.js").write_text("// suite\n", encoding="utf-8")

    with pytest.raises(RepositoryToolError, match="tests are part of what this run delivers"):
        delete_approved_artifact(repo_root, "project/test-contract.js")

    assert (repo_root / "project/test-contract.js").exists()


def test_the_refusal_says_what_to_do_instead(repo_root: Path) -> None:
    """A refusal a model cannot act on just moves the problem."""
    (repo_root / "project/a.test.js").write_text("// suite\n", encoding="utf-8")

    with pytest.raises(RepositoryToolError) as caught:
        delete_approved_artifact(repo_root, "project/a.test.js")

    # Naming the route, not just the rule. The old wording ("give it a name
    # that is not a test name") reads as advice for next time and left an agent
    # holding a throwaway probe with nowhere to go: run-9ff00d5b asked to
    # delete one five times, was refused each time, and the repeat guard failed
    # the run.
    message = " ".join(str(caught.value).split())
    assert "move_artifact" in message
    assert "delete_artifact" in message


def test_a_genuine_scratch_probe_is_still_deletable(repo_root: Path) -> None:
    """`verify-css.js` is what the loop was about; it must stay removable."""
    (repo_root / "project/verify-css.js").write_text("// probe\n", encoding="utf-8")

    delete_approved_artifact(repo_root, "project/verify-css.js")

    assert not (repo_root / "project/verify-css.js").exists()


@pytest.mark.parametrize(
    ("path", "is_test"),
    [
        ("tests/logic.js", True),
        ("project/test-contract.js", True),
        ("project/a.test.js", True),
        ("project/test_helpers.py", True),
        ("project/thing_test.py", True),
        ("project/verify-css.js", False),
        ("_selfdestruct.mjs", False),
        ("project/app.js", False),
        ("project/latest-news.js", False),
    ],
)
def test_what_counts_as_a_test(path: str, is_test: bool) -> None:
    from app.tools.repository import looks_like_a_test

    assert looks_like_a_test(path) is is_test


def test_the_two_definitions_of_a_test_agree() -> None:
    """`repository.looks_like_a_test` guards deletion; `_NOT_APPLICATION`
    decides what the size report and orphan check treat as a test. They are in
    different layers and must not drift."""
    from app.analysis.integration_checks import _NOT_APPLICATION
    from app.tools.repository import looks_like_a_test

    for path in ("tests/logic.js", "project/test-contract.js", "project/a.test.js"):
        assert looks_like_a_test(path), path
        assert _NOT_APPLICATION.search(path), path

    for path in ("project/app.js", "project/verify-css.js"):
        assert not looks_like_a_test(path), path
        assert not _NOT_APPLICATION.search(path), path


@pytest.mark.parametrize("name", ["a.test.mjs", "a.test.cjs", "test-contract.mjs"])
def test_an_mjs_test_is_protected_from_deletion(name: str) -> None:
    """The delete guard read the same too-narrow pattern, so a `.mjs` suite -
    which is what a testable design actually produces - was deletable."""
    from app.tools.repository import looks_like_a_test

    assert looks_like_a_test(name)


# --- the refusal has to name a way out -----------------------------------


def test_the_test_refusal_names_the_two_steps_that_work(tmp_path):
    """run-9ff00d5b's `specialist_testing_1` wrote `todo-app/debug.test.mjs`,
    ran it, then asked to delete it five times in a row - refused every time -
    until the repeat guard stopped the stage and FAILED THE RUN.

    The old text said "give it a name that is not a test name", which reads as
    advice for next time, not as something to do with the file in hand. Two of
    this codebase's own guards collided: the test protection from finding 08
    and the identical-request guard.
    """
    from app.tools.repository import PROJECT_MARKER, delete_approved_artifact

    (tmp_path / "todo-app").mkdir()
    (tmp_path / PROJECT_MARKER).write_text("todo-app\n", encoding="utf-8")
    (tmp_path / "todo-app/debug.test.mjs").write_text("probe\n", encoding="utf-8")

    with pytest.raises(Exception) as refusal:
        delete_approved_artifact(str(tmp_path), "todo-app/debug.test.mjs")

    message = str(refusal.value)
    assert "move_artifact" in message
    assert "todo-app/debug.mjs" in message
    # And it must say that repeating will not help, which is what it did.
    assert "refused the same way" in message


def test_the_route_the_refusal_names_actually_works(tmp_path):
    """Advice that does not work is worse than none.

    Verified end to end rather than asserted: `move_artifact` accepts a test
    name as its source, and `delete_artifact` accepts the renamed file.
    """
    from app.tools.repository import (
        PROJECT_MARKER,
        delete_approved_artifact,
        move_approved_artifact,
    )

    (tmp_path / "todo-app").mkdir()
    (tmp_path / PROJECT_MARKER).write_text("todo-app\n", encoding="utf-8")
    (tmp_path / "todo-app/debug.test.mjs").write_text("probe\n", encoding="utf-8")

    move_approved_artifact(str(tmp_path), "todo-app/debug.test.mjs", "todo-app/debug.mjs")
    deleted = delete_approved_artifact(str(tmp_path), "todo-app/debug.mjs")

    assert deleted["status"] == "deleted"
    assert not (tmp_path / "todo-app/debug.mjs").exists()


def test_a_real_test_is_still_protected(tmp_path):
    """The protection exists because run-2b5def74's test round deleted three of
    its four suites as "temporary helper scripts", leaving only the one that
    tested a copy of the code."""
    from app.tools.repository import PROJECT_MARKER, delete_approved_artifact

    (tmp_path / "todo-app").mkdir()
    (tmp_path / PROJECT_MARKER).write_text("todo-app\n", encoding="utf-8")
    (tmp_path / "todo-app/app.test.mjs").write_text("real tests\n", encoding="utf-8")

    with pytest.raises(Exception):
        delete_approved_artifact(str(tmp_path), "todo-app/app.test.mjs")
    assert (tmp_path / "todo-app/app.test.mjs").exists()
