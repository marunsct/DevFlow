"""A language service's import finding that the fixer's own run showed false: a suspected false finding, not a
rewrite (LF.1401, the rest).

Measured on a medium run: the language service raised `"settings" is unknown import symbol` (and `"RefreshToken"`,
`"User"`) against a router. Its fixer read the module, ran `python -c "from app.config import settings; ..."` and
then `python -c "from app.routers.auth import router; from app.config import settings; print('All imports resolve
OK')"` - both exited 0 and printed what the import loaded - wrote a regression test, which was reverted for
importing the same names, and gave up. What the run measures (`checker_contradicted`, LF.1455) holds only the suite's
and the tests' outcome, so the finding was still "this fails when the code runs", and the rewrite after the
surrender was sent at a file whose imports work.

So after a surrender, the fixer's own commands of this attempt are read from the live transcript (`shown_false`): a
command that exited 0 and imports the name the finding says is missing, or the module the finding is in, loaded it.
Such a finding is not rewritten. It is recorded in the check findings with the file's content as it was
(`recorded`), and while that file is unchanged the gate words it as the language service's, a suspected false finding
of minor severity, as it does one the measurement contradicts (`checker_contradicted.contradicted`). Nothing here
names a language: an import is read by the words languages write one with. Never raises.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

#: The tools that run a command, whose results say how it exited.
COMMAND_TOOLS = frozenset({"run_terminal_command", "run_validation"})
#: The check such a finding is recorded under (`acceptance.check_findings`).
CHECK = "language service, shown false by its fixer's run"
#: The words a line of code imports with, in the languages the language service reads.
_IMPORTS = re.compile(r"\b(?:import|from|require|use|using|include)\b")
#: A language-service defect's first line: `<file> line N: <message> - this fails when the code runs.`
_A_FINDING = re.compile(r"^(?P<file>\S+) line [\d, ]+: (?P<message>.+?) - this fails when the code runs\.")


def _finding(description: str) -> tuple[str, str] | None:
    from app.analysis.checker_contradicted import is_about_an_import

    found = _A_FINDING.match(str(description or "").strip())
    if found is None or not is_about_an_import(found.group("message")):
        return None
    return found.group("file"), found.group("message")


def _module_names(relative: str) -> list[str]:
    """The ways code names the module of `relative`: `app.routers.auth` and `routers/auth` for
    `<project>/backend/app/routers/auth.py`, two parts or more of its path without its suffix."""
    parts = list(PurePosixPath(relative).with_suffix("").parts)
    found = []
    for start in range(len(parts) - 1):
        tail = parts[start:]
        found.extend([".".join(tail), "/".join(tail)])
    return found


def _exited_zero(content: Any) -> bool:
    try:
        result = json.loads(content) if isinstance(content, str) else dict(content or {})
    except (ValueError, TypeError):
        return False
    return isinstance(result, dict) and "error" not in result and str(result.get("returncode")) == "0"


def shown_false(run_id: str | None, stage: str, since: str, description: str) -> str:
    """What in the fixer's own attempt (stage `stage`, since `since`) shows an import finding false: a command that
    exited 0 and imports its name or its module; "" when none did, or the defect is no import finding."""
    try:
        finding = _finding(description)
        if finding is None or not run_id or not stage:
            return ""
        relative, message = finding
        from app.analysis.language_service import the_missing_name
        from app.observability.transcript import read_live

        name = the_missing_name(message)
        modules = _module_names(relative)
        calls: dict[str, str] = {}
        for entry in read_live(run_id, {"tool_call", "tool_result"}):
            if entry.get("stage") != stage or str(entry.get("at") or "") < str(since or ""):
                continue
            if str(entry.get("tool") or "") not in COMMAND_TOOLS:
                continue
            if entry.get("kind") == "tool_call":
                command = (entry.get("args") or {}).get("command")
                calls[str(entry.get("call_id"))] = " ".join(map(str, command)) if isinstance(command, list) \
                    else str(command or "")
                continue
            text = calls.get(str(entry.get("call_id")), "")
            if not text or not _IMPORTS.search(text) or not _exited_zero(entry.get("content")):
                continue
            if (name and re.search(rf"\b{re.escape(name)}\b", text)) or any(module in text for module in modules):
                return (f"its fixer ran `{text[:200]}`, which imports it and exited 0, in the attempt that gave up")
        return ""
    except Exception:  # noqa: BLE001 - nothing shown is the finding as it was
        return ""


def _digest(root: Any, relative: str) -> str:
    try:
        return hashlib.sha1((Path(root) / relative).read_bytes()).hexdigest()[:12]
    except OSError:
        return ""


def _said(relative: str, message: str, digest: str) -> str:
    return f"{relative}: {message} - loaded by its fixer's run while the file was {digest}"


def recorded(root: Any, description: str, why: str) -> None:
    """Record a finding its fixer's run showed false, with the file as it is now. Never raises."""
    try:
        finding = _finding(description)
        if finding is None or not why:
            return
        from app.acceptance import check_findings

        relative, message = finding
        check_findings.noted(root, 0, CHECK, [f"{_said(relative, message, _digest(root, relative))}: {why}"])
    except Exception:  # noqa: BLE001 - the rewrite is declined whether or not it is recorded
        pass


def still_shown_false(root: Any, relative: str, message: str) -> str:
    """What a fixer's run recorded against this finding while its file is as it was then; ""."""
    try:
        if not root:
            return ""
        from app.acceptance import check_findings

        digest = _digest(root, relative)
        said = _said(relative, message, digest)
        for row in reversed(check_findings.read(root)):
            text = str(row.get("text") or "")
            if row.get("check") == CHECK and digest and text.startswith(said + ": "):
                return text[len(said) + 2:]
        return ""
    except Exception:  # noqa: BLE001
        return ""


__all__ = ["CHECK", "COMMAND_TOOLS", "recorded", "shown_false", "still_shown_false"]
