"""Each line of the interface contract is exercised by a test, and one that is not is named to QA (plan item 16, behind `CONTRACT_LINE_COVERAGE`).

The suite is checked against the criteria - every id in some test's name - and never against the contract, so a
criterion could be credited to one test while a route its contract line promises was called by none; such a route is
then seen only by the release's bare probe. This reads the suite's own files, needs no model, and never runs the suite.

It is a search, not a parse, because of what the kept locked suites do: calls through helpers (`createNote(request)`),
paths held in a name (`const base = '/notes'`), loops over tables of method and path, multi-line calls, and ids
interpolated in many spellings. Each of those counts as exercising a line, so a suite is named only when a route's path
or method appears nowhere it could be called. A comment, a docstring or a test's title naming a route proves nothing,
and does not count.

A contract with page lines, or a suite that calls none of the contract's routes, reaches its routes some other way (the
pages it drives), so its route lines are not named: the check says nothing it cannot read.
"""
from __future__ import annotations

import logging
import re
import shlex
from collections.abc import Sequence
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: `CONTRACT_LINE_COVERAGE` set to on or off overrides this; off until measured.
ON_BY_DEFAULT = False
#: What the admin page says this switch does.
explanation = ("At the suite's review, a line of the interface contract no test calls is named to QA and the suite goes "
               "back. Measure: lines with no test at lock.")


def enabled() -> bool:
    from app.switches import is_on

    return is_on("CONTRACT_LINE_COVERAGE", ON_BY_DEFAULT)


#: A whole line that is only a comment, in the languages the suites are written in.
_A_COMMENT_LINE = re.compile(r"^\s*(?://|#|\*|/\*|--)")
#: A route's parameter in the contract: `{id}` or `:id`.
_A_PARAMETER = re.compile(r"^(?:\{[^}]*\}|:[A-Za-z_]\w*)$")
#: What may stand for a parameter in a test: a number, `${id}`, `{id}`, `%s`, or nothing where the id is added after.
_A_VALUE = r"[^/\s'\"`]*"
#: A test's title or a docstring has a space before the path; a call has a quote, a `}` closing the base address, or a host.
_BEFORE_A_PATH = r"(?<=['\"`}\w])"
_AFTER_A_PATH = r"/?(?=[?#'\"`\s,)]|$)"
#: How many lines around a path a call's method may be on: `httpx.post(\n  f"{base}/items",` and `{ path, \n method }`.
_LINES_BEFORE, _LINES_AFTER = 2, 1


def _route(path: str) -> str:
    """`path` as a pattern for its spelling in a test's text."""
    return "/".join(_A_VALUE if _A_PARAMETER.match(part) else re.escape(part) for part in path.rstrip("/").split("/"))


def _the_lines(repo_root: str | Path) -> list[list[str]]:
    """Each suite file's lines, without its comment lines."""
    from app.acceptance import suite

    files = []
    for path in suite.suite_files(repo_root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        files.append([line for line in text.splitlines() if not _A_COMMENT_LINE.match(line)])
    return files


def _a_call_through_a_name(method: str, text: str) -> bool:
    """Whether the suite calls this method with no literal path (`request.put(url)`), or by a table (`request[method](path)`)."""
    verb = method.lower()
    if re.search(rf"(?i){verb}\w*\s*\(\s*(?:\w+\s*,\s*)?(?:[A-Za-z_$]|[`'\"f]+\$?\{{)", text):
        return True
    dispatched = re.search(r"\[\s*\w*(?:method|verb)\w*\s*\]|\.(?:fetch|request)\s*\(", text, re.I)
    return bool(dispatched and re.search(rf"(?i)['\"`]{verb}['\"`]", text))


def _called(check: Any, files: list[list[str]], whole: str) -> bool:
    verb = str(check.method).lower()
    pattern = re.compile(_BEFORE_A_PATH + _route(check.path) + _AFTER_A_PATH)
    held = False
    for lines in files:
        for at, line in enumerate(lines):
            if not pattern.search(line):
                continue
            held = True
            near = "\n".join(lines[max(0, at - _LINES_BEFORE):at + _LINES_AFTER + 1]).lower()
            if verb in near or (verb == "get" and "fetch" in near):
                return True
    return (held or _held_in_parts(check.path, whole)) and _a_call_through_a_name(check.method, whole)


def _held_in_parts(path: str, whole: str) -> bool:
    """Whether a path is built from parts: `const base = '/notes'` then `${base}/${id}`, or `'/api'` then `${api}/notes`."""
    parts = path.rstrip("/").split("/")
    fixed = [part for part in parts if part and not _A_PARAMETER.match(part)]
    if not fixed:
        return True
    literals = re.findall(r"['\"`]/?([\w./-]*)/?['\"`]", whole)
    return any(part in literal.split("/") for part in fixed for literal in literals) and all(part in whole for part in fixed)


def _a_refusal_only(check: Any) -> list[int]:
    """The statuses of a line that allows no success; a test of it must name one. [] for any other line."""
    allowed = list(check.statuses or (check.status,))
    return [] if any(200 <= code < 300 for code in allowed) else allowed


def _command_word(command: str) -> str:
    """The word a test of this command must say - its subcommand or first option; "" when it has neither."""
    try:
        words = shlex.split(command)
    except ValueError:
        return ""
    return next((word for word in words[1:] if not re.search(r"[<>{}\[\]]", word) and "." not in word), "")


def lines_with_no_test(repo_root: str | Path, lines: Sequence[str] = ()) -> list[str]:
    """The contract's lines no test in the suite calls; [] when it cannot tell. Never raises.

    `lines`: the specification's, before the suite is locked; the locked contract after.
    """
    try:
        from app.acceptance import interface_contract

        checks = interface_contract.parse(list(lines))[0] if lines else interface_contract.the_locked_contract(repo_root)
        files = _the_lines(repo_root)
        if not checks or not files:
            return []
        whole = "\n".join("\n".join(each) for each in files)
        routes = [c for c in checks if c.kind == "http"]
        missing: list[Any] = []
        uncalled = [c for c in routes if not _called(c, files, whole)]
        if len(uncalled) < len(routes) and not any(c.kind == "page" for c in checks):
            missing += uncalled
        missing += [c for c in routes if c not in uncalled and (refused := _a_refusal_only(c))
                    and not any(re.search(rf"\b{code}\b", whole) for code in refused)
                    and not any(c.kind == "page" for c in checks)]
        lowered = whole.lower()
        missing += [c for c in checks if c.kind == "page" and c.name.lower() not in lowered]
        missing += [c for c in checks if c.kind == "command"
                    and (word := _command_word(c.command)) and word.lower() not in lowered]
        return list(dict.fromkeys(c.line for c in missing))
    except Exception:  # noqa: BLE001 - a check that cannot run sends nothing back
        logger.debug("Could not read the contract's lines against the suite", exc_info=True)
        return []


def finding(lines_missing: Sequence[str]) -> str:
    """What QA is told about lines no test calls; "" when there are none."""
    if not lines_missing:
        return ""
    return (
        "No test calls these lines of the interface contract: "
        + "; ".join(f"`{line}`" for line in lines_missing[:12])
        + (f"; and {len(lines_missing) - 12} more" if len(lines_missing) > 12 else "")
        + ". The release checks them with a bare request only, so what each promises is proven nowhere. Add to the test "
        "of its criterion, or write one, that makes the request the line names and asserts the status it gives."
    )


def record_at_lock(repo_root: str | Path) -> list[str]:
    """Keep the locked contract's lines with no test beside it and log their count, on or off: plan item 16's measure."""
    from app.acceptance import suite

    missing = lines_with_no_test(repo_root)
    try:
        state = suite._state(repo_root)  # noqa: SLF001 - one state file for the suite and its contract
        state["interface_contract_no_test"] = missing
        suite._save_state(repo_root, state)  # noqa: SLF001
        logger.info("Interface contract at the lock: %d line(s) with no test", len(missing))
    except Exception:  # noqa: BLE001 - a measure lost is no reason to stop a lock
        logger.debug("Could not record the contract's lines with no test", exc_info=True)
    return missing
