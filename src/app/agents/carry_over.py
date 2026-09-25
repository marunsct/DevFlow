"""What a dying stage attempt knows, in a form the next attempt can read.

A stage that produces no structured response is restarted on a fresh
conversation. That is the right move - `_restart_on_a_fresh_conversation`
explains why - but until now it threw away everything the attempt had learned,
and the comment in `workflow.py` said so. Each of three attempts re-read the
same files and re-ran the same commands: 

Measured again on run b0db10b1, where the two stages that spun cost 100 and 80
model calls across their attempts while the fifteen that finished averaged
under ten. The waste is not the failed attempt; it is that the next one starts
blind.

This is deliberately a summary and not a transcript. The reason the attempt is
being restarted is that its conversation was not working, so replaying it would
reproduce the failure - that is the bug `pending_inner_thread_id` being cleared
exists to prevent. What carries over is only what the attempt *established*:
which files it has already seen, which commands it has already run and how they
exited. Facts, not reasoning.

Item 9 of `docs/harness-hardening-plan.md` (B13).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: Files named before the list is truncated. A stage that touched more than
#: this was not held back by not knowing which files exist.
MAX_FILES_NAMED = 12

#: Commands named, most recent last. Enough to show what was tried.
MAX_COMMANDS_NAMED = 8


def _files_already_read(thread_id: str, repo_root: str | None) -> list[str]:
    """The files the dead attempt read, named the way its tools name them.

    `read_digests` is keyed on the resolved absolute path, because that is what
    makes two spellings of one file the same key. A carry-over written from
    those keys hands the next attempt
    `/app/data/workspaces/default/todo-run9-.../app.js`, which no tool here
    accepts - every one of them takes a path relative to the workspace. Seen in
    run 86a60de1, where the note fired five times and named absolute paths each
    time.

    Worse than useless: an absolute path in front of a model is how the invented
    `/project/...` prefix gets invented, which `_the_one_path_it_meant` exists
    to undo.
    """
    from app.agents.stage_memory import recall

    seen = recall(thread_id, "read_digests")
    root = Path(repo_root).resolve() if repo_root else None
    named: list[str] = []
    for path in seen:
        text = str(path)
        if root:
            try:
                text = str(Path(text).resolve().relative_to(root))
            except (ValueError, OSError):
                pass  # Outside the workspace, or unresolvable: name it as it is.
        named.append(text)
    return sorted(set(named))


def _commands_already_run(repo_root: str | None) -> list[tuple[str, Any]]:
    if not repo_root:
        return []
    try:
        from app.tools.sandbox import read_execution_ledger

        entries = read_execution_ledger(repo_root)
    except Exception:  # noqa: BLE001 - a carry-over must never fail a restart
        return []
    ran: list[tuple[str, Any]] = []
    for entry in entries:
        command = entry.get("command") or entry.get("argv")
        if isinstance(command, list):
            command = " ".join(str(part) for part in command)
        if command:
            ran.append((str(command), entry.get("returncode")))
    return ran


def carry_over_note(thread_id: str, repo_root: str | None) -> str:
    """A compact note for the fresh attempt, or "" when there is nothing to say.

    Empty when the dead attempt established nothing - a stage that failed on its
    first call has no facts to pass on, and an empty preamble is one more thing
    for the next attempt to read past.
    """
    try:
        files = _files_already_read(thread_id, repo_root)
        commands = _commands_already_run(repo_root)
    except Exception:  # noqa: BLE001 - never fail a restart over a hint
        logger.debug("Could not build a carry-over note", exc_info=True)
        return ""
    if not files and not commands:
        return ""

    lines = [
        "[Carrying over from your previous attempt at this task, which ended "
        "without a structured response. The conversation is gone; these facts "
        "are not. Do not re-establish them.]",
    ]
    if files:
        shown = files[:MAX_FILES_NAMED]
        more = len(files) - len(shown)
        lines.append(
            "\nFiles you already read, and which have not changed since:\n"
            + "\n".join(f"  {path}" for path in shown)
            + (f"\n  ... and {more} more" if more > 0 else "")
        )
    if commands:
        shown = commands[-MAX_COMMANDS_NAMED:]
        lines.append(
            "\nCommands this stage already ran, with how they exited:\n"
            + "\n".join(
                f"  {command}  -> exit {code}" if code is not None else f"  {command}"
                for command, code in shown
            )
        )
    lines.append(
        "\nRe-reading a file listed above or re-running a command listed above "
        "will return what it returned before. Start from what is here and "
        "write your structured response."
    )
    return "\n".join(lines)


__all__ = ["carry_over_note", "MAX_FILES_NAMED", "MAX_COMMANDS_NAMED"]
