"""The stack block and the library calls a builder is shown, made true to the specification and the install (deep
review 2026-11-25, item 3).

The stack block opens every builder's and fixer's request with "already decided ... Build on exactly this", and listed
the stack selector's "Other tools". The specification is written after the stack is chosen and can replace one of
them. Measured on one medium run: the block named python-jose and passlib after the specification had decided PyJWT
and bcrypt (and the pack's own guidance warned passlib fails with bcrypt 5); one builder installed python-jose, another
recorded "JWT authentication via python-jose and passlib", the review raised "JWT library is ambiguous", and a later
builder removed the dependency again. The same requests gave "Library: PyJWT 1.4.0" - a version of another package
of that name - "as their documentation gives them", beside "Versions here: pyjwt 2.15.1".

So:

- the other tools are named as what they are - named when the stack was chosen; the specification decides the
  libraries - and a tool the specification replaced is named apart, as not used. A tool is replaced when a decision
  record says so in words (`instead of X`, `no dependency on X`, `avoids X`, `over X`), or when a decision record
  about the tool's purpose (`python-jose (JWT)`: a record titled "JWT ...") decides without it; a tool the
  specification's library calls name is never replaced;
- a library call's version that disagrees with the version installed here (`.harness/stack-facts.json`) is given as
  the installed one, saying so.

Read from the specification document on disk, which the harness renders from the structured specification. Never
raises: anything unread leaves the text as it was.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)

SPECIFICATION = "docs/technical_specification.md"

#: A decision record's heading in the rendered specification: `### ADR-04 — bcrypt for password hashing`.
_A_RECORD = re.compile(r"^###\s+(?:ADR-\d+\s*[—–-]\s*)?(.*)$", re.M)
#: A part of a record that names candidates it did not choose.
_EVIDENCE = re.compile(r"\*\*(?:Validation evidence|Alternatives):\*\*.*?(?=\*\*[A-Z][\w -]*:\*\*|\Z)", re.S)
_DECISION = re.compile(r"\*\*Decision:\*\*\s*(.*?)(?=\*\*[A-Z][\w -]*:\*\*|\Z)", re.S)
#: A library call's opening: `Library: PyJWT 1.4.0.`, `FastAPI 0.165.0: ...`.
_A_CALL_S_VERSION = re.compile(r"^(\s*(?:Library:\s*)?)([@A-Za-z][\w.\-/@]*)\s+v?(\d+(?:\.\d+)+)(?![\w+]|\.\d)")


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name or "").lower())


def _the_specification(root: str | Path | None) -> str:
    if not root:
        return ""
    try:
        return (Path(root) / SPECIFICATION).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _section(document: str, heading: str) -> str:
    found = re.search(rf"^## {re.escape(heading)}[^\n]*\n(.*?)(?=^## |\Z)", document, re.S | re.M)
    return found.group(1) if found else ""


def _records(document: str) -> list[tuple[str, str, str]]:
    """(title, decision, the record without what names unchosen candidates) for each decision record."""
    text = document.split("## Decisions (ADR)", 1)[1] if "## Decisions (ADR)" in document else ""
    heads = list(_A_RECORD.finditer(text))
    records = []
    for at, head in enumerate(heads):
        body = text[head.end():heads[at + 1].start() if at + 1 < len(heads) else len(text)]
        decision = _DECISION.search(body)
        records.append((head.group(1).strip(), decision.group(1).strip() if decision else "", _EVIDENCE.sub("", body)))
    return records


def _a_name_and_its_purpose(tool: str) -> tuple[str, str]:
    """`python-jose (JWT)` -> ("python-jose", "JWT"); `Vite` -> ("Vite", "")."""
    found = re.match(r"^\s*(.*?)\s*\(([^()]*)\)\s*$", str(tool))
    return (found.group(1), found.group(2).strip()) if found else (str(tool).strip(), "")


def _names(text: str, name: str) -> bool:
    return bool(name) and bool(re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text, re.I))


def _replaced(tool: str, document: str, called: set[str]) -> bool:
    name, purpose = _a_name_and_its_purpose(tool)
    if not name or _key(name) in called:
        return False
    for title, decision, record in _records(document):
        if re.search(rf"\b(?:no dependency on|instead of|rather than|in place of|avoids?|avoiding|over)\s+[`'\"*]?"
                     rf"{re.escape(name)}(?![\w-])", record, re.I):
            return True
        if purpose and _names(title, purpose) and decision and not _names(decision, name):
            return True
    return False


def _the_libraries_called(document: str) -> set[str]:
    called = set()
    for line in _section(document, "Library Usage").splitlines():
        entry = re.sub(r"^\s*-\s*", "", line)
        found = re.match(r"^\s*(?:Library:\s*)?([@A-Za-z][\w.\-/@]*)", entry)
        if found:
            called.add(_key(found.group(1)))
    return called


def other_tools(tools: Iterable[Any], root: str | Path | None) -> tuple[list[str], list[str]]:
    """The stack's other tools as (kept, replaced by the specification). Never raises."""
    named = [str(tool) for tool in tools or () if str(tool).strip()]
    try:
        document = _the_specification(root)
        if not document:
            return named, []
        called = _the_libraries_called(document)
        replaced = [tool for tool in named if _replaced(tool, document, called)]
        return [tool for tool in named if tool not in replaced], replaced
    except Exception:  # noqa: BLE001 - the tools as named
        logger.debug("Could not compare the stack's tools with the specification", exc_info=True)
        return named, []


def other_tools_line(tools: Iterable[Any], root: str | Path | None) -> str:
    """The stack block's line for the other tools, or "" for none."""
    kept, replaced = other_tools(tools, root)
    if not kept and not replaced:
        return ""
    line = ("- Other tools, named when the stack was chosen (the specification decides the libraries): "
            + (", ".join(kept) or "none left"))
    if replaced:
        line += f". Not used - the specification decided otherwise: {', '.join(replaced)}"
    return line


def _installed(root: str | Path | None) -> dict[str, str]:
    """{package key: the version installed here} from the stack facts; {} when there are none."""
    try:
        from app.stacks import stack_facts

        return {_key(d.get("package")): str(d.get("resolved") or d.get("version") or "")
                for d in stack_facts.read(root).get("dependencies") or [] if isinstance(d, dict) and d.get("package")}
    except Exception:  # noqa: BLE001 - nothing installed is known
        return {}


def _agrees(written: str, installed: str) -> bool:
    """Whether a version written as `2` or `2.15` is the installed `2.15.1`'s."""
    have = installed.split(".")
    return written.split(".") == have[:len(written.split("."))]


def library_calls(entries: Iterable[Any], root: str | Path | None) -> list[str]:
    """The specification's library calls, each version that disagrees with the installed one given as installed."""
    calls = [str(entry).strip() for entry in entries or () if str(entry).strip()]
    try:
        installed = _installed(root)
        if not installed:
            return calls
        fixed = []
        for entry in calls:
            found = _A_CALL_S_VERSION.match(entry)
            have = installed.get(_key(found.group(2))) if found else ""
            if found and have and not _agrees(found.group(3), have):
                entry = (entry[:found.start(3)] + have + f" (installed here; the specification wrote {found.group(3)})"
                         + entry[found.end(3):])
            fixed.append(entry)
        return fixed
    except Exception:  # noqa: BLE001 - the calls as written
        logger.debug("Could not compare the library calls with the installed versions", exc_info=True)
        return calls


__all__ = ["library_calls", "other_tools", "other_tools_line"]
