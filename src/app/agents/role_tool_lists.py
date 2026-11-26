"""One list of tools per kind of writing role (tool review 2026-11-26, TR.7, LF.1541; behind `TOOL_LISTS_BY_ROLE_KIND`).

Measured over the writers' requests of 26 runs (builders, the unit-test writer, the acceptance author, the test round,
the setup of a stack no pack covers): seven tools in every writer's list made 9 calls in 4,260 requests -
`move_artifact` 0 in 4,179 offers, `read_docs` 0, `research` or the web pair 0, `look_up_package` 4, `look_at_page`
3 (fixers, who no longer have it), `module_exports` 2 and `changed_since_sprint` 0 - about 6,200 characters of tool
schema, a quarter of a writer's. The fixers' own list (`lean_fixer.TOOLS`, FX.3) dropped six of them with no tool
missed in 81 requests. So, with the switch on, a writing specialist is offered its role kind's list:

- a builder: the four readers, the file tools (`write_artifact`, `edit_artifact`, `replace_lines` where line edits
  are on, `delete_artifact`; not `move_artifact`), `run_terminal_command` and `read_command_output`;
- a writer of tests (the testing role: the unit-test writer, the acceptance author, the test round, a stack's setup):
  the same and `run_validation`;
- either: `module_exports` where the run offers it (a stack's guidance names it, as the fixer's list keeps it), a tool
  the stage's own request asks for (`kept_tools`: `use_runtime` in the setup of a stack no pack covers), the MCP tools
  the owner configured, and `ask_specification` when its own switch is on.

A tool left out keeps its code and its other stages: the stack selector and the architect keep `look_up_package` and
`read_docs`, the harness keeps its own page probe and its lookups at fixed points. The writing rules then name only
the file tools offered (`rules_for_the_tools`). Each list is chosen when the stage's agent is built, so it is the same on
every call of the stage (a server's prompt cache reuses only an identical prefix).

An efficiency change, so a switch, off in code like every switch; kept only if measured runs lose no hidden test by it.
"""
from __future__ import annotations

import logging
import statistics
import threading
from typing import Any, Iterable

from app.switches import is_on

logger = logging.getLogger(__name__)

#: Off in code like every switch; the compose file says whether it is on.
ON_BY_DEFAULT = False

READERS: tuple[str, ...] = ("ls", "read_file", "glob", "grep")
FILE_TOOLS: tuple[str, ...] = ("write_artifact", "edit_artifact", "replace_lines", "delete_artifact")
COMMANDS: tuple[str, ...] = ("run_terminal_command", "read_command_output")
#: Each role kind's own tools, beside its answer.
LISTS: dict[str, frozenset[str]] = {
    "builder": frozenset({*READERS, *FILE_TOOLS, *COMMANDS}),
    "test writer": frozenset({*READERS, *FILE_TOOLS, *COMMANDS, "run_validation"}),
}
#: The tools the writers' requests carried that made 9 calls in 4,260 of them; the effects report counts what is left.
SELDOM_USED_BY_WRITERS: frozenset[str] = frozenset({
    "move_artifact", "read_docs", "research", "search_the_web", "read_web_page", "look_up_package", "look_at_page",
    "changed_since_sprint",
})

#: A transcript record kind the harness writes of the tools it chose, with no model reading it; the switch-firing
#: check reads its `message`.
RECORD_KIND = "tool_list_chosen"
#: What the record says for this switch; the switch-firing check reads it.
SAID = "tools held to its role's list"


class _ByRoleKind:
    """`TOOL_LISTS_BY_ROLE_KIND` as the switch registry reads one: off in code until measured."""

    ON_BY_DEFAULT = ON_BY_DEFAULT
    #: What the admin page says this switch does.
    explanation = ("Each builder and each writer of tests is offered its role's own tools: the readers, the file "
                   "tools, the command tool and, for tests, the validation runner. The tools writers almost never "
                   "called (moving a file, documentation and web lookups, the package registry, the page view, the "
                   "sprint history) are left out of their lists; other stages keep theirs. Smaller requests, fewer "
                   "wrong choices.")

    @staticmethod
    def enabled() -> bool:
        return is_on("TOOL_LISTS_BY_ROLE_KIND", _ByRoleKind.ON_BY_DEFAULT)


by_role_kind_switch = _ByRoleKind()


def enabled() -> bool:
    return by_role_kind_switch.enabled()


def kind_of(role: str) -> str:
    """The role kind of a writing specialist: "test writer" for the testing role, else "builder"."""
    return "test writer" if str(role) == "testing" else "builder"


def _names(tools: Iterable[Any]) -> set[str]:
    return {str(getattr(tool, "name", "") or "") for tool in tools or ()} - {""}


def only_tools(role: str, offered: Iterable[Any] = (), kept: Iterable[str] = (), also: Iterable[Any] = (),
               stage: str = "") -> frozenset[str] | None:
    """The names a writing specialist of `role` is offered beside its answer, with the switch on; None with it off
    (every tool the role is given, as before).

    `offered`: the stage's extra tools as built, to say what is left out; `kept`: names the stage's own request asks
    for; `also`: tools another choice put there on purpose (the owner's MCP servers, `ask_specification`)."""
    if not enabled():
        return None
    from app.agents.lean_fixer import WHEN_OFFERED

    kind = kind_of(role)
    chosen = LISTS[kind] | WHEN_OFFERED | {str(name) for name in kept or () if name} | _names(also)
    _note(kind, stage, sorted((_names(offered) | {"move_artifact"}) - chosen))
    return frozenset(chosen)


_LOCK = threading.Lock()
#: (run, role kind) already recorded in this process.
_NOTED: set[tuple[str, str]] = set()


def _the_run() -> str:
    try:
        from app.models.model_pin import current_run_id

        return current_run_id()
    except Exception:  # noqa: BLE001 - outside a run
        return ""


def note_once(subject: str, stage: str, message: str, **fields: Any) -> None:
    """Record, once per run and `subject`, a tool choice the harness made (`RECORD_KIND`). Never raises."""
    run = _the_run()
    if not run:
        return
    with _LOCK:
        if (run, subject) in _NOTED:
            return
        _NOTED.add((run, subject))
    try:
        from app.observability.transcript import record

        record(run, stage or subject, RECORD_KIND, message=message, **fields)
    except Exception:  # noqa: BLE001 - a record never fails a stage
        logger.debug("Could not record a tool choice", exc_info=True)


def _note(kind: str, stage: str, left_out: list[str]) -> None:
    note_once(f"role list {kind}", stage, f"A {kind}'s {SAID}; left out: {', '.join(left_out) or 'nothing'}",
              switch="TOOL_LISTS_BY_ROLE_KIND", left_out=left_out)


def rules_for_the_tools(text: str, offered: Iterable[str]) -> str:
    """`text` naming only the file tools `offered`: the writing rules' line for `move_artifact` goes when it is not."""
    names = set(offered)
    if "move_artifact" in names or "`move_artifact`" not in text:
        return text
    return "\n".join(line for line in text.split("\n")
                     if not ("`move_artifact`" in line and line.lstrip().startswith("relocate")))


# --- what the effects report says ------------------------------------------------------------------------------------

def _tools_of(record: dict) -> set[str]:
    tools = record.get("tools")
    return {str(name) for name in tools} if isinstance(tools, list) else set()


def effects_lines(records: Iterable[Any]) -> list[str]:
    """TR.7 and TR.8 for `loop.sh effects`: a writer's request's tool schema and the seldom-used tools it still
    carried; the lookups the model was offered and called."""
    sizes, carried = [], 0
    records = [r for r in records if isinstance(r, dict)]
    for record in records:
        if record.get("kind") != "model_request" or "write_artifact" not in _tools_of(record):
            continue
        size = (record.get("blocks") or {}).get("tool_schemas")
        if isinstance(size, (int, float)):
            sizes.append(int(size))
        carried += bool(_tools_of(record) & SELDOM_USED_BY_WRITERS)
    label = "TR.7 writer requests"
    lines = [f"     -  {label}: not reached" if not sizes and not carried else
             f"  {len(sizes):>4}  {label}: tool schemas median {int(statistics.median(sizes)) if sizes else 0:,} "
             f"characters; {carried} carried a tool writers almost never call (0 with `TOOL_LISTS_BY_ROLE_KIND` on)"]
    from app.models.research_check import lookup_use

    use = lookup_use(records)
    if not use:
        lines.append("     -  TR.8 lookups offered to the model: not reached")
    for model, (offers, calls) in sorted(use.items()):
        lines.append(f"  {offers:>4}  TR.8 replies to a request offering a lookup ({model}); {calls} lookup calls")
    return lines


__all__ = ["LISTS", "ON_BY_DEFAULT", "RECORD_KIND", "SAID", "SELDOM_USED_BY_WRITERS", "by_role_kind_switch",
           "effects_lines", "enabled", "kind_of", "note_once", "only_tools", "rules_for_the_tools"]
