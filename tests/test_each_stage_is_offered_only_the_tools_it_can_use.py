"""Each stage is offered only the tools it can use, the same list on every call of the stage.

Deep review 2026-11-18, item C5: over 30 runs a specialist was offered 20 tools and five made 97% of the calls.
`search_the_web`, `use_runtime`, `code_graph` and `ask_specification` were never called in about 3,500 offers each,
`read_web_page` (which reads what the search finds) three times; `changed_since_sprint` was offered to every stage
of a run before any sprint existed to compare against; and the product manager, which cannot write, was offered four
file readers on a workspace holding one `.gitignore`. With `LEAN_TOOL_LISTS` on, each stage's list is pinned here.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from tests.a_role_agent import Scripted, Stopped

BANNED = {"task", "tasks", "to-do", "todo", "button", "click", "checkbox"}

#: What every writing specialist is offered with the switch on, before any sprint is accepted.
SPECIALIST = [
    "ls", "read_file", "glob", "grep",
    "write_artifact", "edit_artifact", "delete_artifact", "move_artifact",
    "run_terminal_command", "read_command_output", "look_up_package", "module_exports", "read_docs",
]


@pytest.fixture
def lean(monkeypatch):
    """The switch on, and every tool the deployed services enable (the compose file's defaults) enabled."""
    for name, value in {
        "LEAN_TOOL_LISTS": "on", "PREMIUM_PROJECT_INTELLIGENCE": "on", "PREMIUM_DEEP_VERIFICATION": "on",
        "WEB_SEARCH_ENABLED": "true", "SANDBOX_RUNTIMES_ENABLED": "true", "PACKAGE_LOOKUP_ENABLED": "true",
        "DOCS_LOOKUP_ENABLED": "true", "SWITCH_OVERRIDES_FROM_SETTINGS": "off", "PACKAGE_EXPORTS_NAMED": "on",
        "SEARXNG_URL": "http://search.invalid",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr("app.plugins.middleware.get_plugin_instructions", lambda keys, role: "")
    return monkeypatch


def _offered(create, root: Path) -> tuple[list[str], str]:
    """(the tool names the stage's first call is offered, its system prompt), on a scripted model."""
    model = Scripted(replies=[], requests=[], offered=[])
    agent = create(model=model, repo_root=str(root))
    try:
        agent.invoke({"messages": [{"role": "user", "content": "go"}]}, {"configurable": {"thread_id": "t"}})
    except Stopped:
        pass
    system = next(str(m.content) for m in model.requests[0] if getattr(m, "type", "") == "system")
    # Less the answer tool (its schema's class name) and `task`, which only a model on no known provider is given.
    return [name for name in model.offered[0] if not name[:1].isupper() and name != "task"], system


def _seeded(root: Path) -> Path:
    (root / ".gitignore").write_text("node_modules\n")
    return root


def _with_a_document(root: Path) -> Path:
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "product_intake.md").write_text("# Intake\n\nNotes for other programs.\n")
    return root


def _accepted_sprint(root: Path) -> Path:
    for argv in (["git", "init", "-q"], ["git", "add", "-A"],
                 ["git", "-c", "user.email=h@x", "-c", "user.name=h", "commit", "-qm", "s1"], ["git", "tag", "sprint-1"]):
        subprocess.run(argv, cwd=root, check=True, capture_output=True)
    return root


def test_a_builder_is_offered_its_tools_and_none_of_the_seldom_called_ones(lean, tmp_path):
    from app.agents.specialists import create_specialist_agent

    offered, _ = _offered(lambda **kw: create_specialist_agent("backend", **kw), _seeded(tmp_path))

    assert offered == SPECIALIST


def test_the_testing_role_also_runs_validation(lean, tmp_path):
    from app.agents.specialists import create_specialist_agent

    offered, _ = _offered(lambda **kw: create_specialist_agent("testing", **kw), _seeded(tmp_path))

    assert offered == [*SPECIALIST, "run_validation"]


def test_the_setup_of_a_stack_no_pack_covers_keeps_the_runtime_tool_its_request_asks_for(lean, tmp_path):
    from app.agents.specialists import create_specialist_agent

    offered, _ = _offered(
        lambda **kw: create_specialist_agent("testing", setting_up_the_stack=True, **kw), _seeded(tmp_path))

    assert "use_runtime" in offered
    assert not {"search_the_web", "read_web_page", "code_graph", "ask_specification"} & set(offered)


def test_the_sprint_history_tool_is_offered_once_a_sprint_is_accepted(lean, tmp_path):
    from app.agents.scrum_master import create_scrum_master_agent

    before, _ = _offered(create_scrum_master_agent, _with_a_document(tmp_path))
    after, _ = _offered(create_scrum_master_agent, _accepted_sprint(tmp_path))

    assert before == ["ls", "read_file", "glob", "grep"]
    assert after == ["ls", "read_file", "glob", "grep", "changed_since_sprint"]


def test_the_product_manager_on_a_new_workspace_is_offered_no_listing_or_search_and_told_why(lean, tmp_path):
    from app.agents.product_manager import create_product_manager_agent

    offered, system = _offered(create_product_manager_agent, _seeded(tmp_path))

    assert offered == ["read_file"]
    assert "no file listing or search is offered" in system
    assert "`glob`" not in system


def test_the_product_manager_on_a_workspace_with_documents_reads_them(lean, tmp_path):
    from app.agents.product_manager import create_product_manager_agent

    offered, system = _offered(create_product_manager_agent, _with_a_document(_seeded(tmp_path)))

    assert offered == ["ls", "read_file", "glob", "grep"]
    assert "`read_file`" in system


def test_the_architect_is_offered_the_lookups_but_not_the_web(lean, tmp_path):
    from app.agents.principal_architect import create_principal_architect_agent

    offered, _ = _offered(create_principal_architect_agent, _with_a_document(_seeded(tmp_path)))

    assert offered == ["ls", "read_file", "glob", "grep", "look_up_package", "read_docs"]


def test_with_the_switch_off_every_tool_is_offered_as_before(lean, tmp_path):
    from app.agents.specialists import create_specialist_agent

    lean.setenv("LEAN_TOOL_LISTS", "off")
    lean.setenv("WEB_TOOLS_OFFERED", "on")
    offered, _ = _offered(lambda **kw: create_specialist_agent("backend", **kw), _seeded(tmp_path))

    assert {"changed_since_sprint", "search_the_web", "read_web_page", "use_runtime", "code_graph",
            "ask_specification"} <= set(offered)


def test_a_run_that_chose_always_offers_the_web_tools_even_with_lean_lists(lean, tmp_path):
    """The user's Internet lookups choice "always" (plan WL.3): the stages that read documentation get the web tools."""
    from app.agents.principal_architect import create_principal_architect_agent
    from app.agents.specialists import create_specialist_agent

    lean.setenv("WEB_TOOLS_OFFERED", "on")
    builder, _ = _offered(lambda **kw: create_specialist_agent("backend", **kw), _seeded(tmp_path))
    architect, _ = _offered(create_principal_architect_agent, _with_a_document(_seeded(tmp_path)))

    assert {"search_the_web", "read_web_page"} <= set(builder) & set(architect)


def test_a_run_that_chose_off_is_never_offered_the_web_tools_even_with_full_lists(lean, tmp_path):
    """The user's Internet lookups choice "off" (plan WL.3) holds whatever the tool lists' own switch says."""
    from app.agents.specialists import create_specialist_agent

    lean.setenv("LEAN_TOOL_LISTS", "off")
    lean.setenv("WEB_TOOLS_OFFERED", "off")
    offered, _ = _offered(lambda **kw: create_specialist_agent("backend", **kw), _seeded(tmp_path))

    assert not {"search_the_web", "read_web_page"} & set(offered)
    assert {"read_docs", "look_up_package"} <= set(offered), "package metadata and documentation stay"


def test_the_new_line_avoids_the_banned_words():
    from app.agents.stage_tools import SAID

    assert not set(re.findall(r"[\w-]+", SAID.lower())) & BANNED
