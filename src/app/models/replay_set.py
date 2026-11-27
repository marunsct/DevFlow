"""Real stage requests, frozen as the diagnosis's probes, and the checks that score a model's reply to one (DX.8, minimal).

The 2026-11-27 diagnosis design (section 4.3): a probe is a recorded request of a real stage, with its tools and its
answer schema, replayed against the model and scored by what the reply does - a call to a tool it was offered, with
arguments that parse and carry what the tool requires, an answer that validates against the stage's own schema, not
cut at its cap, not repeating itself - never by matching the recorded reply, and never by a hidden test.

The minimal set (`replays/`, built by `scripts/loop/replay_set_build.py`): for each stage kind (`stage_kinds`: a
working step, a review, a design request), one request from each of three benchmark families, each the most
reasoning-heavy request of that kind in a delivered run whose recorded reply passed its own checks, under
`MOST_CHARACTERS`. Owner, 2026-11-27: only benchmark runs' transcripts become probes - never the owner's own runs,
never a hidden test. So the builder takes only runs scored against a benchmark family's own brief (`data/bench`), and
`leaks` refuses an item holding a run id, a host path, or any line of a benchmark's hidden tests; the same guard runs
over the shipped set in the suite.

Transcripts keep tool names, not their schemas: each tool's schema is rebuilt from the harness's own definitions
(`tool_schemas`); a tool the harness no longer has is offered with an open schema. The set's hash (`set_hash`) is kept
with every profile made from it.
"""
from __future__ import annotations

import ast
import gzip
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

ITEMS_DIR = Path(__file__).parent / "replays"
#: The most characters of messages an item holds: the request is replayed whole, at stage size.
MOST_CHARACTERS = 150_000
#: A hidden test's line this long or longer, found in an item, is a leak.
LEAK_LINE_CHARS = 25
_AN_IMPORT = re.compile(r"^(?:import\s|from\s+\S+\s+import\s|const\s+\{?[\w\s,]+\}?\s*=\s*require\(|using\s|use\s)")
_RUN_ID = re.compile(r"\brun-[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b")
_HOST_PATHS = (
    (re.compile(r"/app/data/workspaces/[^/\s\"']+/workspace-run-[0-9a-f-]+/?"), "/workspace/"),
    (re.compile(r"/home/[A-Za-z0-9._-]+/"), "/home/user/"),
    (re.compile(r"host\.docker\.internal:\d+"), "model-server"),
)


@dataclass(frozen=True)
class Item:
    id: str
    kind: str
    family: str
    messages: list[dict]
    tools: list[dict]
    #: "module:Class" of the stage's answer schema, when one of its tools is the answer.
    answer: str = ""
    answer_tool: str = ""
    notes: dict = field(default_factory=dict)


# --- the shipped set --------------------------------------------------------------------------------------------

def load(directory: Path | None = None) -> list[Item]:
    """Every frozen item, in a fixed order (kind, family)."""
    folder = directory or ITEMS_DIR
    items = []
    for path in sorted(folder.glob("*.json.gz")):
        found = json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
        items.append(Item(**{k: v for k, v in found.items() if k in Item.__dataclass_fields__}))
    order = {kind: n for n, kind in enumerate(("step", "reading", "opening"))}
    return sorted(items, key=lambda item: (order.get(item.kind, 9), item.family, item.id))


def set_hash(items: Iterable[Item] | None = None) -> str:
    """A short hash of the set's content: a profile made from another set says so."""
    digest = hashlib.sha256()
    for item in items if items is not None else load():
        digest.update(json.dumps([item.id, item.kind, item.messages, item.tools, item.answer], sort_keys=True,
                                 default=str).encode("utf-8"))
    return digest.hexdigest()[:12]


# --- scoring a reply --------------------------------------------------------------------------------------------

def _answer_model(item: Item) -> Any:
    if not item.answer:
        return None
    import importlib

    module, _, name = item.answer.partition(":")
    try:
        return getattr(importlib.import_module(module), name)
    except Exception:  # noqa: BLE001 - an answer the harness no longer has is checked by its schema's required keys
        return None


def score(item: Item, message: dict, finish: str) -> tuple[bool, str]:
    """Whether a reply to `item` did what a stage needs: a call to an offered tool whose arguments parse and hold what
    the tool requires, an answer that validates against the stage's schema, not cut at its cap, not looping."""
    from app.models.reply_salvage import repeating

    content = str(message.get("content") or "")
    if finish == "length":
        return False, "cut at its cap"
    # A loop in the reasoning that never ended shows as a reply cut at its cap; one that ended and called a tool did
    # what was asked. The answer looping is the failure (`reply_salvage.repeating`).
    if repeating(content):
        return False, "repeated itself"
    calls = message.get("tool_calls") or []
    if not calls:
        return False, "answered as text"
    offered = {str((t.get("function") or {}).get("name") or ""): t for t in item.tools}
    for call in calls:
        function = call.get("function") or {}
        name = str(function.get("name") or "")
        if name not in offered:
            return False, f"called `{name}`, not offered"
        try:
            arguments = json.loads(function.get("arguments") or "{}")
        except ValueError:
            return False, f"unreadable arguments for `{name}`"
        if not isinstance(arguments, dict):
            return False, f"arguments for `{name}` are not an object"
        required = ((offered[name].get("function") or {}).get("parameters") or {}).get("required") or []
        missing = [key for key in required if key not in arguments]
        if missing:
            return False, f"`{name}` without {', '.join(missing)}"
        if name == item.answer_tool:
            schema = _answer_model(item)
            if schema is not None:
                try:
                    schema.model_validate(arguments)
                except Exception as error:  # noqa: BLE001 - a near miss of its schema is the finding
                    return False, f"answer not in its schema: {str(error).splitlines()[0][:80]}"
    return True, ""


# --- building the set from transcripts --------------------------------------------------------------------------

def scrub(text: str) -> str:
    """`text` without run ids or host paths."""
    out = _RUN_ID.sub("run-0", text)
    for pattern, replacement in _HOST_PATHS:
        out = pattern.sub(replacement, out)
    return out


def leaks(item: Item, hidden_lines: Iterable[str]) -> list[str]:
    """Why `item` may not be a probe: a run id, a host path, or a line of a hidden test it holds; [] when none."""
    text = json.dumps([item.messages, item.tools], default=str)
    found = []
    if _RUN_ID.search(text):
        found.append("a run id")
    if any(pattern.search(text) for pattern, _ in _HOST_PATHS):
        found.append("a host path")
    for line in hidden_lines:
        if line in text:
            found.append(f"a hidden test's line: {line[:60]!r}")
            break
    return found


def hidden_lines(benchmarks: Path) -> list[str]:
    """Every line of every benchmark's hidden tests long enough to mean something, JSON-escaped as it would appear."""
    lines: set[str] = set()
    for path in benchmarks.glob("*/hidden/**/*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line in text.splitlines():
            stripped = line.strip()
            # An import names a test library, which every product's own tests import too; it holds nothing of the
            # hidden tests themselves.
            if len(stripped) >= LEAK_LINE_CHARS and not _AN_IMPORT.match(stripped):
                lines.add(json.dumps(stripped)[1:-1])
    return sorted(lines)


def benchmark_runs(bench: Path, benchmarks: Path) -> dict[str, str]:
    """Run id -> family of the runs scored against a benchmark family's own brief: the only runs whose transcripts
    may become probes (owner 2026-11-27); a brief started by hand, or the owner's own run, has no such record."""
    families = {folder.name for folder in benchmarks.iterdir() if (folder / "brief.md").is_file()}
    out = {}
    for path in bench.glob("run-*.json"):
        try:
            found = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if found.get("benchmark") in families and not found.get("brief_mismatch") and found.get("score") == 1.0:
            out[path.stem] = str(found["benchmark"])
    return out


_ANSWER_MODULES = ("technical_lead", "security_reviewer", "scrum_master", "product_manager", "tools_models",
                   "milestone_reviewer", "specialists", "code_reviewer", "acceptance_reviewer",
                   "architecture_reviewer", "stack_selector", "principal_architect")
#: The workspace readers' schemas, as the filesystem layer offers them.
_READERS = {
    "ls": {"path": {"type": "string"}},
    "read_file": {"file_path": {"type": "string"}, "offset": {"type": "integer"}, "limit": {"type": "integer"}},
    "glob": {"pattern": {"type": "string"}, "path": {"type": "string"}},
    "grep": {"pattern": {"type": "string"}, "path": {"type": "string"}, "glob": {"type": "string"}},
}
_READER_REQUIRES = {"ls": ["path"], "read_file": ["file_path"], "glob": ["pattern"], "grep": ["pattern"]}


def answer_class(name: str) -> str:
    """"module:Class" of the stage answer schema named `name`, or ""."""
    import importlib

    for module in _ANSWER_MODULES:
        try:
            found = getattr(importlib.import_module(f"app.agents.{module}"), name, None)
        except Exception:  # noqa: BLE001
            continue
        if found is not None and hasattr(found, "model_json_schema"):
            return f"app.agents.{module}:{name}"
    return ""


def tool_schemas(names: list[str]) -> list[dict]:
    """The OpenAI-style schema of each tool named, rebuilt from the harness's definitions; an open one where none."""
    import tempfile

    from langchain_core.utils.function_calling import convert_to_openai_tool

    from app.tools import agent_toolkit

    built: dict[str, dict] = {}
    with tempfile.TemporaryDirectory() as root:
        makers = [agent_toolkit.build_artifact_write_tool, agent_toolkit.build_artifact_edit_tool,
                  agent_toolkit.build_line_replace_tool, agent_toolkit.build_artifact_delete_tool,
                  agent_toolkit.build_artifact_move_tool, agent_toolkit.build_validation_tool,
                  agent_toolkit.build_terminal_command_tool, agent_toolkit.build_sprint_history_tool]
        for make in makers:
            try:
                tool = make(root)
                built[tool.name] = convert_to_openai_tool(tool)
            except Exception:  # noqa: BLE001
                continue
        try:
            for tool in agent_toolkit.build_repository_read_tools(root):
                built[tool.name] = convert_to_openai_tool(tool)
        except Exception:  # noqa: BLE001
            pass
    out = []
    for name in names:
        if name in built:
            out.append(built[name])
        elif name in _READERS:
            out.append({"type": "function", "function": {"name": name, "description": f"The workspace's {name}.",
                        "parameters": {"type": "object", "properties": _READERS[name],
                                       "required": _READER_REQUIRES[name]}}})
        elif answer_class(name):
            import importlib

            module, _, cls = answer_class(name).partition(":")
            out.append(convert_to_openai_tool(getattr(importlib.import_module(module), cls)))
        else:
            out.append({"type": "function", "function": {"name": name, "description": "A tool of the workspace.",
                        "parameters": {"type": "object", "properties": {}}}})
    return out


def _calls(raw: Any) -> list[dict]:
    if isinstance(raw, str):
        try:
            raw = ast.literal_eval(raw)
        except (ValueError, SyntaxError):
            return []
    return [call for call in raw or [] if isinstance(call, dict)]


def openai_messages(recorded: list[dict]) -> list[dict]:
    """A transcript request's messages as an OpenAI-style conversation, scrubbed."""
    out = []
    for message in recorded:
        role = {"human": "user", "ai": "assistant"}.get(str(message.get("role")), str(message.get("role")))
        content = message.get("content")
        content = scrub(content if isinstance(content, str) else json.dumps(content, default=str))
        entry: dict[str, Any] = {"role": role, "content": content}
        if role == "assistant":
            calls = [{"id": str(call.get("id") or f"c{n}"), "type": "function",
                      "function": {"name": str(call.get("name") or ""),
                                   "arguments": scrub(json.dumps(call.get("args") or {}))}}
                     for n, call in enumerate(_calls(message.get("tool_calls")))]
            if calls:
                entry["tool_calls"] = calls
        if role == "tool":
            entry["tool_call_id"] = str(message.get("tool_call_id") or "")
        out.append(entry)
    return out


def candidates(records: Iterable[dict], family: str) -> list[tuple[int, Item]]:
    """(reasoning characters of the recorded reply, item) for each request of one transcript whose recorded reply
    passed its own checks and called only offered tools, at most `MOST_CHARACTERS`."""
    from app.models import stage_kinds

    pending: dict[str, dict] = {}
    #: Each stage's whole conversation so far: a request records only what it added and how many it `carried`.
    whole: dict[str, list[dict]] = {}
    out = []
    for record in records:
        stage = str(record.get("stage") or "")
        if record.get("kind") == "model_request":
            carried = int(record.get("carried") or 0)
            whole[stage] = [*whole.get(stage, [])[:carried], *(record.get("messages") or [])]
            pending[stage] = {**record, "messages": whole[stage]}
            continue
        if record.get("kind") != "model_response" or stage not in pending:
            continue
        request = pending.pop(stage)
        names = [str(n) for n in request.get("tools") or []]
        calls = _calls(record.get("tool_calls"))
        if not names or not calls or str(record.get("finish_reason") or "") == "length" or record.get("salvaged"):
            continue
        if any(str(call.get("name")) not in names for call in calls):
            continue
        messages = openai_messages(request.get("messages") or [])
        if len(json.dumps(messages)) > MOST_CHARACTERS:
            continue
        kind = stage_kinds.kind(names, any(m["role"] == "tool" for m in messages))
        answer_tool = next((n for n in names if answer_class(n)), "")
        stage_kind = re.sub(r"(_\d+)+$", "", stage)
        item = Item(id=f"{kind}-{family}-{stage_kind}", kind=kind, family=family, messages=messages,
                    tools=tool_schemas(names), answer=answer_class(answer_tool) if answer_tool else "",
                    answer_tool=answer_tool,
                    notes={"stage": stage_kind, "recorded_output_tokens": (record.get("usage") or {}).get("output_tokens"),
                           "recorded_reasoning_chars": record.get("reasoning_chars"),
                           "recorded_calls": [str(call.get("name")) for call in calls]})
        out.append((int(record.get("reasoning_chars") or 0), item))
    return out


__all__ = ["ITEMS_DIR", "Item", "LEAK_LINE_CHARS", "MOST_CHARACTERS", "benchmark_runs", "candidates", "hidden_lines",
           "leaks", "load", "openai_messages", "score", "scrub", "set_hash", "tool_schemas"]
