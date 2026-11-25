"""What the harness repairs in a lead's plan itself, before anything is sent back (plan PA.6).

Measured on a medium run: the lead made 12 plans in 4 visits. The reasons sent back were "No `testing` work order"
(a custom setup has no stack contract, so `work_orders.with_a_testing_work_order` could not name the test files) and
"there is no shell here, so `&&` ... do nothing" - both mechanical - and one plan had an empty title. Each send-back
was a fresh conversation of about 147,000 characters.

Here, always on:
- `declared_test_layout`: a custom setup's own declaration (`stack-setup.json`) names the unit-test folder, file
  pattern and command when no contract was recorded for it, so the testing work order can be written from it;
- `with_joined_commands_split`: a verification line of commands joined by `&&` or `;` becomes the commands it joins,
  each on its own line; `cd <folder> && <command>` becomes `<command>`, with the folder it runs in said on the work
  order, since a work order's command already runs in the project directory and the command tool takes a folder;
- `with_empty_titles_filled`: an empty title is the first line of the work order's description.

What still needs judgement goes back to the lead as one more turn of its own conversation (`graph.nodes.building`).
"""
from __future__ import annotations

import json
import logging
import re
import shlex
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import Any

logger = logging.getLogger(__name__)

#: The file a custom setup declares its runners in (`app.stacks.custom_setup.DECLARATION_FILE`).
_DECLARATION = "stack-setup.json"
#: How long a title taken from a description may be.
_TITLE_LENGTH = 70


def _project(repo_root: str | Path | None) -> str:
    from app.analysis.work_orders import _pinned_project_directory

    return _pinned_project_directory(repo_root)


def _argv(value: Any) -> tuple[str, ...]:
    """A declared command as its words: a list of strings, one string, or one list inside a list."""
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], (list, str)):
        value = value[0]
    if isinstance(value, str):
        try:
            return tuple(shlex.split(value))
        except ValueError:
            return ()
    if isinstance(value, list) and value and all(isinstance(part, str) and part for part in value):
        return tuple(value)
    return ()


def declared_test_layout(repo_root: str | Path | None) -> tuple[Any, dict[str, Any]] | None:
    """(a pack-like layout, {}) from the custom setup's `stack-setup.json`, or None when there is none to read.

    Read leniently - only the unit-test folder, its file-name pattern and the unit-test command - since a setup that
    was not proven is left to the agents, and its test layout is still the one they write tests in. Never raises.
    """
    if not repo_root:
        return None
    root = Path(repo_root)
    project = _project(repo_root)
    for folder in ([root / project] if project else []) + [root]:
        try:
            data = json.loads((folder / _DECLARATION).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        unit_dir = str(data.get("unit_dir") or "").strip().replace("\\", "/").removeprefix("./").strip("/")
        if unit_dir == folder.name:
            unit_dir = "."
        pattern = str(data.get("unit_pattern") or "").strip()
        if not unit_dir or "*" not in pattern or "/" in pattern or ".." in PurePosixPath(unit_dir).parts:
            continue
        return SimpleNamespace(unit_dir=unit_dir, unit_pattern=pattern, unit_test=_argv(data.get("unit_test")),
                               unit_test_names=(), unit_mirrors=()), {}
    return None


# --- joined commands --------------------------------------------------------------------------------------------------

#: Shell that only quiets a command or ignores its failure: what is left is the command itself.
_QUIETED = re.compile(r"\s+(?:\d?>{1,2}\s*(?:/dev/null|&\d)|&>\s*/dev/null)")
_OR_ELSE = re.compile(r"\s+\|\|\s+.*$")
_CD = re.compile(r"^\s*cd\s+(['\"]?)([^'\"&;|<>]+?)\1\s*$")


def _parts(command: str) -> list[str]:
    """`command` split at each `&&` and `;` outside quotes."""
    parts, current, quote, at = [], "", "", 0
    while at < len(command):
        character = command[at]
        if quote:
            quote = "" if character == quote else quote
        elif character in "'\"":
            quote = character
        elif command.startswith("&&", at) or character == ";":
            parts.append(current)
            current = ""
            at += 2 if character == "&" else 1
            continue
        current += character
        at += 1
    parts.append(current)
    return parts


def _folder_inside(target: str, current: str, root: str, project: str) -> str | None:
    """Where `cd target` from `current` leads, named from the project directory ("" for the project itself), or None
    when it leaves the project."""
    target = target.strip().rstrip("/") or "/"
    if root and target.startswith(root.rstrip("/") + "/"):
        target = target[len(root.rstrip("/")) + 1:]
    elif target.startswith("/"):
        # The workspace as an agent sees it is rooted at "/": only the project directory under it is the project.
        target = target.lstrip("/")
        if not (project and (target == project or target.startswith(f"{project}/"))):
            return None
    if project and (target == project or target.startswith(f"{project}/")):
        target = target[len(project):].lstrip("/")
        current = ""
    joined = PurePosixPath(current, target) if current else PurePosixPath(target)
    parts: list[str] = []
    for part in joined.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def split_command(command: str, repo_root: str | Path | None = None) -> list[tuple[str, str]] | None:
    """(command, the folder it runs in - "" for the project directory) for each command `command` joins; None when it
    joins nothing the harness can split - a single command, or a `cd` that leaves the project."""
    text = str(command or "").strip().strip("`")
    parts = _parts(text)
    if len(parts) < 2 and not _OR_ELSE.search(text) and not _QUIETED.search(text):
        return None
    root = str(Path(repo_root)) if repo_root else ""
    project = _project(repo_root)
    folder = ""
    split: list[tuple[str, str]] = []
    for part in parts:
        going = _CD.match(part)
        if going:
            folder = _folder_inside(going.group(2), folder, root, project)
            if folder is None:
                return None
            continue
        cleaned = re.sub(r"\s*&\s*$", "", _OR_ELSE.sub("", _QUIETED.sub("", part))).strip()
        if cleaned:
            split.append((cleaned, folder))
    return split or None


def with_joined_commands_split(milestone: Any, repo_root: str | Path | None) -> Any:
    """The plan with each verification line that joins commands written as the commands it joins. Never raises.

    A command that runs in a folder of the project says so on its work order: the command tool takes the folder.
    """
    try:
        tasks = list(getattr(milestone, "delegated_tasks", None) or [])
        changed = False
        rewritten = []
        for task in tasks:
            commands = [str(c) for c in getattr(task, "verification", None) or []]
            kept: list[str] = []
            elsewhere: list[str] = []
            for command in commands:
                split = split_command(command, repo_root)
                if split is None:
                    kept.append(command)
                    continue
                for one, folder in split:
                    kept.append(one)
                    if folder:
                        elsewhere.append(f"`{one}` runs in `{folder}/` of the project directory")
            if kept != commands:
                changed = True
                update: dict[str, Any] = {"verification": kept}
                if elsewhere:
                    description = str(getattr(task, "task_description", "") or "")
                    update["task_description"] = (
                        f"{description}\n\nWhere its verification commands run: " + "; ".join(elsewhere)
                        + " (the command tool's `working_directory`)."
                    )
                task = task.model_copy(update=update)
            rewritten.append(task)
        return milestone.model_copy(update={"delegated_tasks": rewritten}) if changed else milestone
    except Exception:  # noqa: BLE001 - the readiness check still reports it
        logger.debug("Could not split the plan's joined commands", exc_info=True)
        return milestone


def with_empty_titles_filled(milestone: Any) -> Any:
    """The plan with each work order that has no title named by the first line of its description. Never raises."""
    try:
        tasks = list(getattr(milestone, "delegated_tasks", None) or [])
        changed = False
        filled = []
        for task in tasks:
            if not str(getattr(task, "title", "") or "").strip():
                first = next((line.strip() for line in str(getattr(task, "task_description", "") or "").splitlines()
                              if line.strip()), "")
                if first:
                    title = first if len(first) <= _TITLE_LENGTH else first[:_TITLE_LENGTH].rsplit(" ", 1)[0] + "..."
                    task = task.model_copy(update={"title": title})
                    changed = True
            filled.append(task)
        return milestone.model_copy(update={"delegated_tasks": filled}) if changed else milestone
    except Exception:  # noqa: BLE001 - a plan without a title still dispatches
        return milestone


def repaired(milestone: Any, repo_root: str | Path | None) -> Any:
    """The plan with every mechanical repair of this module made."""
    return with_empty_titles_filled(with_joined_commands_split(milestone, repo_root))


__all__ = ["declared_test_layout", "repaired", "split_command", "with_empty_titles_filled",
           "with_joined_commands_split"]
