"""A command that only reads a file is a read, decided as `read_file` is (TR.2 for the shell, LF.1525).

Measured on one medium run: a builder needed a 593-line file another work order owned. With `read_file` withheld it
read the file through `run_terminal_command` instead - `head -100`, `head -200`, `cat`, `wc -l`, `sed -n 200,400p`
(refused as "To change a file, use `edit_artifact`"), `sed -n 200,350p` again, `head -100` again, and four Python
one-liners printing slices of its lines, one failing on the path and two asking for the same lines. 49 calls, 22%
failing, 32 tokens read for every one written. Withholding the reader did not stop the reading: each detour cost a
call.

One place, `a_shell_read`, says whether a command only reads a file and which lines: `cat`, `head`, `tail`, `sed -n`
with a range, `awk` with a line range, `less`, `more`, `nl`, `wc`, and inline code that only opens and prints a file
(its forms are the language table's `file_prints`). Such a command is decided as `read_file` is on the same call -
one rule, whatever tool reads. Where the stage's reads are decided file by file (TR.2, LF.1517; thinking off,
LF.1527):

- a file the project memory holds whole and unchanged, or the request quotes whole, is refused by name with where its
  text is (`project_memory.held_read_refusal`);
- lines whose numbered text the conversation still holds are refused the same way (`already_in_the_conversation`);
- lines this stage visit already ran while reading was withheld, or a file or a visit past its bounds, are refused as
  `read_file`'s are (`reads_once_while_withheld`, LF.1577);
- any other file is answered as a ranged read: the window and numbering `read_file` gives, from the file on disk.

Where every read is withheld whole by another rule, it is refused as `read_file` is. Each is recorded as a
`read_while_withheld` with the command tool as its `tool`. With reading not withheld, a shell read runs as any command
does, except one sent again for the same lines while its first answer is still in the conversation: that is answered
from the first, as `read_file`'s repeats are.
"""
from __future__ import annotations

import logging
import os
import posixpath
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

logger = logging.getLogger(__name__)

#: The tool a shell read is sent with.
COMMAND_TOOL = "run_terminal_command"

#: Where the sandbox mounts the workspace; a path under it is the workspace's own.
_MOUNT = "/workspace/"

#: Stage memory: the reads the latest model call's conversation holds.
_HELD = "shell reads held"


@dataclass(frozen=True)
class ShellRead:
    """What a command reads: one workspace file, and which of its lines.

    `offset` is the lines skipped before the first shown, as `read_file` counts it; negative, the file's last
    `-offset` lines (`tail`). `limit` is the lines asked for; 0, from `offset` on, in `read_file`'s window. `counts`:
    the file's counts (`wc`), not its lines.
    """

    path: str
    offset: int = 0
    limit: int = 0
    counts: bool = False

    @property
    def key(self) -> tuple[str, int, int]:
        """The read as `settled_answer` keys a read: the default window spelled 0, however it was asked."""
        from app.agents.workspace_paths import DEFAULT_READ_LINES

        return self.path, self.offset, 0 if self.limit == DEFAULT_READ_LINES else self.limit

    def lines_asked(self) -> str:
        """"lines 200-400", "the last 20 lines", or "" for the whole file."""
        if self.offset < 0:
            return f"the last {-self.offset} lines"
        if not self.limit and not self.offset:
            return ""
        return f"lines {self.offset + 1}-{self.offset + self.limit}" if self.limit else f"lines {self.offset + 1} on"


def _resolved(word: str, working_directory: str) -> str | None:
    """The workspace-relative path `word` names from `working_directory`; None outside the workspace.

    Named from the workspace's root while the command runs in a folder of it - `cat app/requirements.txt` with
    `working_directory` "app" - it is that path, as the sandbox shortens it (measured: the builder above did so for
    every read). Decided on the words alone, so the conversation's reads and a new one are keyed alike.
    """
    word = str(word or "").strip()
    if not word or word.startswith("-"):
        return None
    if word.startswith(_MOUNT):
        word = word[len(_MOUNT):]
    elif word.startswith("/"):
        return None
    here = str(working_directory or "").strip()
    if here.startswith(_MOUNT) or here == _MOUNT.rstrip("/"):
        here = here[len(_MOUNT):]
    here = here.strip("/")
    here = "" if here in ("", ".") else posixpath.normpath(here)
    if here and (word == here or word.startswith(here + "/")):
        joined = posixpath.normpath(word)
    else:
        joined = posixpath.normpath(posixpath.join(here, word)) if here else posixpath.normpath(word)
    if joined in ("", ".") or joined == ".." or joined.startswith("../"):
        return None
    return joined


def _operands(argv: Sequence[str], valued: frozenset[str] = frozenset()) -> tuple[list[str], list[str]] | None:
    """(flags, operands) of `argv[1:]`; a flag in `valued` takes the next word as its value. None for `-` (stdin)."""
    flags: list[str] = []
    operands: list[str] = []
    words = list(argv[1:])
    i = 0
    while i < len(words):
        word = str(words[i])
        if word == "-":
            return None
        if word == "--":
            operands.extend(str(w) for w in words[i + 1:])
            break
        if word.startswith("-"):
            flags.append(word)
            if word in valued and i + 1 < len(words):
                flags.append(str(words[i + 1]))
                i += 1
        else:
            operands.append(word)
        i += 1
    return flags, operands


def _count_of_lines(flags: list[str], default: int) -> int | None:
    """`head`'s or `tail`'s line count: `-20`, `-n 20`, `-n20`, `--lines=20`; `+K` as -K (from line K on)."""
    count: str | None = None
    i = 0
    while i < len(flags):
        flag = flags[i]
        if re.fullmatch(r"-\d+", flag):
            count = flag[1:]
        elif flag == "-n" and i + 1 < len(flags):
            count = flags[i + 1]
            i += 1
        elif re.fullmatch(r"-n[+-]?\d+", flag):
            count = flag[2:]
        elif flag.startswith("--lines="):
            count = flag.split("=", 1)[1]
        elif flag in ("-q", "-v", "--quiet", "--silent", "--verbose"):
            pass
        else:
            return None  # `-c` (bytes), `-f` (follow) and the rest read something else
        i += 1
    if count is None:
        return default
    if re.fullmatch(r"\+\d+", count):
        return -int(count[1:])
    return int(count) if re.fullmatch(r"\d+", count) else None


#: A print-only `sed` script: `200,400p`, `200p`, `200,$p`, with an optional `400q` after it.
_SED_RANGE = re.compile(r"\s*(?P<first>\d+)\s*(?:,\s*(?P<last>\d+|\$))?\s*p\s*(?:;\s*\d+\s*q\s*)?;?\s*")
#: A print-only `awk` program: `NR>=200 && NR<=400`, `NR==200,NR==400`, `NR==200`, each with an optional `{print}`.
_AWK_RANGE = re.compile(
    r"\s*(?:NR\s*>=?\s*(?P<from>\d+)\s*&&\s*NR\s*<=?\s*(?P<to>\d+)|NR\s*==\s*(?P<a>\d+)\s*(?:,\s*NR\s*==\s*(?P<b>\d+))?)"
    r"\s*(?:\{\s*print(?:\s+\$0)?\s*;?\s*\})?\s*"
)
_AWK_WHOLE = re.compile(r"\s*(?:1|\{\s*print(?:\s+\$0)?\s*;?\s*\})\s*")


def _the_interpreter(program: str) -> str:
    """`python3.12` as `python3`, `python3` as itself: the names the language table lists."""
    match = re.fullmatch(r"(python3?)(?:\.\d+)*", program)
    return match.group(1) if match else program


def _an_inline_print(program: str, argv: list[str]) -> tuple[str, int, int] | None:
    """(path as written, offset, limit) of inline code that only prints a file (the language table's `file_prints`)."""
    from app.stacks.languages import file_prints
    from app.tools.sandbox import CODE_AS_A_FILE

    flags = CODE_AS_A_FILE.get(program)
    if not flags or len(argv) != 3 or argv[1] not in flags:
        return None
    for pattern in file_prints(program):
        match = re.fullmatch(pattern, argv[2], re.S)
        if match is None:
            continue
        groups = match.groupdict()
        start = int(groups.get("start") or 0)
        end = groups.get("end")
        if end:
            if int(end) <= start:
                return None
            return match.group("path"), start, int(end) - start
        return match.group("path"), start, 0
    return None


def a_shell_read(command: Any, working_directory: Any = "") -> ShellRead | None:
    """The file a command only reads, and which lines; None for any other command.

    The one place that decides it, for the decision while reading is withheld, the conversation's record of what it
    holds, and the sandbox's refusal of an editor used only to print.
    """
    if not isinstance(command, (list, tuple)) or not command:
        return None
    argv = [str(part) for part in command]
    program = _the_interpreter(os.path.basename(argv[0]))
    here = str(working_directory or "")
    inline = _an_inline_print(program, argv)
    if inline is not None:
        path = _resolved(inline[0], here)
        return ShellRead(path, inline[1], inline[2]) if path else None
    if program in ("cat", "less", "more", "nl", "wc"):
        parsed = _operands(argv, frozenset({"-w", "-s", "-v", "-i", "-b", "-n"}) if program == "nl" else frozenset())
        if parsed is None or len(parsed[1]) != 1:
            return None
        path = _resolved(parsed[1][0], here)
        return ShellRead(path, counts=program == "wc") if path else None
    if program in ("head", "tail"):
        parsed = _operands(argv, frozenset({"-n", "-c"}))
        if parsed is None or len(parsed[1]) != 1:
            return None
        count = _count_of_lines(parsed[0], 10)
        path = _resolved(parsed[1][0], here)
        if count is None or not path:
            return None
        if program == "head":
            return ShellRead(path, 0, count) if count > 0 else None
        if count < 0:  # `tail -n +K`: from line K on
            return ShellRead(path, max(-count - 1, 0), 0)
        return ShellRead(path, -count, count) if count > 0 else None
    if program == "sed":
        parsed = _operands(argv, frozenset({"-e", "--expression"}))
        if parsed is None:
            return None
        flags, operands = parsed
        quiet = any(f in ("-n", "--quiet", "--silent") or re.fullmatch(r"-[nEr]*n[nEr]*", f) for f in flags)
        if not quiet or any(f.startswith(("-i", "--in-place")) for f in flags):
            return None
        scripts = [flags[i + 1] for i, f in enumerate(flags[:-1]) if f in ("-e", "--expression")]
        if not scripts:
            if len(operands) != 2:
                return None
            scripts, operands = [operands[0]], operands[1:]
        if len(scripts) != 1 or len(operands) != 1:
            return None
        match = _SED_RANGE.fullmatch(scripts[0])
        path = _resolved(operands[0], here)
        if match is None or not path:
            return None
        first = int(match.group("first"))
        last = match.group("last")
        if first < 1:
            return None
        if last == "$":
            return ShellRead(path, first - 1, 0)
        last_line = int(last) if last else first
        return ShellRead(path, first - 1, last_line - first + 1) if last_line >= first else None
    if program in ("awk", "gawk", "mawk"):
        parsed = _operands(argv)
        if parsed is None or parsed[0] or len(parsed[1]) != 2:
            return None
        script, operand = parsed[1]
        path = _resolved(operand, here)
        if not path:
            return None
        if _AWK_WHOLE.fullmatch(script):
            return ShellRead(path)
        match = _AWK_RANGE.fullmatch(script)
        if match is None:
            return None
        first = int(match.group("from") or match.group("a"))
        last = int(match.group("to") or match.group("b") or first)
        return ShellRead(path, first - 1, last - first + 1) if first >= 1 and last >= first else None
    return None


def read_key(args: Any) -> tuple[str, int, int] | None:
    """The read a `run_terminal_command` call's arguments make, keyed as `settled_answer` keys a read; None for a
    command that is not a read of a file's lines."""
    args = args if isinstance(args, dict) else {}
    read = a_shell_read(args.get("command"), args.get("working_directory") or "")
    return None if read is None or read.counts else read.key


def as_read_arguments(read: ShellRead) -> dict[str, int]:
    """The `offset` and `limit` a `read_file` of the same lines is sent with."""
    from app.agents.workspace_paths import DEFAULT_READ_LINES

    return {"offset": max(read.offset, 0), "limit": read.limit or DEFAULT_READ_LINES}


def read_instead(argv: Sequence[str]) -> str:
    """What to send instead of a refused command that only prints a file's lines, or "" when it is not one.

    Measured: `sed -n 200,400p routes.py` was refused with "To change a file, use `edit_artifact`" - it changed
    nothing - and sent again for other lines.
    """
    read = a_shell_read(list(argv))
    if read is None or read.counts:
        return ""
    from app.agents.workspace_paths import DEFAULT_READ_LINES

    shown = " ".join(str(part) for part in argv)
    what = read.lines_asked()
    if read.offset < 0:
        how = "`read_file` reads them by `offset` and `limit`"
    elif read.limit:
        how = f"`read_file` with `offset` {read.offset} and `limit` {read.limit} reads them"
    elif read.offset:
        how = f"`read_file` with `offset` {read.offset} reads them, {DEFAULT_READ_LINES} lines at a time"
    else:
        how = "`read_file` reads it"
    return f"`{shown}` only reads {what + ' of ' if what else ''}`{read.path}`, changing nothing: {how}, numbered."


def answered_as_a_read(repo_root: str | Path, read: ShellRead) -> str | None:
    """The lines `read` asks for, as `read_file` gives them: its window, numbered as it numbers them; None when the
    file is not a text file there (the command then runs and says so itself)."""
    from deepagents.backends.utils import format_content_with_line_numbers

    from app.agents.workspace_paths import DEFAULT_READ_LINES

    path = Path(repo_root) / read.path
    try:
        if not path.is_file():
            return None
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    total = len(lines)
    offset = max(total + read.offset, 0) if read.offset < 0 else read.offset
    window = min(read.limit or DEFAULT_READ_LINES, DEFAULT_READ_LINES)
    shown = lines[offset:offset + window]
    if not shown:
        return (f"`{read.path}` has {total} lines; nothing is there from line {offset + 1}. This command only reads "
                "it, so it was answered as `read_file` answers that read.")
    last = offset + len(shown)
    note = (f"[This command only reads `{read.path}`, so it was answered as `read_file` answers it: lines "
            f"{offset + 1}-{last} of {total}, numbered.")
    asked_last = offset + (read.limit or total - offset)
    if last < min(asked_last, total):
        note += f" Lines {last + 1}-{min(asked_last, total)} are not shown: ask for them by range."
    return note + "]\n" + format_content_with_line_numbers(shown, start_line=offset + 1)


def _remember(messages: list[Any]) -> None:
    """The reads the conversation this model call sends holds, for the calls it makes (`_decided`)."""
    from app.agents.settled_answer import reads_in_the_conversation
    from app.agents.stage_memory import store

    kept = store(_HELD, {})
    kept["reads"] = sorted(reads_in_the_conversation(messages))
    kept["shell"] = sorted(reads_in_the_conversation(messages, shell_only=True))


def _held(which: str) -> set[tuple]:
    from app.agents.stage_memory import store

    return {tuple(read) for read in store(_HELD, {}).get(which) or ()}


def _per_file() -> set[str]:
    """The read tools the stage's latest call decides file by file (TR.2, LF.1527)."""
    from app.agents.stage_memory import store

    return set(store("withheld tools", {}).get("per_file") or ())


#: A command that only reads, while every read is withheld: the same refusal `read_file` gets, by its words, so the
#: guards that count refused calls count it.
WITHHELD_WHOLE_REFUSAL = (
    "Refusing: this command only reads `{path}`, and reading is withheld at this point of the stage and was not run, "
    "whichever tool reads. Use what this conversation already holds."
)


def _decided(call: dict, repo_root: str) -> Any:
    """The answer to a command call that only reads a file, or None for the command to run as sent."""
    from langchain_core.messages import ToolMessage

    from app.agents import withheld_records
    from app.agents.settled_answer import READ_TOOLS, already_in_the_conversation, withheld_now

    args = call.get("args") if isinstance(call.get("args"), dict) else {}
    read = a_shell_read(args.get("command"), args.get("working_directory") or "")
    if read is None:
        return None
    withheld = withheld_now()
    if COMMAND_TOOL in withheld:
        return None  # refused whole where it is withheld
    call_id = str(call.get("id") or "")

    def refused(text: str) -> ToolMessage:
        return ToolMessage(content=text, tool_call_id=call_id, name=COMMAND_TOOL, status="error")

    reading_withheld = withheld & READ_TOOLS
    if not reading_withheld:
        # The same lines asked again by a command while its first answer is still here: answered from the first.
        if not read.counts and read.key in _held("shell"):
            return refused(already_in_the_conversation(read.path))
        return None
    if not reading_withheld & _per_file():
        # Withheld whole by another rule (its last calls, a stall, the notices ignored): refused as `read_file` is.
        withheld_records.noted_read(withheld_records.WITHHELD_WHOLE, read.path, COMMAND_TOOL)
        return refused(WITHHELD_WHOLE_REFUSAL.format(path=read.path))
    from app.agents.project_memory import held_read_refusal

    held = held_read_refusal(repo_root, read.path, as_read_arguments(read))
    if held is not None:
        withheld_records.noted_read(held[1], read.path, COMMAND_TOOL)
        return refused(held[0])
    if not read.counts and read.key in _held("reads"):
        withheld_records.noted_read(withheld_records.IN_THE_CONVERSATION, read.path, COMMAND_TOOL)
        return refused(already_in_the_conversation(read.path))
    if not read.counts:
        # Lines this visit already ran while withheld, or past the bounds: refused whatever tool reads (LF.1577).
        from app.agents import reads_once_while_withheld

        again = reads_once_while_withheld.refusal(*read.key)
        if again is not None:
            withheld_records.noted_read(again[1], read.path, COMMAND_TOOL)
            return refused(again[0])
    withheld_records.noted_read(withheld_records.RAN, read.path, COMMAND_TOOL)
    if read.counts:
        return None
    answer = answered_as_a_read(repo_root, read)
    return None if answer is None else ToolMessage(content=answer, tool_call_id=call_id, name=COMMAND_TOOL)


def build_shell_read_middleware(repo_root: str) -> Any:
    """Middleware deciding a command that only reads a file as a read (LF.1525). Inside the path rewrite, so it sees
    the arguments the command tool will run; inside the project memory, which it asks what is held."""
    from langchain.agents.middleware import AgentMiddleware

    class ShellReadMiddleware(AgentMiddleware):
        def wrap_model_call(self, request: Any, handler: Any) -> Any:
            try:
                messages = getattr(request, "messages", None)
                if isinstance(messages, list):
                    _remember(messages)
            except Exception:  # noqa: BLE001 - then nothing is known held, and reads are decided as they come
                logger.debug("Could not note the reads a conversation holds", exc_info=True)
            return handler(request)

        def wrap_tool_call(self, request: Any, handler: Any) -> Any:
            call = getattr(request, "tool_call", None) or {}
            if call.get("name") != COMMAND_TOOL:
                return handler(request)
            try:
                answer = _decided(call, repo_root)
            except Exception:  # noqa: BLE001 - the command runs as it was sent
                logger.debug("Could not decide a command that reads", exc_info=True)
                answer = None
            return handler(request) if answer is None else answer

    return ShellReadMiddleware()


__all__ = [
    "COMMAND_TOOL", "ShellRead", "a_shell_read", "answered_as_a_read", "as_read_arguments",
    "build_shell_read_middleware", "read_instead", "read_key",
]
