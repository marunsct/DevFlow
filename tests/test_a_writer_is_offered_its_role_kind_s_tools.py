"""A builder and a writer of tests are offered their role kind's own tools (tool review 2026-11-26, TR.7, LF.1541).

Measured over the writers' requests of 26 runs: seven tools in every writer's list - `move_artifact`, `read_docs`,
`research` or the web pair, `look_up_package`, `look_at_page`, `module_exports`, `changed_since_sprint` - made 9 calls
in 4,260 requests, about 6,200 characters of tool schema. With `TOOL_LISTS_BY_ROLE_KIND` on, a builder gets the
readers, the file tools less `move_artifact`, the command tool and `read_command_output`; a writer of tests adds
`run_validation`; `module_exports` stays where the run offers it, since a stack's guidance names it.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.a_role_agent import Scripted, Stopped

BUILDER = [
    "ls", "read_file", "glob", "grep", "write_artifact", "edit_artifact", "delete_artifact",
    "run_terminal_command", "read_command_output", "module_exports",
]


@pytest.fixture
def lists(monkeypatch, tmp_path):
    """The switch on, the web tools offered, and every tool the deployed services enable enabled."""
    for name, value in {
        "TOOL_LISTS_BY_ROLE_KIND": "on", "LEAN_TOOL_LISTS": "on", "WEB_TOOLS_OFFERED": "on",
        "PREMIUM_PROJECT_INTELLIGENCE": "on", "PREMIUM_DEEP_VERIFICATION": "on",
        "WEB_SEARCH_ENABLED": "true", "SANDBOX_RUNTIMES_ENABLED": "true", "PACKAGE_LOOKUP_ENABLED": "true",
        "DOCS_LOOKUP_ENABLED": "true", "SWITCH_OVERRIDES_FROM_SETTINGS": "off", "PACKAGE_EXPORTS_NAMED": "on",
        "SEARXNG_URL": "http://search.invalid", "DATA_DIR": str(tmp_path / "data"),
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr("app.plugins.middleware.get_plugin_instructions", lambda keys, role: "")
    monkeypatch.setattr("app.models.model_pin.current_run_id", lambda: "run-role-lists")
    return monkeypatch


def _offered(role: str, root: Path, **options) -> tuple[list[str], str]:
    """(the tool names the stage's first call is offered, its system prompt), on a scripted model."""
    from app.agents.specialists import create_specialist_agent

    model = Scripted(replies=[], requests=[], offered=[])
    agent = create_specialist_agent(role, model=model, repo_root=str(root), **options)
    try:
        agent.invoke({"messages": [{"role": "user", "content": "go"}]}, {"configurable": {"thread_id": "t"}})
    except Stopped:
        pass
    system = next(str(m.content) for m in model.requests[0] if getattr(m, "type", "") == "system")
    return [name for name in model.offered[0] if not name[:1].isupper() and name != "task"], system


def _workspace(root: Path) -> Path:
    """A workspace with a sprint accepted, so the sprint history tool would be offered too."""
    workspace = root / "workspace"
    workspace.mkdir()
    (workspace / ".gitignore").write_text("node_modules\n")
    for argv in (["git", "init", "-q"], ["git", "add", "-A"],
                 ["git", "-c", "user.email=h@x", "-c", "user.name=h", "commit", "-qm", "s1"], ["git", "tag", "sprint-1"]):
        subprocess.run(argv, cwd=workspace, check=True, capture_output=True)
    return workspace


def test_a_builder_is_offered_its_role_kind_s_list_and_none_of_the_tools_writers_never_call(lists, tmp_path):
    offered, _ = _offered("backend", _workspace(tmp_path))

    assert offered == BUILDER


def test_a_writer_of_tests_is_offered_the_builder_s_list_and_the_validation_runner(lists, tmp_path):
    offered, _ = _offered("testing", _workspace(tmp_path))

    assert offered == [*BUILDER, "run_validation"]


def test_the_setup_of_a_stack_no_pack_covers_keeps_the_runtime_tool_its_request_asks_for(lists, tmp_path):
    offered, _ = _offered("testing", _workspace(tmp_path), setting_up_the_stack=True)

    assert sorted(offered) == sorted([*BUILDER, "run_validation", "use_runtime"])


def test_the_writing_rules_name_no_file_tool_the_list_leaves_out(lists, tmp_path):
    _, system = _offered("backend", _workspace(tmp_path))

    assert "`move_artifact`" not in system
    assert "`edit_artifact`" in system and "`delete_artifact`" in system


def test_with_the_switch_off_a_builder_is_offered_what_it_was_before(lists, tmp_path):
    lists.setenv("TOOL_LISTS_BY_ROLE_KIND", "off")

    offered, system = _offered("backend", _workspace(tmp_path))

    assert {"move_artifact", "look_up_package", "read_docs", "changed_since_sprint"} <= set(offered)
    assert "`move_artifact`" in system


def test_the_run_records_that_the_list_acted_and_what_it_left_out(lists, tmp_path):
    from app.observability.switch_firing import fired
    from app.observability.transcript import read_transcript

    lists.setattr("app.models.model_pin.current_run_id", lambda: "run-role-lists-recorded")
    _offered("database", _workspace(tmp_path))

    records = read_transcript("run-role-lists-recorded")
    chosen = [r for r in records if r.get("kind") == "tool_list_chosen"]
    assert "TOOL_LISTS_BY_ROLE_KIND" in fired(records)
    assert {"move_artifact", "look_up_package", "read_docs"} <= set(chosen[0]["left_out"])
