"""Work orders drafted straight from the specification, one call per file.

Fast delivery's build step (`app.delivery`). The specification names every
file, its exports, every function's steps and messages, and the library
calls they make; a work order's builder used to turn that into code through
an agent loop of about forty tool calls - list, read, write, run, read again
- each resending the whole conversation. Measured on one run: 296 such calls
for 549 lines of product.

Here each file a work order owns is written in one call, from the
specification's entries for it and the files it works with, several files
at once. A work order all of whose files were written is recorded as done,
as an agent's would be; the rest are left to the agent loop, which is
unchanged. Tests are drafted the same way, and only the ones the
specification plans.
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import Any, Callable

logger = logging.getLogger(__name__)

#: The most of the files it works with that one draft is shown.
MOST_NEIGHBOUR_CHARACTERS = 24_000
#: The most of one neighbour.
MOST_ONE_NEIGHBOUR_CHARACTERS = 8_000

_FENCE = re.compile(r"```[^\n`]*\n(.*?)```", re.S)
_A_PATH = re.compile(r"[\w./@-]+\.[A-Za-z0-9]{1,8}\b")


def the_content_in(reply: str) -> str:
    """The file a reply holds: its longest fenced block, or the whole reply when it has none."""
    text = str(reply or "")
    blocks = _FENCE.findall(text)
    if blocks:
        return max(blocks, key=len).rstrip() + "\n"
    stripped = text.strip()
    return stripped + "\n" if stripped else ""


#: One line of a file plan: its indent, an optional list marker, then its first word.
_PLAN_LINE = re.compile(r"^(?P<indent>[ \t]*)(?:[-*+]|\d+[.)])?[ \t]*(?P<head>\S+)")
#: What a path is made of, once its markup is stripped.
_PATH_CHARACTERS = re.compile(r"[\w./@+-]+")


def planned_files(specification: Any) -> list[str]:
    """The paths the specification's file plan names, in its order.

    An entry is `path: purpose`, `path - purpose`, or a list item
    (``- **`path`** - purpose``). A directory entry (`pkg/services/`) heads the
    bare names indented under it, in the same entry or the ones after it; a
    line that names no path - a heading such as "Backend source code" - names
    no file, and ends the directory above it.

    Measured on one gate run: every entry was a list item, so the first word
    of each was its `-`, and the plan read as its five headings ("Root-level",
    "Frontend", ...). The work orders made from it held none of the product's
    files, and three services listed only under their directory were given
    to nobody - three re-plans of the lead.
    """
    found: list[str] = []
    directories: list[tuple[int, str]] = []
    for entry in getattr(specification, "file_plan", None) or []:
        for line in str(entry).expandtabs(4).splitlines():
            match = _PLAN_LINE.match(line)
            if match is None:
                continue
            indent = len(match.group("indent"))
            while directories and directories[-1][0] >= indent:
                directories.pop()
            raw = match.group("head")
            head = raw.strip("`*:,;")
            if not _PATH_CHARACTERS.fullmatch(head) or not ("/" in head or "." in head or "`" in raw):
                continue
            above = directories[-1][1] if directories else ""
            if above and not head.startswith(above):
                head = above + head.lstrip("./")
            if head.endswith("/"):
                directories.append((indent, head))
                continue
            if head not in found:
                found.append(head)
    return found


def _is_planned(path: str, planned: list[str]) -> bool:
    plain = path.strip().lstrip("./")
    return any(plain == p or plain.endswith("/" + p) or p.endswith("/" + plain) for p in planned)


#: Test files the lead may give its work orders when the file plan names none.
MOST_UNPLANNED_TEST_FILES = 5

#: Files one fast work order owns at most. A soft cap: the lead's larger
#: orders are split here, not refused (owner decision 2026-10-18, to be
#: measured over two runs). One file per order multiplies stages and makes a
#: contract across files harder; an order of many files is one agent loop the
#: size of the whole product when its drafts do not land.
MOST_FILES_PER_WORK_ORDER = 3


def in_work_orders_of_at_most(tasks: list[Any], most: int = MOST_FILES_PER_WORK_ORDER) -> tuple[list[Any], int]:
    """`tasks` with each order of more than `most` files split, in order, into orders of `most`; and how many were split.

    Each part keeps its order's owner, description, contract and checks, and
    owns its own files only; its title says which part it is.
    """
    kept: list[Any] = []
    split = 0
    for task in tasks:
        files = list(getattr(task, "files", None) or [])
        if len(files) <= most:
            kept.append(task)
            continue
        split += 1
        parts = [files[i:i + most] for i in range(0, len(files), most)]
        title = str(getattr(task, "title", "") or "").strip()
        for number, part in enumerate(parts, start=1):
            siblings = [f for f in files if f not in part]
            update = {
                "files": part,
                "title": f"{title} (part {number} of {len(parts)})" if title else f"part {number} of {len(parts)}",
            }
            # A part carries what concerns its own files. An order's steps for
            # a sibling's file sent a part to write, or wait for, a file that
            # is not its own (Initiative AO.3).
            for field in _LINES_ABOUT_FILES:
                lines = getattr(task, field, None)
                if lines:
                    update[field] = _lines_for_a_part(lines, part, siblings)
            update["out_of_scope"] = [
                *(getattr(task, "out_of_scope", None) or []),
                "Written by a parallel part of this order - do not wait for them or rewrite them, "
                "and use their contracts from the specification: " + ", ".join(siblings),
            ]
            kept.append(task.model_copy(update=update))
    return kept, split


#: The work-order fields whose lines can be about one file or another.
_LINES_ABOUT_FILES = ("interfaces", "steps", "edge_cases", "test_cases", "verification")


def _lines_for_a_part(lines: list[str], own: list[str], siblings: list[str]) -> list[str]:
    """`lines` without those that name only files of other parts.

    A line naming one of this part's files stays; a line naming no file of the
    order at all (a rule for the whole work) stays; one that names only
    siblings goes.
    """
    def names(line: str, files: list[str]) -> bool:
        return any(PurePosixPath(f).name in line for f in files)

    return [line for line in lines if names(line, own) or not names(line, siblings)]


def with_tests_the_specification_plans(tasks: list[Any], specification: Any) -> tuple[list[Any], list[str]]:
    """`tasks`, each test file not in the specification's file plan taken out; and what was taken.

    Only when the specification plans files at all. One run's testing work
    orders wrote 5,058 lines of tests - launcher, integration and contract
    suites nobody planned - for 549 lines of product.
    """
    from app.analysis.file_kinds import classify_file

    planned = planned_files(specification)
    if not planned:
        return tasks, []
    # A file plan that names no test at all is no plan for the tests: dropping
    # every one then shipped a 2,863-line product with no unit test (one run).
    # The lead's are kept instead, bounded, so the bloat this guards stays out.
    plans_tests = any(classify_file(f) == "test" for f in planned)
    allowance = 0 if plans_tests else MOST_UNPLANNED_TEST_FILES
    kept_tasks, dropped = [], []
    for task in tasks:
        files = list(getattr(task, "files", None) or [])
        keep = []
        for f in files:
            if classify_file(f) != "test" or _is_planned(f, planned):
                keep.append(f)
            elif allowance > 0:
                keep.append(f)
                allowance -= 1
        dropped.extend(f for f in files if f not in keep)
        kept_tasks.append(task.model_copy(update={"files": keep}) if keep != files else task)
    return kept_tasks, dropped


def _stack_line(stack: Any) -> str:
    parts = [
        str(getattr(stack, field, "") or "").strip()
        for field in ("language", "framework", "frontend_framework", "testing_framework")
    ]
    return ", ".join(part for part in parts if part) or "as the specification says"


def _neighbours(root: Path, path: str, task: Any, detail: str) -> str:
    """The files this one works with, as they are on disk: the work order's own and any its entries name."""
    named = [*(getattr(task, "files", None) or []), *_A_PATH.findall(detail)]
    shown, used = [], 0
    for other in dict.fromkeys(named):
        other = other.strip().lstrip("./")
        if not other or other == path.lstrip("./"):
            continue
        candidates = [root / other, *(root.glob(f"*/{other}"))]
        target = next((c for c in candidates if c.is_file()), None)
        if target is None:
            continue
        try:
            text = target.read_text(encoding="utf-8")[:MOST_ONE_NEIGHBOUR_CHARACTERS]
        except (OSError, UnicodeDecodeError):
            continue
        if used + len(text) > MOST_NEIGHBOUR_CHARACTERS:
            break
        used += len(text)
        shown.append(f"--- {target.relative_to(root).as_posix()} ---\n{text}")
    return "\n\n".join(shown)


def _where_dependencies_go(root: Path) -> str:
    """The manifests this project's install reads, for every drafted file; "" with no recorded setup.

    Drafting wrote the dependency lists: on five gate runs in a row it put a
    service's packages in `pyproject.toml`, which the pack's install never
    reads, and the product did not start until a fix round moved them.
    """
    try:
        from app.stacks import contract

        record = contract.read(root)
        if not record:
            return ""
        return "--- Where this project's dependencies go ---\n" + contract._where_dependencies_go(
            str(record.get("project") or ""), record)
    except Exception:  # noqa: BLE001 - the request as it was
        return ""


def draft_request(root: Path, path: str, task: Any, specification: Any, stack: Any,
                  diagnostics: list[str] | None = None) -> str:
    """What one file's draft is asked; `diagnostics` are what the compiler reported on its last draft."""
    from app.agents.shared_facts import the_facts_section
    from app.agents.specialists import specification_for_the_work_order

    detail = specification_for_the_work_order(
        specification, SimpleNamespace(files=[path], interfaces=list(getattr(task, "interfaces", None) or [])),
    )
    target = root / path
    now = ""
    if target.is_file():
        try:
            now = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            now = ""
    criteria = "\n".join(f"- {c}" for c in getattr(task, "acceptance_criteria", None) or [])
    neighbours = _neighbours(root, path, task, detail)
    return "\n\n".join(part for part in (
        f"Write the file `{path}` of this product, exactly as its specification says. "
        f"The stack: {_stack_line(stack)}.",
        detail.strip(),
        f"--- The work order it belongs to ---\n{getattr(task, 'task_description', '')}"
        + (f"\nDone when:\n{criteria}" if criteria else ""),
        f"--- The files it works with ---\n{neighbours}" if neighbours else "",
        f"--- `{path}` as it is now; keep what still holds ---\n{now}" if now.strip() else "",
        ("--- The compiler reports, in the draft above ---\n" + "\n".join(diagnostics)) if diagnostics else "",
        # The layout every builder and judge reads (plan CM.1).
        the_facts_section(root, built=False).strip(),
        _where_dependencies_go(root),
        f"Reply with the complete content of `{path}` and nothing else, in one fenced code block. "
        "Every name, signature, message, import and library call is the one the specification "
        "gives; where it gives none, write the plainest code that meets the work order.",
    ) if part)


def _draft_one(model: Any, root: Path, path: str, task: Any, specification: Any, stack: Any,
               diagnostics: list[str] | None = None) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.observability.direct_calls import config_for_this_run

    reply = model.invoke([
        SystemMessage(content="You write source files for a software product from its specification. "
                              "You reply with one file's complete content in one fenced code block."),
        HumanMessage(content=draft_request(root, path, task, specification, stack, diagnostics)),
    ], **config_for_this_run("drafting"))
    return the_content_in(getattr(reply, "content", "") if not isinstance(reply, str) else reply)


Write = Callable[[str, str, str], Any]

#: Passes over drafted files the compiler still reports errors in.
MOST_REPAIR_PASSES = 2


def _repaired_where_the_compiler_says(
    results: list[tuple[int, str, bool]], jobs: list[tuple[int, str, Any]], diagnose: Callable[[list[str]], list[str]],
    model: Any, root: Path, repo_root: str, specification: Any, stack: Any, write: Write,
) -> None:
    """Each drafted file the compiler reports an error in, drafted again with what it reported.

    One run's drafts were written in a minute and did not compile - a
    variable declared twice, a type that did not exist - and the test round
    found it half an hour later, through a model. The compiler says it at once.
    """
    written = [path for _, path, ok in results if ok]
    tasks = {path: task for _, path, task in jobs}
    for _pass in range(MOST_REPAIR_PASSES):
        reported = diagnose(written) if written else []
        if not reported:
            return
        failing = [path for path in written if any(f"`{path}`" in line for line in reported)]
        logger.info("Drafts the compiler reports errors in, drafted again: %s", ", ".join(failing))
        for path in failing:
            mine = [line for line in reported if f"`{path}`" in line]
            try:
                content = _draft_one(model, root, path, tasks[path], specification, stack, mine)
                if content.strip():
                    write(repo_root, path, content)
            except Exception as error:  # noqa: BLE001 - the next stage meets what is there
                logger.info("Repair of draft %s failed: %s", path, str(error)[:200])


#: Words of a refused write that name the content, not the path: drafted once more with them.
CONTENT_REFUSALS = ("language service is sure of", "cannot parse this file")


def draft_work_orders(
    tasks: list[Any],
    specification: Any,
    stack: Any,
    repo_root: str,
    model: Any,
    *,
    write: Write | None = None,
    workers: int = 1,
    diagnose: Callable[[list[str]], list[str]] | None = None,
) -> dict[int, Any]:
    """Each work order whose files were all drafted, by its index, with the output an agent would return.

    A file whose draft is empty or that the workspace refuses (a syntax
    error, a path outside the project) leaves its work order to the agent
    loop. Never raises.
    """
    from app.agents.specialists import SpecialistOutput
    from app.analysis.file_kinds import classify_file

    if specification is None:
        return {}
    if write is None:
        from app.tools.repository import write_approved_artifact

        def write(root: str, path: str, content: str) -> Any:
            return write_approved_artifact(root, path, content)

    root = Path(repo_root)
    from app.tools.repository import is_secret_path

    # A credential-shaped path (`.env.example`) is one no stage may write: the
    # write is refused, and handed to the agent loop it was refused again.
    # Measured on one run. It is no draft's, and its work order is done
    # without it; the settings it would hold take development defaults.
    never_written = {
        str(path) for task in tasks for path in (getattr(task, "files", None) or [])
        if str(path).strip() and is_secret_path(Path(str(path)))
    }
    jobs = [
        (index, path, task)
        for index, task in enumerate(tasks)
        for path in (getattr(task, "files", None) or [])
        if str(path).strip() and not str(path).endswith("/") and str(path) not in never_written
    ]
    if not jobs and not never_written:
        return {}

    def run(job: tuple[int, str, Any]) -> tuple[int, str, bool]:
        index, path, task = job
        try:
            content = _draft_one(model, root, path, task, specification, stack)
            if not content.strip():
                return index, path, False
            try:
                write(repo_root, path, content)
            except Exception as refused:  # noqa: BLE001 - drafted once more with what was refused
                # What the code says - a compiler's finding or a line the
                # language cannot parse - is drafted once more with it in hand.
                # Measured on one run: a service's entry point failed to parse
                # on one line, and its whole work order went to the agent loop.
                if not any(said in str(refused) for said in CONTENT_REFUSALS):
                    raise
                content = _draft_one(model, root, path, task, specification, stack, [str(refused)])
                write(repo_root, path, content)
            return index, path, True
        except Exception as error:  # noqa: BLE001 - the agent loop takes this work order
            logger.info("Draft of %s left to the agent loop: %s", path, str(error)[:200])
            return index, path, False

    from app.observability.direct_calls import mapped_in_this_context

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        results = mapped_in_this_context(pool, run, jobs)
    if diagnose is not None:
        _repaired_where_the_compiler_says(results, jobs, diagnose, model, root, repo_root, specification, stack, write)
    drafted: dict[int, Any] = {}
    for index, task in enumerate(tasks):
        mine = [(path, ok) for i, path, ok in results if i == index]
        if not all(ok for _, ok in mine):
            continue
        if not mine and not any(str(p) in never_written for p in (getattr(task, "files", None) or [])):
            continue
        written = [path for path, _ in mine]
        skipped = [str(p) for p in (getattr(task, "files", None) or []) if str(p) in never_written]
        drafted[index] = SpecialistOutput(
            changed_files=written,
            tests=[path for path in written if classify_file(path) == "test"],
            decisions=["Drafted from the specification, one call per file (fast delivery)."]
            + [f"`{path}` is a credential file no stage writes; its settings take development defaults."
               for path in skipped],
        )
    logger.info(
        "Drafted %d of %d work order(s) from the specification (%d of %d files)",
        len(drafted), len(tasks), sum(ok for _, _, ok in results), len(results),
    )
    return drafted
