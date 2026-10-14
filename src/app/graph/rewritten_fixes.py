"""A defect fixed by the harness gathering and the model rewriting, one call per file.

Fast delivery's fix (`app.delivery`). Measured on one run: 294 model calls and
152 minutes of agent loops to fix one sprint's defects - the fixer listing,
reading, searching and running tests to find what the harness already knew,
and one in ten of its tool calls malformed. A local model is good at writing a
whole file and poor at driving tools.

So the harness does the gathering: the files the defect names and the files
its failure output points at, what the failing tests printed, the
specification's entries for each file, and the files they work with. Each
file is asked for in one call and written whole. The compiler's diagnostics on
what was written are given back for up to `MOST_PASSES` passes. What follows
is the fix stage's as before: a fix that breaks a passing test is reverted,
and the next test round measures it. A defect with no file the harness can
name, or a file the workspace refuses, goes to the agent loop, unchanged.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path, PurePosixPath
from typing import Any, Callable

logger = logging.getLogger(__name__)

#: Files one defect's fix rewrites at most.
MOST_FILES = 4
#: Passes over the written files: the first, and one more for each set of
#: diagnostics the compiler still reports.
MOST_PASSES = 3
#: Characters of failure output shown.
MOST_FAILURE_CHARACTERS = 6_000

_AN_ERROR_LOCATION = re.compile(r"([\w./@-]+\.[A-Za-z0-9]{1,8})(?:\((\d+),\d+\)|:(\d+)(?::\d+)?)")


def what_failed(defect: Any, repo_root: str | Path, last_failure: Any = None) -> str:
    """What the defect's failing tests and last failing command printed, as one text."""
    parts: list[str] = []
    for field in ("actual_behavior", "reproduction_steps"):
        value = getattr(defect, field, "")
        text = "\n".join(map(str, value)) if isinstance(value, (list, tuple)) else str(value or "")
        if text.strip():
            parts.append(text.strip())
    try:
        from app.acceptance import suite
        from app.acceptance.junit import tags_in

        tags = set(tags_in(str(getattr(defect, "description", "") or "")))
        criteria = (suite.last_result(repo_root) or {}).get("criteria") or {}
        for cid in sorted(tags):
            for test in (criteria.get(cid) or {}).get("tests") or []:
                if test.get("outcome") != "passed" and test.get("message"):
                    parts.append(f"{cid} `{test.get('name')}`: {test['message']}")
    except Exception:  # noqa: BLE001 - the description still says what failed
        logger.debug("Could not read the acceptance result for a fix", exc_info=True)
    if isinstance(last_failure, dict):
        printed = "\n".join(str(last_failure.get(k) or "") for k in ("command", "stdout", "stderr")).strip()
        if printed:
            parts.append(f"The last failing command printed:\n{printed}")
    return "\n\n".join(parts)[:MOST_FAILURE_CHARACTERS]


def files_to_fix(defect: Any, failure: str, repo_root: str | Path, may_write: Callable[[str], bool]) -> list[str]:
    """The workspace files a fix rewrites: the ones the defect names, then the ones its failure points at."""
    from app.tools.repository import IGNORED_DIRECTORIES

    root = Path(repo_root)
    named = [str(f).strip().lstrip("./") for f in getattr(defect, "affected_files", None) or [] if str(f).strip()]
    named += [match.group(1).lstrip("./") for match in _AN_ERROR_LOCATION.finditer(failure)]
    found: list[str] = []
    for name in dict.fromkeys(named):
        candidates = [root / name, *root.glob(f"*/{name}")]
        target = next((c for c in candidates if c.is_file()), None)
        if target is None or any(part in IGNORED_DIRECTORIES for part in target.parts):
            continue
        relative = target.relative_to(root).as_posix()
        if relative not in found and may_write(relative):
            found.append(relative)
        if len(found) >= MOST_FILES:
            break
    return found


def fix_request(root: Path, path: str, defect: Any, failure: str, specification: Any,
                stack: Any, others: list[str], diagnostics: list[str]) -> str:
    """What one file's rewrite is asked."""
    from app.agents.specialists import specification_for_the_work_order
    from app.graph.drafting import _neighbours, _stack_line
    from types import SimpleNamespace

    detail = specification_for_the_work_order(specification, SimpleNamespace(files=[path], interfaces=[])) if specification else ""
    now = (root / path).read_text(encoding="utf-8", errors="replace")
    neighbours = _neighbours(root, path, SimpleNamespace(files=others), detail)
    return "\n\n".join(part for part in (
        f"Correct the file `{path}` of this product so the failure below no longer happens. "
        f"The stack: {_stack_line(stack)}.",
        f"--- The defect ---\n{getattr(defect, 'description', '')}\n"
        f"Expected: {getattr(defect, 'expected_behavior', '')}",
        f"--- What failed ---\n{failure}" if failure.strip() else "",
        ("--- The compiler still reports, in the files just written ---\n" + "\n".join(diagnostics)) if diagnostics else "",
        detail.strip(),
        f"--- The files it works with ---\n{neighbours}" if neighbours else "",
        f"--- `{path}` as it is now ---\n{now}",
        f"Reply with the complete corrected content of `{path}` and nothing else, in one fenced "
        "code block. Change only what the failure needs; keep every name, signature and "
        "message the specification gives. If this file needs no change for this failure, "
        "reply with it unchanged.",
    ) if part)


def fix_by_rewriting(
    defect: Any, repo_root: str | Path, model: Any, *, specification: Any = None, stack: Any = None,
    last_failure: Any = None, may_write: Callable[[str], bool] | None = None,
    write: Callable[[str, str, str], Any] | None = None,
    diagnose: Callable[[list[str]], list[str]] | None = None,
) -> Any | None:
    """The fix stage's output for a defect fixed by rewriting its files, or None for the agent loop."""
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.agents.specialists import SpecialistOutput
    from app.graph.drafting import the_content_in

    root = Path(repo_root)
    if write is None:
        from app.tools.repository import write_approved_artifact

        def write(base: str, path: str, content: str) -> Any:
            return write_approved_artifact(base, path, content)

    failure = what_failed(defect, root, last_failure)
    files = files_to_fix(defect, failure, root, may_write or (lambda _: True))
    if not files:
        return None
    changed: list[str] = []
    diagnostics: list[str] = []
    for _pass in range(MOST_PASSES):
        targets = files if not diagnostics else [f for f in files if any(f"`{f}`" in d for d in diagnostics)] or files
        for path in targets:
            try:
                reply = model.invoke([
                    SystemMessage(content="You correct source files of a software product. You reply with "
                                          "one file's complete content in one fenced code block."),
                    HumanMessage(content=fix_request(root, path, defect, failure, specification, stack,
                                                     [f for f in files if f != path], diagnostics)),
                ])
                content = the_content_in(getattr(reply, "content", reply) if not isinstance(reply, str) else reply)
                if not content.strip():
                    continue
                if content != (root / path).read_text(encoding="utf-8", errors="replace"):
                    write(str(root), path, content)
                    if path not in changed:
                        changed.append(path)
            except Exception as error:  # noqa: BLE001 - the agent loop takes what this could not
                logger.info("Rewrite of %s for a fix failed: %s", path, str(error)[:200])
                if not changed:
                    return None
        diagnostics = diagnose(changed) if diagnose and changed else []
        if not diagnostics:
            break
    if not changed:
        return None
    logger.info("Fixed by rewriting %d file(s) from what failed: %s", len(changed), ", ".join(changed))
    return SpecialistOutput(
        changed_files=changed,
        tests=["the acceptance suite and unit tests, run by the harness after the fix"],
        decisions=[
            f"Rewrote {', '.join(changed)} from the failure output and the specification (fast delivery)."
            + (f" The compiler still reports: {'; '.join(diagnostics)[:400]}" if diagnostics else "")
        ],
    )
