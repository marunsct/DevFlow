"""The notice of tools still listed but refused names every refused one (deep review 2026-11-25, item 4).

Measured over 12 runs: the notice named only the first 12 refused tools in alphabetical order, which always dropped
`run_terminal_command`, `write_artifact` and the rest of the alphabet; 24 of 139 refused calls were to a tool it had
left out. The tools are those of a real builder request that withheld all but its answer.
"""

from __future__ import annotations

import re

from app.agents.settled_answer import stable_tools_notice

#: The tools of the request, in its order.
OFFERED = ["ls", "read_file", "glob", "grep", "write_artifact", "edit_artifact", "delete_artifact", "move_artifact",
           "run_terminal_command", "read_command_output", "look_up_package", "module_exports", "read_docs",
           "search_the_web", "read_web_page", "SpecialistOutput"]
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _said_to_be_refused(notice: str, tool: str) -> bool:
    if "every tool except" in notice:
        return f"`{tool}`" not in notice.split("every tool except", 1)[1]
    return f"`{tool}`" in notice


def test_every_withheld_tool_is_said_to_be_refused():
    withheld = set(OFFERED) - {"SpecialistOutput"}

    notice = stable_tools_notice(withheld, OFFERED)

    assert [tool for tool in sorted(withheld) if not _said_to_be_refused(notice, tool)] == []
    assert not _said_to_be_refused(notice, "SpecialistOutput")
    assert not BANNED.search(notice)


def test_a_few_withheld_are_each_named():
    withheld = {"run_terminal_command", "search_the_web", "write_artifact"}

    notice = stable_tools_notice(withheld, OFFERED)

    assert all(f"`{tool}`" in notice for tool in withheld)
    assert "`read_file`" not in notice


def test_more_than_twelve_withheld_without_the_offered_list_are_all_named():
    withheld = set(OFFERED) - {"SpecialistOutput"}

    notice = stable_tools_notice(withheld)

    assert all(f"`{tool}`" in notice for tool in withheld)
