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
from typing import Any, Callable, Collection

logger = logging.getLogger(__name__)

#: The longest reply one file's draft may take, in tokens; the agent loop builds a file that needs more.
MOST_DRAFT_TOKENS = 16_000
#: Said to a draft asked again because its first came back mostly the same lines over again.
DRAFT_REPEATS = (
    "Your last draft of this file repeats the same lines over and over. Write each behaviour once: one test or "
    "one function per thing the specification asks, not one for every variant you can name."
)


def repeats_itself(content: str) -> bool:
    """Whether a draft is mostly the same lines over again: a reply caught in a loop, not a file."""
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    return len(lines) >= 300 and len(set(lines)) < len(lines) / 8


#: The most of the files it works with that one draft is shown.
MOST_NEIGHBOUR_CHARACTERS = 24_000
#: The most of one neighbour.
MOST_ONE_NEIGHBOUR_CHARACTERS = 8_000

_FENCE = re.compile(r"```[^\n`]*\n(.*?)```", re.S)
_A_PATH = re.compile(r"[\w./@-]+\.[A-Za-z0-9]{1,8}\b")


#: A line that opens or closes a fenced block.
_FENCE_LINE = re.compile(r"^[ \t]*```", re.M)


def the_content_in(reply: Any) -> str:
    """The file a reply holds: its longest fenced block, or the whole reply when it has none; "" when it was cut off.

    A reply that reached the reply cap ends inside its block, with no closing
    fence. That was taken as a file with no fence at all - the whole reply,
    its opening ```` ```python ```` line included - and written over the file,
    or, when the reply held a short block before the long one, the short one
    was. A file longer than the cap allows is the large-codebase case of it.
    "" is what every caller already treats as no draft: nothing is written and
    the file stays as it was.
    """
    from app.models.reply_text import reply_text

    # A hosted model's content is a list of blocks (its thinking, then its text): read as its text, never as the
    # list's Python form, which one run wrote into five source files.
    text = reply_text(reply)
    if len(_FENCE_LINE.findall(text)) % 2:
        return ""
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


def _neighbours(root: Path, path: str, task: Any, detail: str, code_under_test: Collection[str] = (),
                written_before: Collection[str] = ()) -> str:
    """The files this one works with, as they are on disk: the code a test tests first, then the work order's own and any its entries name.

    `written_before` - the files of earlier drafting waves this one depends on (`drafting_waves`) - come first of
    all; one too long for the room left is shown by its definitions, not cut off at its head.
    """
    named = [*written_before, *code_under_test, *(getattr(task, "files", None) or []), *_A_PATH.findall(detail)]
    earlier = {str(p).strip().lstrip("./") for p in written_before}
    shown, used = [], 0
    for other in dict.fromkeys(named):
        other = other.strip().lstrip("./")
        if not other or other == path.lstrip("./"):
            continue
        candidates = [root / other, *(root.glob(f"*/{other}"))]
        target = next((c for c in candidates if c.is_file()), None)
        if target is None:
            # Deeper than one folder: the one file whose path ends so (see `the_file_ending`).
            from app.analysis.walk import the_file_ending
            from app.tools.repository import IGNORED_DIRECTORIES

            target = the_file_ending(root, other, IGNORED_DIRECTORIES)
        if target is None:
            continue
        try:
            whole = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        text = whole[:MOST_ONE_NEIGHBOUR_CHARACTERS]
        if other in earlier and (len(whole) > len(text) or used + len(text) > MOST_NEIGHBOUR_CHARACTERS):
            from app.graph.anchored_edits import outline

            text = f"(its definitions only, by line; the file is {len(whole.splitlines())} lines)\n{outline(whole)}"
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


def _the_registry_s_releases(root: Path, path: str, specification: Any, stack: Any) -> str:
    try:
        from app.graph import registry_versions

        return registry_versions.section(root, path, specification, stack)
    except Exception:  # noqa: BLE001 - the request as it was
        return ""


def _the_naming_standard(stack: Any) -> str:
    try:
        from app.stacks.naming import standard_for

        return standard_for(stack)
    except Exception:  # noqa: BLE001 - the request as it was
        return ""


def the_reference_code(root: Path, path: str) -> str:
    """The pack's golden example as reference code for writing or fixing `path`, or "" (`contract.reference_code`)."""
    try:
        from app.stacks.contract import reference_code

        return reference_code(root, path)
    except Exception:  # noqa: BLE001 - the request as it was
        return ""


def _the_builder_s_facts(root: Path, path: str) -> str:
    try:
        from app.graph.builder_facts import section

        return section(root, path)
    except Exception:  # noqa: BLE001 - the request as it was
        return ""


#: Said to a file drafted after the files it depends on (`drafting_waves`); its own words are the switch's firing signal.
WRITTEN_BEFORE = (
    "The files it depends on were drafted before it and are shown below as they are now. Use the names, "
    "signatures, types and shared state they declare, and wire to them the way they expect; do not declare "
    "again anything they already declare. They are:"
)


def _what_a_stand_in_leaves_out(path: str) -> str:
    """The stand-in rule for a test file's draft; "" for any other file."""
    from app.agents.stand_in_rule import FOR_TEST_WRITERS
    from app.analysis.file_kinds import classify_file

    return FOR_TEST_WRITERS if classify_file(path) == "test" else ""


def _an_empty_store_of_its_own(path: str) -> str:
    """The empty-store rule for a test file's draft, with how its language gives a test its own store; "" otherwise."""
    from app.agents.own_store_rule import FOR_TEST_WRITERS
    from app.analysis.file_kinds import classify_file
    from app.analysis.stand_in_tests import row_for
    from app.stacks.languages import Gap

    if classify_file(path) != "test":
        return ""
    row = row_for(path)
    how = "" if row is None or isinstance(row.fresh_store, Gap) else " " + row.fresh_store
    return FOR_TEST_WRITERS + how


def draft_request(root: Path, path: str, task: Any, specification: Any, stack: Any,
                  diagnostics: list[str] | None = None, code_under_test: Collection[str] = (),
                  written_before: Collection[str] = (), advice: dict[str, list[str]] | None = None) -> str:
    """What one file's draft is asked; `diagnostics` are what the compiler reported on its last draft.

    `code_under_test` are the product files a unit test tests, already written: shown first, so the test uses
    their real names, signatures, messages and storage set-up instead of guessing them from the specification.
    `written_before` are the files of earlier drafting waves this file depends on (`drafting_waves`), shown first
    of all, so it wires to what they declare instead of declaring it again.
    `advice` is the specialists' advice (`specialist_advice`): the items the specification adopted for the file's
    domain, and that domain's guidance, are shown with the work order (`domain_advice`, SK.1).
    """
    from app.agents import domain_advice, domain_craft
    from app.agents.normal_form import for_a_draft as _a_group_in_its_normal_form
    from app.agents.shared_facts import the_facts_section
    from app.agents.specialists import specification_for_the_work_order
    from app.stacks import api_cards

    detail = specification_for_the_work_order(
        specification, SimpleNamespace(files=[path], interfaces=list(getattr(task, "interfaces", None) or [])), root,
    )
    target = root / path
    now = ""
    if target.is_file():
        try:
            now = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            now = ""
    criteria = "\n".join(f"- {c}" for c in getattr(task, "acceptance_criteria", None) or [])
    neighbours = _neighbours(root, path, task, detail, code_under_test, written_before)
    return "\n\n".join(part for part in (
        f"Write the file `{path}` of this product, exactly as its specification says. "
        f"The stack: {_stack_line(stack)}.",
        (WRITTEN_BEFORE + " " + ", ".join(f"`{p}`" for p in written_before)) if written_before else "",
        ("The code this test tests is already written and shown below. Call it by its real names and "
         "signatures, expect its real messages, and set up its data the way it stores it: where the code and "
         "the specification differ, test what the specification asks with the code's own names.")
        if code_under_test else "",
        # A test file is told what a test with a stand-in can check (LF.1312).
        _what_a_stand_in_leaves_out(path),
        # A test file is told that a test that stores data starts from an empty store of its own (LF.1316).
        _an_empty_store_of_its_own(path),
        # A product file is told a group of values compared in a normal form is reported in that form (LF.1317).
        _a_group_in_its_normal_form(path),
        detail.strip(),
        f"--- The work order it belongs to ---\n{getattr(task, 'task_description', '')}"
        + (f"\nDone when:\n{criteria}" if criteria else ""),
        # The adopted advice of the file's domain and its guidance (SK.1); a craft checklist (SK.2, off until measured).
        domain_advice.for_a_draft(advice, specification, task, path),
        domain_craft.for_a_draft(root, task, path),
        f"--- The files it works with ---\n{neighbours}" if neighbours else "",
        f"--- `{path}` as it is now; keep what still holds ---\n{now}" if now.strip() else "",
        ("--- The compiler reports, in the draft above ---\n" + "\n".join(diagnostics)) if diagnostics else "",
        # The layout every builder and judge reads (plan CM.1).
        the_facts_section(root, built=False).strip(),
        # The pack's golden example, for a file in its languages (deep review 2026-11-18, item E4).
        the_reference_code(root, path),
        # What a fixer is told after a failure, told before the file is written (BUILDER_FACTS).
        _the_builder_s_facts(root, path),
        _the_naming_standard(stack),
        _where_dependencies_go(root),
        # The registry's current releases, before a dependency manifest is written (plan WL.4 T4).
        _the_registry_s_releases(root, path, specification, stack),
        # The installed API of libraries newer than the model, when this file uses one (plan HK.7).
        api_cards.for_a_draft(root, path, detail),
        f"Reply with the complete content of `{path}` and nothing else, in one fenced code block. "
        "Every name, signature, message, import and library call is the one the specification "
        "gives; where it gives none, write the plainest code that meets the work order.",
    ) if part)


def _draft_one(model: Any, root: Path, path: str, task: Any, specification: Any, stack: Any,
               diagnostics: list[str] | None = None, code_under_test: Collection[str] = (),
               written_before: Collection[str] = (), advice: dict[str, list[str]] | None = None) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.observability.direct_calls import config_for_this_run

    try:
        # One file's own limit: a draft caught repeating itself ran to the model's whole reply limit (measured,
        # about 25 minutes for one test file).
        bounded = model.bind(max_tokens=MOST_DRAFT_TOKENS)
    except Exception:  # noqa: BLE001 - a model that takes no limit is asked as it is
        bounded = model
    request = draft_request(root, path, task, specification, stack, diagnostics, code_under_test, written_before,
                            advice)
    for attempt in range(2):
        reply = bounded.invoke([
            SystemMessage(content="You write source files for a software product from its specification. "
                                  "You reply with one file's complete content in one fenced code block."),
            HumanMessage(content=request),
        ], **config_for_this_run("drafting"))
        content = the_content_in(getattr(reply, "content", "") if not isinstance(reply, str) else reply)
        if not repeats_itself(content):
            return content
        request += "\n\n" + DRAFT_REPEATS
    return ""


Write = Callable[[str, str, str], Any]


def _raise_if_the_run_stopped(error: BaseException) -> None:
    from app.models.call_gate import raise_if_the_run_stopped

    raise_if_the_run_stopped(error)


def _noted(path: str, attempt: str, outcome: str) -> None:
    """One `draft` transcript record: the file, which pass (first, content-refusal, repair-n), and how it ended.

    Harness review HR2.P.5: whether a draft's repair held and why a file went to the agent loop were log lines only,
    so no change to drafting could be judged. Never raises.
    """
    try:
        from app.observability.log_context import _TASK_RUN, _from_the_graph
        from app.observability.transcript import record

        run, _ = _from_the_graph()
        record(str(run or _TASK_RUN.get() or "") or None, "drafting", "draft",
               path=str(path), attempt=attempt, outcome=str(outcome)[:300])
    except Exception:  # noqa: BLE001 - a record must never cost the draft
        logger.debug("Could not record a draft", exc_info=True)

#: Told to a file redrafted between drafting waves: what a later wave will write is not this file's to declare.
STILL_TO_COME = (
    "These files are drafted after this one and are not written yet; a name they will declare is not missing "
    "from this file and is not to be declared here:"
)
#: Passes over drafted files the compiler still reports errors in.
MOST_REPAIR_PASSES = 2


def _repaired_where_the_compiler_says(
    results: list[tuple[int, str, bool]], jobs: list[tuple[int, str, Any]], diagnose: Callable[[list[str]], list[str]],
    model: Any, root: Path, repo_root: str, specification: Any, stack: Any, write: Write,
    not_yet_written: Collection[str] = (), needs: dict[str, list[str]] | None = None,
) -> None:
    """Each drafted file the compiler reports an error in, drafted again with what it reported.

    One run's drafts were written in a minute and did not compile - a
    variable declared twice, a type that did not exist - and the test round
    found it half an hour later, through a model. The compiler says it at once.

    After a drafting wave (`drafting_waves`), `not_yet_written` are the files later waves will draft: a report that
    names one is theirs to answer, not this wave's, and a redraft is told they are still to come.
    """
    written = [path for _, path, ok in results if ok]
    tasks = {path: task for _, path, task in jobs}
    needs = needs or {}
    from app.graph.builder_facts import compiler_lines
    from app.graph.fewest_findings import BestVersions

    later = [str(p) for p in not_yet_written]
    later_names = re.compile(
        r"(?<![\w-])(?:" + "|".join(re.escape(n) for p in later for n in {PurePosixPath(p).name, PurePosixPath(p).stem}
                                     if n) + r")(?![\w])"
    ) if later else None

    def reported_now() -> list[str]:
        reported = diagnose(written) if written else []
        # The compiler's own errors beside the language service's: `tsc` reports a router handed to `app.use`, the
        # service does not (BUILDER_FACTS).
        found = [*reported, *(line for line in compiler_lines(repo_root, written) if line not in reported)]
        return [line for line in found if later_names is None or not later_names.search(line)]

    # Each file's version with the fewest errors is what stays, the draft included (A2): the last repair was kept
    # unmeasured, even when it made the file worse than the draft before it.
    best = BestVersions()
    for _pass in range(MOST_REPAIR_PASSES + 1):
        reported = reported_now()
        best.offer_as_they_are(root, written, reported)
        if not reported or _pass == MOST_REPAIR_PASSES:
            break
        # An error the pack knows carries its cause into the redraft (deep review 2026-11-18, item E4); counted
        # above without it, so the cause never changes which version has fewer errors.
        from app.stacks.known_errors import with_known_causes_in_lines

        reported = with_known_causes_in_lines(repo_root, reported)
        failing = [path for path in written if any(f"`{path}`" in line for line in reported)]
        logger.info("Drafts the compiler reports errors in, drafted again: %s", ", ".join(failing))
        for path in failing:
            mine = [line for line in reported if f"`{path}`" in line]
            if later:
                mine.append(STILL_TO_COME + " " + ", ".join(f"`{p}`" for p in later))
            earlier = {"written_before": needs[path]} if needs.get(path) else {}
            try:
                content = _draft_one(model, root, path, tasks[path], specification, stack, mine, **earlier)
                if content.strip():
                    write(repo_root, path, content)
                    _noted(path, f"repair-{_pass + 1}", "accepted")
                else:
                    _noted(path, f"repair-{_pass + 1}", "empty; the earlier draft stays")
            except Exception as error:  # noqa: BLE001 - the next stage meets what is there
                _raise_if_the_run_stopped(error)
                logger.info("Repair of draft %s failed: %s", path, str(error)[:200])
                _noted(path, f"repair-{_pass + 1}", f"refused; the earlier draft stays: {error}")
    for path in best.put_back(root, write):
        _noted(path, "repair", "an earlier version the compiler reported fewer errors in was kept")


#: Words of a refused write that name the content, not the path: drafted once more with them.
CONTENT_REFUSALS = ("language service is sure of", "cannot parse this file")


#: What a work order promises in its `interfaces`, in the words the lead writes them: `export function makeThing(...)`,
#: `export interface Thing`, `def make_thing(`, `class Thing`.
_A_PROMISED_NAME = re.compile(
    r"\bexport\s+(?:default\s+)?(?:async\s+)?(?:abstract\s+)?(?:interface|class|function|const|let|type|enum)\s+([A-Za-z_$][\w$]*)"
    r"|\b(?:def|class)\s+([A-Za-z_]\w*)"
)
_A_DEFINITION = (
    r"(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:abstract\s+)?"
    r"(?:interface|class|function|const|let|var|type|enum|def|fn|func|struct|trait)\s+{name}\b"
)


def promised_names(task: Any) -> list[str]:
    """The names a work order says its files will export or define; [] when it names none."""
    found: list[str] = []
    for line in getattr(task, "interfaces", None) or []:
        for match in _A_PROMISED_NAME.finditer(str(line)):
            name = match.group(1) or match.group(2)
            if name and name not in found:
                found.append(name)
    return found


def not_defined_in(names: list[str], files: dict[str, str]) -> list[str]:
    """The promised names no drafted file defines (the word only mentioned or imported does not count)."""
    return [
        name for name in names
        if not any(re.search(_A_DEFINITION.format(name=re.escape(name)), text) for text in files.values())
    ]


def _promised_but_not_written(task: Any, written: list[str], root: Path) -> list[str]:
    """The names the work order promises that none of its written files defines; [] when it names none or all are there."""
    names = promised_names(task)
    if not names:
        return []
    texts: dict[str, str] = {}
    for path in written:
        try:
            texts[path] = (root / path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return not_defined_in(names, texts) if texts else []


Job = tuple[int, str, Any]


def _in_waves(code_jobs: list[Job], tasks: list[Any], specification: Any,
              repo_root: str) -> tuple[list[list[Job]], dict[str, list[str]]]:
    """The product's code drafts in the waves `drafting_waves` orders them in, and what each file depends on.

    One wave of them all, as before, when `DRAFTING_IN_WAVES` is off, the product has one or two code files, or
    nothing known before drafting orders them. Never raises.
    """
    if not code_jobs:
        return [], {}
    try:
        from app.graph import drafting_waves

        if not drafting_waves.enabled():
            return [code_jobs], {}
        try:
            from app.stacks.scaffold import _served_entrypoints

            project, served = _served_entrypoints(repo_root)
            entrypoints = [f"{project}/{entry}" if project else entry for entry in served]
        except Exception:  # noqa: BLE001 - no pack, no entry file known
            entrypoints = []
        planned = drafting_waves.drafting_waves([path for _, path, _ in code_jobs], tasks, specification, entrypoints)
    except Exception:  # noqa: BLE001 - drafted in one wave, as before
        logger.debug("Could not order the drafts in waves", exc_info=True)
        return [code_jobs], {}
    if len(planned.waves) <= 1:
        return [code_jobs], {}
    by_path: dict[str, list[Job]] = {}
    for job in code_jobs:
        by_path.setdefault(job[1], []).append(job)
    waves = [[job for path in wave for job in by_path.get(path, ())] for wave in planned.waves]
    logger.info("Drafting in %d waves: %s", len(waves),
                " | ".join(", ".join(path for _, path, _ in wave) for wave in waves))
    return [wave for wave in waves if wave], planned.needs


#: The author the project memory records for a file the drafting pass wrote.
DRAFTING_STAGE = "drafting"


def remember_drafted(repo_root: str | Path, paths: list[str]) -> None:
    """Record the drafting pass as the stage that changed each file it wrote. Never raises.

    Its writes run outside a stage's config, so the write tools recorded no author: measured on one run, every
    product file a sprint drafted read as unwritten, and the next builder opened on the plans whole
    (`project_memory.builds_on_code`).
    """
    try:
        from app.analysis import project_memory

        for path in paths:
            project_memory.record(repo_root, path, DRAFTING_STAGE)
    except Exception:  # noqa: BLE001 - bookkeeping never fails a draft
        logger.debug("Could not record the drafted files", exc_info=True)


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
    kept: Collection[str] = (),
    advice: dict[str, list[str]] | None = None,
) -> dict[int, Any]:
    """Each work order whose files were all drafted, by its index, with the output an agent would return.

    A file whose draft is empty or that the workspace refuses (a syntax
    error, a path outside the project) leaves its work order to the agent
    loop. Raises only `RunCancelled`: a run paused or stopped mid-way drafts again on resume.
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
        # A file the best attempt already has, on a re-plan, stays as it is (`best_attempt.files_the_best_attempt_already_has`).
        and str(path) not in kept
    ]
    if not jobs and not never_written and not kept:
        return {}

    needs: dict[str, list[str]] = {}

    def run(job: tuple[int, str, Any], code_under_test: Collection[str] = ()) -> tuple[int, str, bool]:
        index, path, task = job
        attempt = "first"
        # The files of earlier waves it depends on, those that were written (`drafting_waves`).
        earlier: dict[str, Any] = {"written_before": needs[path]} if needs.get(path) else {}
        if advice:
            earlier["advice"] = advice  # the adopted advice of the file's domain (SK.1)
        try:
            content = _draft_one(model, root, path, task, specification, stack, None, code_under_test, **earlier)
            if not content.strip():
                _noted(path, attempt, "left to the loop: the draft was empty")
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
                _noted(path, attempt, f"refused for its content: {refused}")
                attempt = "content-refusal"
                content = _draft_one(model, root, path, task, specification, stack, [str(refused)], code_under_test,
                                     **earlier)
                write(repo_root, path, content)
            _noted(path, attempt, "accepted")
            return index, path, True
        except Exception as error:  # noqa: BLE001 - the agent loop takes this work order
            _raise_if_the_run_stopped(error)
            logger.info("Draft of %s left to the agent loop: %s", path, str(error)[:200])
            _noted(path, attempt, f"left to the loop: {error}")
            return index, path, False

    from app.observability.direct_calls import mapped_in_this_context

    # The product first, its unit tests after: drafted in one batch, a test was written before the code it tests
    # and guessed its signatures, messages and storage - measured over 18 runs, 25 of 31 fixes of failing unit
    # tests were left open. Each test is shown the product files drafted here, those it names first.
    code_jobs = [job for job in jobs if classify_file(job[1]) != "test"]
    test_jobs = [job for job in jobs if classify_file(job[1]) == "test"]
    waves, waves_needs = _in_waves(code_jobs, tasks, specification, repo_root)
    results: list[tuple[int, str, bool]] = []
    for number, wave in enumerate(waves):
        # Each wave's files drafted side by side, as the one wave was; a later wave reads what the earlier wrote.
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            done = mapped_in_this_context(pool, run, wave)
        results += done
        written_so_far = {path for _, path, ok in results if ok}
        for job in (job for later in waves[number + 1:] for job in later):
            needs[job[1]] = [used for used in waves_needs.get(job[1], ()) if used in written_so_far]
        if diagnose is not None and number < len(waves) - 1:
            # A later wave builds on files that compile (deep review 2026-11-18, item 1.6).
            _repaired_where_the_compiler_says(
                done, wave, diagnose, model, root, repo_root, specification, stack, write,
                not_yet_written=[job[1] for later in waves[number + 1:] for job in later], needs=needs,
            )
    drafted_code = [path for _, path, ok in results if ok]

    def the_code_it_tests(path: str, task: Any) -> list[str]:
        words = set(re.findall(r"[a-z0-9]+", f"{path} {getattr(task, 'task_description', '')}".lower())) - {"test", "tests", "spec"}
        named = [code for code in drafted_code if PurePosixPath(code).stem.lower() in words]
        return [*named, *(code for code in drafted_code if code not in named)]

    if test_jobs:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            results += mapped_in_this_context(pool, lambda job: run(job, the_code_it_tests(job[1], job[2])), test_jobs)
    if diagnose is not None:
        _repaired_where_the_compiler_says(results, jobs, diagnose, model, root, repo_root, specification, stack, write,
                                          needs=needs)
    remember_drafted(repo_root, [path for _, path, ok in results if ok])
    drafted: dict[int, Any] = {}
    for index, task in enumerate(tasks):
        mine = [(path, ok) for i, path, ok in results if i == index]
        if not all(ok for _, ok in mine):
            continue
        if not mine and not any(str(p) in never_written or str(p) in kept for p in (getattr(task, "files", None) or [])):
            continue
        written = [path for path, _ in mine]
        left = [str(p) for p in (getattr(task, "files", None) or []) if str(p) in kept]
        # A file drafted from a specification that does not describe what the work order adds comes out as the
        # file it was: measured, a work order to add a SQLite store was recorded as done with `store.ts` unchanged.
        # A work order is done when what it promised is there; else the agent loop builds it, as for a failed file.
        absent = _promised_but_not_written(task, [*written, *left], root)
        if absent:
            logger.info("Work order %d is left to the agent loop: its files do not define %s", index, ", ".join(absent))
            for path in written:
                _noted(path, "promise check", f"left to the loop: the work order's files do not define {', '.join(absent)}")
            continue
        skipped = [str(p) for p in (getattr(task, "files", None) or []) if str(p) in never_written]
        drafted[index] = SpecialistOutput(
            changed_files=written,
            tests=[path for path in written if classify_file(path) == "test"],
            decisions=["Drafted from the specification, one call per file (fast delivery)."]
            + [f"`{path}` is a credential file no stage writes; its settings take development defaults."
               for path in skipped]
            + [f"`{path}` was left as the best attempt so far had it." for path in left],
        )
    logger.info(
        "Drafted %d of %d work order(s) from the specification (%d of %d files)",
        len(drafted), len(tasks), sum(ok for _, _, ok in results), len(results),
    )
    return drafted
