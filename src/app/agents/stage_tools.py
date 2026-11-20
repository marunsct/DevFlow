"""Each stage offered only the tools it can use (deep review 2026-11-18, item C5, behind `LEAN_TOOL_LISTS`).

Over 30 runs a specialist was offered 20 tools and five of them made 97% of the calls. Four were never called in
about 3,500 offers each - `search_the_web`, `use_runtime`, `code_graph`, `ask_specification` - and `read_web_page`,
which reads the pages `search_the_web` finds, three times. Every tool's schema is sent with every request (about
3,300 characters for those five), and a small model choosing among tools that do one job is a choice it can get
wrong. With the switch on:

- those five are not offered, except where a stage's own request asks for one (`use_runtime` in the setup of a stack
  no pack covers); their code and their own switches stay as they were;
- `changed_since_sprint` is offered only once a sprint has been accepted: before that it can only answer that there
  is nothing to compare against;
- a role that cannot write, on a workspace that holds nothing but the files it was created with, is offered no file
  listing or search - only `read_file`, which the filesystem layer requires: the brief in its request is the whole of
  the evidence, and its prompt says so instead of naming the readers.

Each list is chosen when the stage's agent is built, so it is the same on every call of the stage (a server's prompt
cache reuses only an identical prefix, and the tools are part of it).

An efficiency change, so a switch, off in code like every switch; kept only if measured runs lose no hidden test by it.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from app.switches import is_on

#: Off in code like every switch; the compose file says whether it is on.
ON_BY_DEFAULT = False

#: Never or almost never called in about 3,500 offers each (30 runs): not offered with the switch on.
SELDOM_CALLED: frozenset[str] = frozenset({
    "search_the_web", "read_web_page", "use_runtime", "code_graph", "ask_specification",
})
#: The built-in readers of the workspace.
WORKSPACE_READERS: tuple[str, ...] = ("ls", "read_file", "glob", "grep")
#: The one reader the filesystem layer cannot do without (deepagents refuses a list without it).
REQUIRED_READER = "read_file"
#: The tool that answers what changed since an accepted sprint.
SPRINT_HISTORY = "changed_since_sprint"

#: What a read-only role on a workspace with nothing in it is told in place of the readers' line; the audit's
#: switch-firing check reads it.
SAID = (
    "- The workspace holds nothing yet, so no file listing or search is offered:\n"
    "  the request in front of you is the whole of the evidence. Answer from it.\n"
)


class _LeanToolLists:
    """`LEAN_TOOL_LISTS` as the switch registry reads one: off in code until measured."""

    ON_BY_DEFAULT = ON_BY_DEFAULT
    #: What the admin page says this switch does.
    explanation = ("Each stage is offered only the tools it can use: the five tools almost never called in 30 runs "
                   "(web search and page reading, runtime install, code graph, specification questions) are left out, "
                   "the sprint history tool waits for an accepted sprint, and a read-only role on an empty workspace "
                   "gets no file listing or search. Smaller requests, fewer wrong choices.")

    @staticmethod
    def enabled() -> bool:
        return is_on("LEAN_TOOL_LISTS", _LeanToolLists.ON_BY_DEFAULT)


lean_tool_lists_switch = _LeanToolLists()


def enabled() -> bool:
    return lean_tool_lists_switch.enabled()


def _named(tool: Any) -> str:
    return str(getattr(tool, "name", "") or (tool.get("name", "") if isinstance(tool, dict) else ""))


def without_the_seldom_called(tools: Iterable[Any], keep: Iterable[str] = ()) -> list[Any]:
    """`tools` less the seldom-called ones, but for those named in `keep` and the web tools when the run's Internet
    lookups choice offers them (`WEB_TOOLS_OFFERED`); all of them when the switch is off."""
    tools = list(tools)
    if not enabled():
        return tools
    kept = set(keep)
    from app.tools import web_search

    if web_search.offered():
        kept |= web_search.WEB_TOOL_NAMES
    return [tool for tool in tools if _named(tool) not in SELDOM_CALLED or _named(tool) in kept]


def _names_a_reader(prompt: str) -> bool:
    import re

    return any(re.search(rf"(?<![\w./-]){name}(?![\w-])", prompt or "")
               for name in WORKSPACE_READERS if name != REQUIRED_READER)


def sprint_history_offered(repo_root: str | Path) -> bool:
    """Whether `changed_since_sprint` is offered: always with the switch off, else once a sprint has been accepted."""
    if not enabled():
        return True
    try:
        from app.tools.version_control import accepted_sprints

        return bool(accepted_sprints(repo_root))
    except Exception:  # noqa: BLE001 - offered when the history cannot be read, as before
        return True


def workspace_readers(repo_root: str | Path, can_write: bool, prompt: str = "") -> list[str]:
    """The built-in readers a role is offered: only the required one for a read-only role on a workspace that holds
    nothing yet, unless the role's own `prompt` names one of the others (a role told of a tool is offered it)."""
    if not enabled() or can_write or _names_a_reader(prompt):
        return list(WORKSPACE_READERS)
    try:
        from app.agents.workspace_digest import holds_nothing_yet

        empty = holds_nothing_yet(repo_root)
    except Exception:  # noqa: BLE001 - offered when the workspace cannot be read, as before
        empty = False
    return [REQUIRED_READER] if empty else list(WORKSPACE_READERS)


__all__ = ["ON_BY_DEFAULT", "REQUIRED_READER", "SAID", "SELDOM_CALLED", "SPRINT_HISTORY", "WORKSPACE_READERS", "enabled",
           "lean_tool_lists_switch", "sprint_history_offered", "without_the_seldom_called", "workspace_readers"]
