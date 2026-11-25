"""What the harness itself knows of a stage's work, kept beside its work note and checked against it (LF.1466).

The work note (PA.2) is written by the summariser from the latest part of a stage's conversation. Measured on one
medium run, a backend builder's eight notes in forty calls: note 2 recorded a failed write as the state of a file the
next reply wrote correctly, and notes 3 to 8 carried "resolve the error at line 301" forward - from note 4 at line 301
of a file of 276 lines; notes 5 to 8 said "Changed: None" while the harness's own line under each named five files
written; note 4 recorded what the command tool refuses and note 6 dropped it, after which the stage sent the same
refused shape three more times.

So the harness keeps what it can know from the tool calls - the files written, the commands run with their exit
codes, each refusal a tool gave - and hands it to the summariser and to the stage, whatever the note says; and before
a note is kept, a `path:line` past its file's end is marked so, and a path that is not in the workspace is said not to
be.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

#: The most refusals and commands the ledger keeps, the latest last.
MOST_REFUSALS = 12
MOST_COMMANDS = 10
#: The most of one refusal kept: its first sentence, within this.
MOST_REFUSAL_CHARACTERS = 240
MOST_COMMAND_CHARACTERS = 160

#: A tool's refusal, as the harness's tools say one: a JSON `error`, or a text that opens by refusing.
_REFUSING = re.compile(r"^\s*(?:Refusing\b|Refused\b|\[?An earlier call was refused\b)", re.I)
_A_SENTENCE_END = re.compile(r"(?<=[.!?])\s")


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(b.get("text") or "") if isinstance(b, dict) else str(b) for b in content)
    return str(content or "")


def _first_sentence(text: str, most: int) -> str:
    text = " ".join(str(text or "").split())
    parts = _A_SENTENCE_END.split(text, 1)
    first = parts[0] if parts else text
    return first if len(first) <= most else first[:most].rstrip() + " ..."


def _json(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped.startswith("{"):
        return None
    try:
        found = json.loads(stripped)
    except ValueError:
        return None
    return found if isinstance(found, dict) else None


def refusal_of(content: Any) -> str:
    """The first sentence of a tool's refusal, or "" when `content` is no refusal."""
    text = _text(content)
    found = _json(text)
    if found is not None and isinstance(found.get("error"), str) and found["error"].strip():
        return _first_sentence(found["error"], MOST_REFUSAL_CHARACTERS)
    if _REFUSING.match(text):
        return _first_sentence(text.lstrip("[ "), MOST_REFUSAL_CHARACTERS)
    return ""


#: The tools that write a file: a refusal of one is about what was sent, and a later write of the file settles it.
_WRITING_TOOLS = frozenset({"write_artifact", "edit_artifact", "replace_lines", "replace_approved_lines"})
_PATH_ARGUMENTS = ("relative_path", "path", "file_path")


def settled(refused: list[str], written: list[str]) -> list[str]:
    """`refused` less each refusal naming a file in `written`: written since, what was refused is no longer so."""
    return [r for r in refused if not any(path and path in r for path in written)]


def refusals(messages: list[Any]) -> list[str]:
    """Each distinct refusal the tools gave in `messages`, in order, less a write's refusal the stage wrote the file
    after: measured, a refused write's "error at line 301" was carried as the file's state long after the next reply
    wrote it without the error."""
    paths: dict[str, str] = {}
    for message in messages:
        for call in getattr(message, "tool_calls", None) or []:
            if call.get("name") in _WRITING_TOOLS:
                args = call.get("args") or {}
                paths[str(call.get("id") or "")] = next((str(args[k]) for k in _PATH_ARGUMENTS if args.get(k)), "")
    found: list[str] = []
    for message in messages:
        if getattr(message, "type", None) != "tool":
            continue
        said = refusal_of(getattr(message, "content", ""))
        path = paths.get(str(getattr(message, "tool_call_id", "") or ""), "")
        if said:
            if said not in found:
                found.append(said)
        elif path:
            found = settled(found, [path])
    return found


def commands(messages: list[Any]) -> list[str]:
    """Each command the stage ran in `messages` with its exit code, as "`command` (in `folder`): exit N"."""
    results = {str(getattr(m, "tool_call_id", "")): _text(getattr(m, "content", ""))
               for m in messages if getattr(m, "type", None) == "tool"}
    found: list[str] = []
    for message in messages:
        for call in getattr(message, "tool_calls", None) or []:
            if call.get("name") != "run_terminal_command":
                continue
            args = call.get("args") or {}
            command = args.get("command")
            shown = " ".join(map(str, command)) if isinstance(command, list) else str(command or "")
            if not shown.strip():
                continue
            shown = shown if len(shown) <= MOST_COMMAND_CHARACTERS else shown[:MOST_COMMAND_CHARACTERS] + " ..."
            folder = str(args.get("working_directory") or "").strip()
            result = _json(results.get(str(call.get("id") or ""), "")) or {}
            if isinstance(result.get("error"), str):
                ended = "refused, not run"
            elif "returncode" in result:
                ended = f"exit {result['returncode']}"
            else:
                ended = "no exit code"
            found.append(f"`{shown}`" + (f" (in `{folder}`)" if folder else "") + f": {ended}")
    return found


def merged(earlier: list[str] | None, later: list[str], most: int) -> list[str]:
    """`earlier` then `later` without repeats, the latest `most` kept."""
    out = [str(e) for e in earlier or []]
    for item in later:
        if item in out:
            out.remove(item)
        out.append(item)
    return out[-most:]


#: A path the note names, with a line or a range: `routes/auth.py:301`, `app.py:1-80`, `routes/auth.py` (line 301).
_PATH_AND_LINE = re.compile(r"`([\w./-]+\.[A-Za-z0-9]+)(?::(\d+)(?:-(\d+))?)?`"
                            r"(?:[ \t]*\(?(?:at[ \t]+)?lines?[ \t]+(\d+)(?:-(\d+))?\)?)?")


def _workspace_files(repo_root: str | Path) -> dict[str, Path]:
    from app.agents.project_memory import current

    root = Path(repo_root)
    return {path: root / path for path in current(root)}


def _the_files(named: str, files: dict[str, Path]) -> list[str]:
    """The workspace paths `named` may be: itself, else each path it is the end of."""
    named = named.lstrip("./")
    if named in files:
        return [named]
    return [path for path in files if path.endswith("/" + named)]


def checked(note: str, repo_root: str | Path | None) -> str:
    """`note` with each `path:line` past the end of its file said to be, and each path naming no file in the workspace
    said not to be there; `note` itself without a workspace. Never raises."""
    if not note or repo_root is None or not Path(repo_root).is_dir():
        return note
    try:
        files = _workspace_files(repo_root)
        lines: dict[str, int] = {}

        def said(match: re.Match[str]) -> str:
            named = match.group(1)
            start, end = (match.group(2), match.group(3)) if match.group(2) else (match.group(4), match.group(5))
            if "/" not in named and start is None:
                return match.group(0)
            candidates = _the_files(named, files)
            if not candidates:
                if "/" not in named or (Path(repo_root) / named.lstrip("/")).exists():
                    return match.group(0)
                return match.group(0) + " [checked by the harness: no such file is in the workspace now]"
            if start is None or len(candidates) > 1:
                return match.group(0)
            path = candidates[0]
            if path not in lines:
                try:
                    lines[path] = len(files[path].read_text(encoding="utf-8").splitlines())
                except (OSError, UnicodeDecodeError):
                    return match.group(0)
            last = int(end or start)
            if last > lines[path]:
                return (match.group(0) + f" [checked by the harness: `{path}` has {lines[path]} lines now, so line "
                        f"{last} is not in it - do not go on from this line]")
            return match.group(0)

        return _PATH_AND_LINE.sub(said, note)
    except Exception:  # noqa: BLE001 - the note as written
        return note


_SECTION = re.compile(r"^## +(\w+)[^\n]*\n", re.M)


def with_every_file_written(note: str, written: list[str]) -> str:
    """`note` whose Changed section names every file in `written` (the stage's own writes, from its tool calls): a
    file the note leaves out is added under it, and a "None" there is replaced. `note` itself without one."""
    if not note or not written:
        return note
    heads = list(_SECTION.finditer(note))
    changed = next((i for i, m in enumerate(heads) if m.group(1).lower() == "changed"), None)
    if changed is None:
        return note
    start = heads[changed].end()
    end = heads[changed + 1].start() if changed + 1 < len(heads) else len(note)
    body = note[start:end]
    missing = [path for path in written if path not in body and path.rsplit("/", 1)[-1] not in body]
    if not missing:
        return note
    kept = "\n".join(line for line in body.strip("\n").splitlines()
                     if line.strip().lstrip("-* ").strip().rstrip(".").lower() != "none")
    added = "\n".join(f"- `{path}`: written by this stage (from its own tool calls; read the file for what it now "
                      "holds)" for path in missing)
    new_body = ((kept + "\n") if kept.strip() else "") + added + "\n\n"
    return note[:start] + new_body + note[end:].lstrip("\n")


def for_the_summariser(written: list[str], written_now: list[str], refused: list[str], ran: list[str]) -> str:
    """The ledger as the summariser is handed it; "" when there is nothing in it."""
    parts = []
    if written:
        parts.append("Files this stage has written or changed so far, from its own tool calls (name each under Changed): "
                     + ", ".join(f"`{p}`" for p in written) + ".")
    if written_now:
        parts.append("Of those, written in the part of the work below: " + ", ".join(f"`{p}`" for p in written_now)
                     + ". An item of the earlier note naming one of them may be done: keep it under Left only if this "
                     "part shows it is not.")
    if refused:
        parts.append("What the tools refused, which the stage must not send again (keep each under Found):\n"
                     + "\n".join(f"- {r}" for r in refused))
    if ran:
        parts.append("Commands the stage ran, with how each ended:\n" + "\n".join(f"- {c}" for c in ran))
    return "\n\n".join(parts)


def for_the_stage(refused: list[str], ran: list[str]) -> str:
    """The ledger's lines under a summary, for the stage itself; "" when there is nothing in it."""
    parts = []
    if refused:
        parts.append("The tools refused these earlier in this stage; do not send them again:\n"
                     + "\n".join(f"- {r}" for r in refused))
    if ran:
        parts.append("Commands this stage has run, with how each ended (the latest last):\n"
                     + "\n".join(f"- {c}" for c in ran))
    return "\n\n".join(parts)


__all__ = ["MOST_COMMANDS", "MOST_REFUSALS", "checked", "commands", "for_the_stage", "for_the_summariser", "merged",
           "refusal_of", "refusals", "settled", "with_every_file_written"]
