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
#: Characters of the project memory one rewrite is shown.
MEMORY_CHARACTERS = 60_000
#: Characters of failure output shown.
MOST_FAILURE_CHARACTERS = 6_000

_AN_ERROR_LOCATION = re.compile(r"([\w./@-]+\.[A-Za-z0-9]{1,8})(?:\((\d+),\d+\)|:(\d+)(?::\d+)?)")
#: A file named in a failure's text without a line: "README.md must give PORT a
#: default". Measured on one run: every failing test said what the README
#: lacked, the stack traces pointed at the entry point, and the rewrite fixed
#: the entry point - the same failure twice.
_A_FILE_NAMED = re.compile(r"(?<![\w/.@-])((?:[\w@-]+/)*[\w@-]+\.[A-Za-z][A-Za-z0-9]{0,7})(?![\w/-])")


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
    # In the order the failure names them, with a line or without.
    mentioned = sorted(
        [(m.start(), m.group(1)) for m in _AN_ERROR_LOCATION.finditer(failure)]
        + [(m.start(), m.group(1)) for m in _A_FILE_NAMED.finditer(failure)],
    )
    named += [name.lstrip("./") for _, name in mentioned]
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
    from app.agents import project_memory

    if project_memory.enabled():
        # The whole project as it is now, the files the failure names first,
        # rather than only the files this one imports. See `app.agents.project_memory`.
        neighbours, _ = project_memory.render(root, MEMORY_CHARACTERS, focus=f"{path}\n{failure}")
    else:
        neighbours = _neighbours(root, path, SimpleNamespace(files=others), detail)
    return "\n\n".join(part for part in (
        f"Correct the file `{path}` of this product so the failure below no longer happens. "
        f"The stack: {_stack_line(stack)}.",
        f"--- The defect ---\n{getattr(defect, 'description', '')}\n"
        f"Expected: {getattr(defect, 'expected_behavior', '')}",
        f"--- What failed ---\n{failure}" if failure.strip() else "",
        ("--- The compiler still reports, in the files just written ---\n" + "\n".join(diagnostics)) if diagnostics else "",
        detail.strip(),
        f"--- The project ---\n{neighbours}" if neighbours else "",
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
                    try:
                        write(str(root), path, content)
                    except Exception as refused:  # noqa: BLE001 - the next pass is told what was refused
                        if "language service is sure of" not in str(refused):
                            raise
                        diagnostics = [*diagnostics, f"- In `{path}`: {refused}"]
                        continue
                    if path not in changed:
                        changed.append(path)
            except Exception as error:  # noqa: BLE001 - the agent loop takes what this could not
                logger.info("Rewrite of %s for a fix failed: %s", path, str(error)[:200])
                if not changed:
                    return None
        refused = [line for line in diagnostics if "language service is sure of" in line]
        diagnostics = [*refused, *(diagnose(changed) if diagnose and changed else [])]
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


#: Candidate fixes asked for at once, when a defect has failed a fix already.
CANDIDATES = 3


def fix_by_candidates(
    defect: Any, repo_root: str | Path, model: Any, check: Callable[[], bool | None], *,
    specification: Any = None, stack: Any = None, last_failure: Any = None,
    may_write: Callable[[str], bool] | None = None, write: Callable[[str, str, str], Any] | None = None,
    candidates: int = CANDIDATES,
) -> Any | None:
    """A defect fixed by several candidate rewrites asked for at once, the first its tests pass kept; or None.

    Agentless's repair and validation: one run's defect failed fix after fix
    on the build model, each an agent loop of half an hour. Here the
    judgement model writes `candidates` versions of the files in parallel -
    a cloud model serves them side by side - and the harness applies each in
    turn, runs the defect's own tests (`check`), and keeps the first that
    passes, putting the files back between tries. None when no candidate
    passes, or nothing could be written: the agent loop takes the defect.
    """
    from concurrent.futures import ThreadPoolExecutor

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
    originals = {path: (root / path).read_text(encoding="utf-8", errors="replace") for path in files}

    def one(path_and_index: tuple[str, int]) -> tuple[int, str, str]:
        path, index = path_and_index
        try:
            reply = model.invoke([
                SystemMessage(content="You correct source files of a software product. You reply with "
                                      "one file's complete content in one fenced code block."),
                HumanMessage(content=fix_request(root, path, defect, failure, specification, stack,
                                                 [f for f in files if f != path], [])),
            ])
            return index, path, the_content_in(getattr(reply, "content", reply) if not isinstance(reply, str) else reply)
        except Exception as error:  # noqa: BLE001 - one candidate fewer
            logger.info("A candidate rewrite of %s failed: %s", path, str(error)[:200])
            return index, path, ""

    with ThreadPoolExecutor(max_workers=max(1, candidates * len(files))) as pool:
        written = list(pool.map(one, [(path, index) for index in range(candidates) for path in files]))
    versions: list[dict[str, str]] = [{} for _ in range(candidates)]
    for index, path, content in written:
        if content.strip():
            versions[index][path] = content

    def put_back() -> None:
        for path, text in originals.items():
            (root / path).write_text(text, encoding="utf-8")

    for number, version in enumerate(versions, 1):
        changed = [path for path, content in version.items() if content != originals[path]]
        if not changed:
            continue
        try:
            for path in changed:
                write(str(root), path, version[path])
        except Exception as error:  # noqa: BLE001 - this candidate is refused; the next is tried
            logger.info("Candidate %d refused: %s", number, str(error)[:200])
            put_back()
            continue
        passed = check()
        if passed is not False:
            logger.info("Candidate fix %d of %d kept%s: %s", number, candidates,
                        "" if passed else " (nothing to check it against)", ", ".join(changed))
            return SpecialistOutput(
                changed_files=changed,
                tests=["the defect's own acceptance and unit tests, run by the harness"],
                decisions=[f"Candidate {number} of {candidates} rewrites; its tests pass (fast delivery)."
                           if passed else f"Candidate {number} of {candidates}; no test of its own to check it."],
            )
        put_back()
    logger.info("No candidate fix of %d passed its tests; the agent loop takes the defect", candidates)
    return None
