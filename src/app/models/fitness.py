"""Can this model call tools well enough to run the harness's stages?

Measured on one run: a 1-bit build model passed the readiness check (it was
served under the name the settings gave) and then called tools that did not
exist (`Read`, `ReadFile`, `run_read_11=File`), sent one query 27 times and
took 101 minutes over a sprint plan another model wrote in 7. Being served is
not being fit. Five short scripted requests, each with one plainly right tool
call, measure that before a run starts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


def _tool(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


_PATH = {"type": "string"}
TOOLS = [
    _tool("read_file", "Read a file's contents.", {"file_path": _PATH}, ["file_path"]),
    _tool("ls", "List a directory.", {"path": _PATH}, ["path"]),
    _tool("grep", "Search the project's files for a pattern.", {"pattern": _PATH}, ["pattern"]),
    _tool("write_file", "Write a file.", {"file_path": _PATH, "content": {"type": "string"}}, ["file_path", "content"]),
    _tool(
        "run_terminal_command",
        "Run one program with its arguments; there is no shell.",
        {"command": {"type": "array", "items": {"type": "string"}}, "working_directory": _PATH},
        ["command"],
    ),
]


def _has(key: str, text: str) -> Callable[[dict[str, Any]], bool]:
    return lambda args: text in str(args.get(key) or "")


#: (request, the tool meant, a check of its arguments)
PROBES: list[tuple[str, str, Callable[[dict[str, Any]], bool]]] = [
    ("Read the file docs/plan.md.", "read_file", _has("file_path", "plan.md")),
    ("List what is in the directory src.", "ls", _has("path", "src")),
    ("Find where createStore appears in the project.", "grep", _has("pattern", "createStore")),
    ("Write the text hello to the file notes/hi.txt.", "write_file",
     lambda a: "hi.txt" in str(a.get("file_path") or "") and "hello" in str(a.get("content") or "")),
    ("Run npm test in the directory app.", "run_terminal_command",
     lambda a: isinstance(a.get("command"), list) and "npm" in a["command"]),
]

FIT = 5
USABLE = 3


@dataclass
class Fitness:
    passed: int
    total: int
    misses: list[str] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        if self.passed >= FIT:
            return "fit"
        if self.passed >= USABLE:
            return "usable"
        return "unfit"

    def advice(self, model_name: str = "") -> str:
        said = self._advice()
        if self.verdict != "fit" and model_name:
            # Which server setting is likely missing, from the family (Initiative M):
            # a tool-call failure is mostly a server that does not parse the family's calls.
            from app.models.registry import profile_for

            profile = profile_for(model_name)
            if profile.family != "generic":
                said += (f"; check that the server parses this {profile.family} model's tool calls: "
                         f"{profile.parser} (llama.cpp: --jinja with the model's own chat template; "
                         "vLLM: --tool-call-parser)")
        return said

    def _advice(self) -> str:
        if self.verdict == "fit":
            return "fit for every stage"
        if self.verdict == "usable":
            return ("usable: expect repaired and refused calls; Fast delivery and a higher-quality "
                    "quantisation of the same model are recommended")
        return ("unfit for agent stages: it does not call the tool a plain request asks for; use a "
                "higher-quality quantisation or another model before a run")


def probe(model: Any) -> Fitness:
    """Ask `model` each probe once and count the replies that call the right tool with sound arguments."""
    from langchain_core.messages import HumanMessage, SystemMessage

    bound = model.bind_tools(TOOLS)
    passed, misses = 0, []
    for request, meant, sound in PROBES:
        try:
            reply = bound.invoke([
                SystemMessage(content="Answer each request with exactly one call of the right tool."),
                HumanMessage(content=request),
            ])
            calls = list(getattr(reply, "tool_calls", None) or [])
        except Exception as error:  # noqa: BLE001 - a failed call is a miss
            misses.append(f"{meant}: {type(error).__name__}")
            continue
        right = [call for call in calls if call.get("name") == meant]
        if right and sound(right[0].get("args") or {}):
            passed += 1
        else:
            got = ", ".join(f"{c.get('name')}({str(c.get('args'))[:60]})" for c in calls) or "no tool call"
            misses.append(f"{meant}: {got}")
    return Fitness(passed, len(PROBES), misses)


#: Three small files and a change for each, asked once as a whole-file write and
#: once as a find-and-replace edit (Initiative BH). Well formed: the call names
#: the file, and its result is the file with the change and nothing else lost.
EDIT_SAMPLES: list[tuple[str, str, str, str]] = [
    ("app/config.py", "PORT = 8000\nDEBUG = False\nNAME = 'notes'\n", "Set DEBUG to True.", "DEBUG = True"),
    ("src/greet.js", "export function greet(name) {\n  return 'Hello, ' + name;\n}\n",
     "Make greet say Hi instead of Hello.", "'Hi, '"),
    ("README.md", "# Notes\n\nA small notes service.\n\n## Run\n\nsh start.sh\n",
     "Add a line 'Port: 8000' at the end of the Run section.", "Port: 8000"),
]
EDIT_ROUNDS = 2

_EDIT_TOOL = _tool(
    "edit_file", "Replace one exact passage of a file.",
    {"file_path": _PATH, "find": {"type": "string"}, "replace": {"type": "string"}}, ["file_path", "find", "replace"],
)


def _well_formed_whole(args: dict[str, Any], path: str, before: str, wanted: str) -> bool:
    content = str(args.get("content") or "")
    kept = [line for line in before.splitlines() if line.strip() and wanted.split()[0] not in line]
    return path in str(args.get("file_path") or "") and wanted in content and sum(l in content for l in kept) >= len(kept) - 1


def _well_formed_edit(args: dict[str, Any], path: str, before: str, wanted: str) -> bool:
    find = str(args.get("find") or "")
    return (path in str(args.get("file_path") or "") and bool(find) and before.count(find) == 1
            and wanted in before.replace(find, str(args.get("replace") or "")))


def edit_probe(model: Any) -> dict[str, float]:
    """The share of well-formed whole-file writes and of well-formed find-and-replace edits; uses the model."""
    from langchain_core.messages import HumanMessage, SystemMessage

    tallies = {"whole": [0, 0], "edit": [0, 0]}
    for mode, tool, check in (("whole", TOOLS[3], _well_formed_whole), ("edit", _EDIT_TOOL, _well_formed_edit)):
        bound = model.bind_tools([tool])
        how = "by writing the whole file again" if mode == "whole" else "by replacing exactly one passage"
        for _ in range(EDIT_ROUNDS):
            for path, before, change, wanted in EDIT_SAMPLES:
                tallies[mode][1] += 1
                try:
                    reply = bound.invoke([
                        SystemMessage(content=f"Make the requested change {how}, with one tool call."),
                        HumanMessage(content=f"The file {path} holds:\n```\n{before}```\n{change}"),
                    ])
                    calls = list(getattr(reply, "tool_calls", None) or [])
                except Exception:  # noqa: BLE001 - a failed call is not well formed
                    continue
                if calls and check(calls[0].get("args") or {}, path, before, wanted):
                    tallies[mode][0] += 1
    return {mode: round(ok / total, 3) if total else 0.0 for mode, (ok, total) in tallies.items()}
