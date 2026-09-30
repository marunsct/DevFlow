"""Check the commands a plan tells a specialist to run, before anyone runs them.

A technical lead writes a work order for someone else to follow, and a
specialist follows it. When the order names a command this sandbox will not
run, every specialist handed it fails the same way.

Observed on one run: the lead ended three of its tasks with "MANDATORY
VERIFICATION: ... run `node -e "require('fs').readFileSync(...)"`". The sandbox
refuses inline code for every interpreter, so four specialist stages sent that
command, were refused, and spent a call recovering - one of them twice. Nothing
was wrong with the specialists; they did what the plan said.

So each command a task names is put through the sandbox's own
`validate_command` for the role that will run it, and a refusal is written
onto the task where the specialist will read it. It uses the sandbox's policy
rather than a list of its own, so it is exactly as language-agnostic as that
policy, and it never refuses a plan - the plan is still right about what to
build.
"""
from __future__ import annotations

import os
import re
import shlex
from pathlib import Path
from typing import Any, Iterable

#: An inline code span, `like this`, or one line inside a fenced block.
_INLINE = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")
_FENCE = re.compile(r"```[^\n]*\n(.*?)```", re.S)
#: What a shell would join or redirect, and this sandbox has no shell to do.
_SHELL_JOIN = re.compile(r"\s(?:&&|\|\||;|\|)\s")
_REDIRECT = re.compile(r"^\d?(?:>>?|<)(?:&\d|\S*)$")


def _known_programs() -> frozenset[str]:
    """Every program the sandbox has an opinion about, in any role or stack."""
    from app.tools import sandbox

    known: set[str] = set(sandbox.COMMON_EXECUTABLES)
    for group in (sandbox.ROLE_EXECUTABLES, sandbox.TOOLCHAINS):
        for programs in group.values():
            known |= set(programs)
    return frozenset(known)


def _spans(text: str) -> Iterable[str]:
    """The command-like spans in `text`: inline code and fenced lines."""
    for block in _FENCE.findall(text):
        for line in block.splitlines():
            if line.strip():
                yield line.strip().lstrip("$ ").strip()
    for span in _INLINE.findall(_FENCE.sub("", text)):
        yield span.strip().lstrip("$ ").strip()


def _commands_in(span: str) -> tuple[list[list[str]], bool]:
    """Each command a span holds as argv, and whether it leaned on a shell."""
    pieces = _SHELL_JOIN.split(f" {span} ")
    shell = len(pieces) > 1
    commands: list[list[str]] = []
    for piece in pieces:
        try:
            argv = shlex.split(piece)
        except ValueError:
            continue
        kept = [part for part in argv if not _REDIRECT.match(part)]
        shell = shell or len(kept) != len(argv)
        if kept:
            commands.append(kept)
    return commands, shell


def commands_the_sandbox_would_refuse(
    text: str, role_name: str, repo_root: str | Path | None = None
) -> list[str]:
    """One sentence per command in `text` this role would be refused. Never raises."""
    try:
        from app.tools.sandbox import CommandNotAllowed, validate_command

        known = _known_programs()
    except Exception:  # noqa: BLE001 - no sandbox policy, nothing to check against
        return []
    notes: list[str] = []
    seen: set[str] = set()
    for span in _spans(text):
        commands, shell = _commands_in(span)
        commands = [argv for argv in commands if os.path.basename(argv[0]) in known]
        if not commands or span in seen:
            continue
        seen.add(span)
        reasons: list[str] = []
        for argv in commands:
            try:
                validate_command(argv, role_name, repo_root)
            except CommandNotAllowed as refused:
                reasons.append(" ".join(str(refused).split())[:400])
            except Exception:  # noqa: BLE001 - an unreadable command is not a refusal
                continue
        if shell:
            reasons.append(
                "There is no shell here, so `&&`, `||`, `|`, `;` and redirections "
                "do nothing: run each command as its own call, without them."
            )
        if reasons:
            notes.append(f"`{span}` will not run as written. " + " ".join(reasons))
    return notes


def with_refused_commands_noted(milestone: Any, repo_root: str | Path | None) -> Any:
    """The milestone plan, with each task told which of its commands will be refused.

    Returns the plan unchanged when nothing would be refused, and never raises:
    a check on the plan must not cost the plan.
    """
    try:
        tasks = list(getattr(milestone, "delegated_tasks", None) or [])
        changed = False
        noted = []
        for task in tasks:
            role = str(getattr(task, "specialist_role", "") or "")
            text = str(getattr(task, "task_description", "") or "")
            criteria = "\n".join(str(c) for c in getattr(task, "acceptance_criteria", None) or [])
            notes = commands_the_sandbox_would_refuse(
                f"{text}\n{criteria}", f"{role}_specialist", repo_root
            )
            if notes:
                changed = True
                task = task.model_copy(update={
                    "task_description": text + "\n\nChecked against this sandbox before "
                    "you started: " + " ".join(notes)
                })
            noted.append(task)
        return milestone.model_copy(update={"delegated_tasks": noted}) if changed else milestone
    except Exception:  # noqa: BLE001
        return milestone


__all__ = ["commands_the_sandbox_would_refuse", "with_refused_commands_noted"]
