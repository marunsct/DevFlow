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
from typing import Any, Callable, Sequence

from app.observability.direct_calls import config_for_this_run, mapped_in_this_context

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


#: A line that warns and does not fail: `FooWarning:`, `warning:`, `(node:12) Warning:`.
_WARNS = re.compile(r"warning\b", re.I)
_FAILS = re.compile(r"\berror\b|\bfailed\b|exception|traceback", re.I)


def _only_warns(text: str, at: int) -> bool:
    """Whether the line of `text` holding position `at` is a warning and nothing worse."""
    start = text.rfind("\n", 0, at) + 1
    end = text.find("\n", at)
    line = text[start:end if end >= 0 else len(text)]
    return bool(_WARNS.search(line)) and not _FAILS.search(line)


#: Where the run's last failing command begins in `what_failed`: whatever stage ran
#: it, which need not be this defect's.
THE_LAST_FAILING_COMMAND = "The last failing command printed:"
#: How a defect raised from the unit tests' own failure begins (`workflow.UNIT_TESTS_FAIL`).
_THE_UNIT_TESTS_FAIL = "The unit tests fail."


def what_failed(defect: Any, repo_root: str | Path, last_failure: Any = None) -> str:
    """What the defect's failing tests and last failing command printed, as one text.

    The defect's own words come first and the runner's output after them; over the budget, the output keeps at least
    half of it. Found in a code review: each reverted fix added its note to the defect, the notes reached about 4,200
    characters after three reverts, and the output after them was cut at test 23 of 79.
    """
    own: list[str] = []
    for field in ("actual_behavior", "reproduction_steps"):
        value = getattr(defect, field, "")
        text = "\n".join(map(str, value)) if isinstance(value, (list, tuple)) else str(value or "")
        if text.strip():
            own.append(text.strip())
    parts: list[str] = []
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
            parts.append(f"{THE_LAST_FAILING_COMMAND}\n{printed}")
    said, printed = "\n\n".join(own), "\n\n".join(parts)
    if len(said) + len(printed) + 2 <= MOST_FAILURE_CHARACTERS:
        return "\n\n".join(part for part in (said, printed) if part)
    # Cut from the front, so frames outside the project would push the
    # project's own lines and the assertion out first (plan SZ.3).
    from app.analysis.tracebacks import without_outside_frames

    said, printed = without_outside_frames(said, repo_root), without_outside_frames(printed, repo_root)
    if not printed:
        return said[:MOST_FAILURE_CHARACTERS]
    room = max(MOST_FAILURE_CHARACTERS - len(printed) - 2, MOST_FAILURE_CHARACTERS // 2)
    said = said[:room]
    text = "\n\n".join(part for part in (said, printed) if part)
    return text[:MOST_FAILURE_CHARACTERS]


def files_to_fix(defect: Any, failure: str, repo_root: str | Path, may_write: Callable[[str], bool]) -> list[str]:
    """The workspace files a fix rewrites: the ones the defect names, then the ones its failure points at."""
    from app.acceptance.junit import tags_in

    root = Path(repo_root)

    # A criterion the acceptance suite judges is the product's, never a unit
    # test's: the suite runs the product. Measured live: a login criterion's
    # rewrite took `tests/test_auth.py` from the run's last failing command,
    # rewrote it, and the defect was recorded as fixed with the login still
    # broken - and with it every test that needs a signed-in user.
    # A test is rewritten from failure text only for a defect the unit tests
    # themselves raised, whose test may be the thing that is wrong; any defect
    # still rewrites a test it names as its own.
    tests_from_the_text = str(getattr(defect, "description", "") or "").startswith(_THE_UNIT_TESTS_FAIL)
    # Not a failing unit run, whatever ids its tests' names carry: measured on two runs, unit tests named
    # "AC-1 CreateNoteTest" made it read as the suite's, every test file was left out, and both fixes rewrote the
    # product, broke other unit tests and were reverted.
    judged_by_the_suite = not tests_from_the_text and any(
        t.startswith(("AC-", "CR-")) for t in tags_in(str(getattr(defect, "description", "") or ""))
    )
    named = [str(f).strip().lstrip("./") for f in getattr(defect, "affected_files", None) or [] if str(f).strip()]
    # A trace that prints absolute paths - most runtimes but Python's - names
    # the workspace's files under its root.
    failure = failure.replace(str(root).rstrip("/") + "/", "")
    # The defect's own evidence first; the run's last failing command only when
    # that names no file. Measured live: a page check's "the interface is not
    # styled" was rewritten as its stylesheet and `tests/test_tasks.py` - named
    # by another fixer's unit-test run, the run's last failure - the test file
    # broke 17 tests, and the revert took the stylesheet with it.
    own, _, last = failure.partition(THE_LAST_FAILING_COMMAND)

    def mentioned_in(text: str) -> list[str]:
        # In the order the text names them, with a line or without - but not
        # where a line only warns. Measured live: a service failed at start-up
        # in the module that opens its database, the one product file its
        # output named was a deprecation warning's, and the rewrite fixed that.
        return [name.lstrip("./") for _, name in sorted(
            (m.start(), m.group(1))
            for pattern in (_AN_ERROR_LOCATION, _A_FILE_NAMED)
            for m in pattern.finditer(text)
            if not _only_warns(text, m.start())
        )]

    def files(mentioned: list[str]) -> list[str]:
        return _the_files(root, named, mentioned, judged_by_the_suite, tests_from_the_text, may_write)

    found = files(mentioned_in(own))
    if last and len(found) == len(files([])):
        found = files(mentioned_in(own) + mentioned_in(last))
    owing = [name for name in _modules_missing_an_export(own, root) if may_write(name)]
    if owing:
        # The module that should export it is the file to write; the test that imports it is left as it is.
        from app.analysis.file_kinds import classify_file

        found = [*owing, *(name for name in found if name not in owing and classify_file(name) != "test")][:MOST_FILES]
    return found



def _the_project_ignores(root: Path, relative: str) -> bool:
    """Whether the project's own ignore rules exclude the file: a report, a build, a cache - never its source.

    Measured live: two fixes in a row took `test-results/acceptance.xml`,
    named in the failure text, as the file to rewrite, rewrote the runner's
    report, and left both defects open. Asked of git, so every stack's own
    ignore file answers. False when there is no repository to ask.
    """
    import subprocess

    try:
        done = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", "--", relative],
                              capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0

def _a_test_report(root: Path, relative: str, target: Path) -> bool:
    """Whether the file is a test runner's report: one the setup declares, or any JUnit XML document.

    Measured live, on a setup whose `.gitignore` did not list its `reports/` folder: two fixes in a
    row took `reports/unit.xml`, named in the failure text, as the file to rewrite - 27,000 tokens
    spent on a file the next run overwrites, both defects left open, the sprint planned again.
    `_the_project_ignores` answers only when the project's ignore file happens to say so.
    """
    try:
        from app.stacks import contract

        record = contract.read(root) or {}
        project = str(record.get("project") or "")
        declared = {f"{project}/{record[key]}".strip("/") for key in ("unit_report", "acceptance_report") if record.get(key)}
        if relative in declared:
            return True
    except Exception:  # noqa: BLE001 - the content decides
        pass
    if target.suffix.lower() == ".xml":
        try:
            return "<testsuite" in target.read_text(encoding="utf-8", errors="replace")[:2_000]
        except OSError:
            return False
    return False


#: TypeScript's ESM idiom: a module is imported by the name of the file it compiles to.
_COMPILED_TO = {".js": (".ts", ".tsx"), ".jsx": (".tsx",), ".mjs": (".mts",), ".cjs": (".cts",)}


def _its_typescript_sources(name: str) -> list[str]:
    """`src/store.ts` for `src/store.js`: the sources a compiled name stands for; [] for any other name.

    Measured: a test failed on "Module '../src/store.js' has no exported member", the fix looked for
    `src/store.js`, found no such file (it is `store.ts`), and rewrote only the test.
    """
    for suffix, sources in _COMPILED_TO.items():
        if name.endswith(suffix):
            return [name[: -len(suffix)] + source for source in sources]
    return []


#: How a missing export is worded, by language tool: the module that should have exported it is group 1.
_A_MISSING_EXPORT = (
    re.compile(r"""[Mm]odule ['"]+([^'"\n]+?)['"]+ has no exported member"""),
    re.compile(r"""requested module ['"]([^'"\n]+)['"] does not provide an export named"""),
)


def _modules_missing_an_export(failure: str, root: Path) -> list[str]:
    """The product source files a failure says should export something they do not: where the fix belongs.

    An import error is reported in the file that imports; the repair is in the module that is imported. Measured:
    the fix rewrote the importing test to define the missing function itself, the type error went away, and the
    feature was never built.
    """
    from app.analysis.file_kinds import classify_file
    from app.analysis.walk import the_file_ending
    from app.tools.repository import IGNORED_DIRECTORIES

    found: list[str] = []
    for pattern in _A_MISSING_EXPORT:
        for match in pattern.finditer(failure):
            spec = match.group(1).strip().lstrip("./")
            for spelling in (spec, *_its_typescript_sources(spec)):
                target = the_file_ending(root, spelling, IGNORED_DIRECTORIES)
                if target is None:
                    continue
                relative = target.relative_to(root).as_posix()
                if classify_file(relative) != "test" and relative not in found:
                    found.append(relative)
                break
    return found


def _the_files(
    root: Path, named: list[str], mentioned: list[str], judged_by_the_suite: bool, tests_from_the_text: bool,
    may_write: Callable[[str], bool],
) -> list[str]:
    """The workspace files to rewrite: those the defect names, then those its failure text mentions."""
    from app.analysis.file_kinds import classify_file, is_scratch
    from app.tools.repository import IGNORED_DIRECTORIES

    own = set(named)
    found: list[str] = []
    for name in dict.fromkeys([*named, *mentioned]):
        target = None
        for spelling in (name, *_its_typescript_sources(name)):
            candidates = [root / spelling, *root.glob(f"*/{spelling}")]
            target = next((c for c in candidates if c.is_file()), None)
            if target is None:
                # Deeper than one folder: the one file whose path ends so (see `the_file_ending`).
                from app.analysis.walk import the_file_ending

                target = the_file_ending(root, spelling, IGNORED_DIRECTORIES)
            if target is not None:
                break
        if target is None or any(part in IGNORED_DIRECTORIES for part in target.parts):
            continue
        relative = target.relative_to(root).as_posix()
        # A stage's throwaway probe is no part of the product. Measured live:
        # one fixer's `tmp-check-*.py` failed, its traceback reached two later
        # fixes as what failed, and each rewrote the probe and was recorded
        # as having fixed its defect.
        is_a_test = classify_file(relative) == "test"
        if (is_scratch(relative) or (judged_by_the_suite and is_a_test) or _the_project_ignores(root, relative)
                or _a_test_report(root, relative, target)):
            continue
        if is_a_test and name not in own and not tests_from_the_text:
            continue
        if relative not in found and may_write(relative):
            found.append(relative)
        if len(found) >= MOST_FILES:
            break
    return found


def fix_request(root: Path, path: str, defect: Any, failure: str, specification: Any,
                stack: Any, others: list[str], diagnostics: list[str], co_failures: str = "") -> str:
    """What one file's rewrite is asked. `co_failures`: the other open defects that point at this file (`co_defect_failures`)."""
    from app.agents.shared_facts import the_facts_section
    from app.agents.specialists import specification_for_the_work_order
    from app.graph.drafting import _neighbours, _stack_line
    from types import SimpleNamespace

    from app.graph import anchored_edits

    detail = specification_for_the_work_order(specification, SimpleNamespace(files=[path], interfaces=[])) if specification else ""
    now = (root / path).read_text(encoding="utf-8", errors="replace")
    # Too long to come back whole within a reply: its outline and the parts
    # the failure points at, answered by anchored edits (plan SZ.2).
    long_file = anchored_edits.too_long_to_rewrite(now)
    unapplied = [line for line in diagnostics if anchored_edits.AN_EDIT_NOT_APPLIED in line]
    diagnostics = [line for line in diagnostics if anchored_edits.AN_EDIT_NOT_APPLIED not in line]
    from app.agents import project_memory

    if project_memory.enabled():
        # The whole project as it is now, the files the failure names first,
        # rather than only the files this one imports. See `app.agents.project_memory`.
        neighbours, held = project_memory.render(root, MEMORY_CHARACTERS, focus=f"{path}\n{failure}")
    else:
        neighbours, held = _neighbours(root, path, SimpleNamespace(files=others), detail), {}
    # What happened to the attempts before this one: a rewrite asked again
    # exactly as before wrote the same change, and was reverted for the same
    # broken test - measured on the first all-on run, two identical requests
    # and two identical reverts in one sprint attempt.
    from app.agents.ledger import earlier_attempts

    actual = str(getattr(defect, "actual_behavior", "") or "").strip()
    return "\n\n".join(part for part in (
        f"Correct the file `{path}` of this product so the failure below no longer happens. "
        f"The stack: {_stack_line(stack)}.",
        f"--- The defect ---\n{getattr(defect, 'description', '')}\n"
        f"Expected: {getattr(defect, 'expected_behavior', '')}"
        + (f"\nActual: {actual}" if actual else ""),
        earlier_attempts(defect).strip(),
        f"--- What failed ---\n{failure}" if failure.strip() else "",
        co_failures,
        ("--- The compiler still reports, in the files just written ---\n" + "\n".join(diagnostics)) if diagnostics else "",
        ("--- Edits from the last pass that were not made, and why ---\n" + "\n".join(unapplied)) if unapplied else "",
        detail.strip(),
        f"--- The project ---\n{neighbours}" if neighbours else "",
        (anchored_edits.in_the_memory(path) if held.get(path) == now
         else anchored_edits.excerpt(path, now, failure, _the_defect_s_words(defect))) if long_file
        else f"--- `{path}` as it is now ---\n{now}",
        # The facts every builder and judge reads (plan CM.1).
        the_facts_section(root).strip(),
        anchored_edits.instruction(path) if long_file else
        f"Reply with the complete corrected content of `{path}` and nothing else, in one fenced "
        "code block. Change only what the failure needs; keep every name, signature and "
        "message the specification gives. If this file needs no change for this failure, "
        "reply with it unchanged.",
    ) if part)


def _the_defect_s_words(defect: Any) -> str:
    return "\n".join(str(getattr(defect, field, "") or "") for field in ("description", "expected_behavior", "actual_behavior"))


#: What a whole-file fix is told it replies with; see `anchored_edits.SYSTEM` for a long file.
WHOLE_FILE_SYSTEM = "You correct source files of a software product. You reply with one file's complete content in one fenced code block."


def _system_for(text: str) -> str:
    from app.graph import anchored_edits

    return anchored_edits.SYSTEM if anchored_edits.too_long_to_rewrite(text) else WHOLE_FILE_SYSTEM


def _the_reply_s_file(path: str, original: str, reply: Any) -> str:
    """The file a reply makes of `original`: its whole content, or `original` with its anchored edits made.

    Raises RepositoryToolError when an anchored edit cannot be made (`anchored_edits.applied`).
    """
    from app.graph import anchored_edits
    from app.graph.drafting import the_content_in

    text = getattr(reply, "content", reply) if not isinstance(reply, str) else reply
    if anchored_edits.too_long_to_rewrite(original):
        return anchored_edits.applied(path, original, text if isinstance(text, str) else str(text))
    return the_content_in(text)


def fix_by_rewriting(
    defect: Any, repo_root: str | Path, model: Any, *, specification: Any = None, stack: Any = None,
    last_failure: Any = None, may_write: Callable[[str], bool] | None = None,
    write: Callable[[str, str, str], Any] | None = None,
    diagnose: Callable[[list[str]], list[str]] | None = None,
    files: list[str] | None = None, co_defects: Sequence[Any] = (),
) -> Any | None:
    """The fix stage's output for a defect fixed by rewriting its files, or None for the agent loop.

    `co_defects`: the other open defects, whose failures that point at a file go into its rewrite (`co_defect_failures`).

    `files`, when given, is used as the files to rewrite and no localisation
    call is made: a retry that already asked `fix_by_candidates` where the
    defect lives need not ask again. See `app.graph.workflow._fixed_by_rewriting`.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.agents.specialists import SpecialistOutput
    from app.graph.anchored_edits import AN_EDIT_NOT_APPLIED
    from app.tools.repository import RepositoryToolError

    root = Path(repo_root)
    if write is None:
        from app.tools.repository import write_approved_artifact

        def write(base: str, path: str, content: str) -> Any:
            return write_approved_artifact(base, path, content)

    failure = what_failed(defect, root, last_failure)
    if files is None:
        files = files_to_fix(defect, failure, root, may_write or (lambda _: True))
        # Asked where, once and cheaply, when the failure named none or many (plan AY step 1, off).
        from app.graph.localisation import localised

        files = localised(defect, failure, root, model, files, may_write or (lambda _: True))
    if not files:
        return None
    from app.graph import co_defect_failures, repeated_rewrite_prompts

    co_failures = co_defect_failures.failures_by_file(co_defects, root, may_write or (lambda _: True))
    changed: list[str] = []
    diagnostics: list[str] = []
    for _pass in range(MOST_PASSES):
        targets = files if not diagnostics else [f for f in files if any(f"`{f}`" in d for d in diagnostics)] or files
        for path in targets:
            try:
                active_model = model
                if active_model is None:
                    try:
                        from app.models import build_default_chat_model

                        active_model = build_default_chat_model()
                    except Exception:  # noqa: BLE001 - a model that cannot be built leaves the defect for the loop
                        active_model = None
                if active_model is None or not hasattr(active_model, "invoke"):
                    logger.info("Rewrite of %s skipped: no chat model available for rewriting", path)
                    if not changed:
                        return None
                    break
                current = (root / path).read_text(encoding="utf-8", errors="replace")
                asked = fix_request(root, path, defect, failure, specification, stack,
                                    [f for f in files if f != path], diagnostics, co_failures.get(path, ""))
                if repeated_rewrite_prompts.exhausted(root, asked):
                    logger.info("Rewrite of %s not sent: the same request has failed %d times", path,
                                repeated_rewrite_prompts.MOST_IDENTICAL)
                    if not changed:
                        return None
                    continue
                # Counted as failed when sent: a rewrite that holds closes its defect and is not asked again.
                repeated_rewrite_prompts.failed(root, asked)
                reply = active_model.invoke([
                    SystemMessage(content=_system_for(current)),
                    HumanMessage(content=asked),
                ], **config_for_this_run("defect_fix"))
                try:
                    content = _the_reply_s_file(path, current, reply)
                except RepositoryToolError as unapplied:
                    # An anchored edit that matched nowhere or more than once:
                    # the file stays as it was and the next pass is told why.
                    diagnostics = [*diagnostics, f"- In `{path}`: {unapplied}"]
                    continue
                if not content.strip():
                    continue
                if content != current:
                    try:
                        write(str(root), path, content)
                    except Exception as refused:  # noqa: BLE001 - the next pass is told what was refused
                        if "language service is sure of" not in str(refused):
                            raise
                        diagnostics = [*diagnostics, f"- In `{path}`: {refused}"]
                        continue
                    if path not in changed:
                        changed.append(path)
                    # Made now: what an earlier pass was told of its edits is past.
                    diagnostics = [d for d in diagnostics if not (AN_EDIT_NOT_APPLIED in d and f"`{path}`" in d)]
            except Exception as error:  # noqa: BLE001 - the agent loop takes what this could not
                logger.info("Rewrite of %s for a fix failed: %s", path, str(error)[:200])
                if not changed:
                    return None
        refused = [line for line in diagnostics if "language service is sure of" in line or AN_EDIT_NOT_APPLIED in line]
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
    candidates: int = CANDIDATES, files: list[str] | None = None, co_defects: Sequence[Any] = (),
) -> Any | None:
    """A defect fixed by several candidate rewrites asked for at once, the first its tests pass kept; or None.

    `files`, when given, is used as the files to change and no localisation
    call is made. See `app.graph.workflow._fixed_by_rewriting`.

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

    root = Path(repo_root)
    if write is None:
        from app.tools.repository import write_approved_artifact

        def write(base: str, path: str, content: str) -> Any:
            return write_approved_artifact(base, path, content)

    # Candidates are chosen by their tests: a defect with none has nothing to
    # choose by, so the first that changed anything was kept unchecked and the
    # others were paid for and thrown away. The single rewrite or the agent
    # loop takes it.
    try:
        if check() is None:
            return None
    except Exception:  # noqa: BLE001 - nothing to choose by
        return None
    failure = what_failed(defect, root, last_failure)
    if files is None:
        files = files_to_fix(defect, failure, root, may_write or (lambda _: True))
        # Asked where, once and cheaply, when the failure named none or many (plan AY step 1, off).
        from app.graph.localisation import localised

        files = localised(defect, failure, root, model, files, may_write or (lambda _: True))
    if not files:
        return None
    originals = {path: (root / path).read_text(encoding="utf-8", errors="replace") for path in files}
    from app.graph import co_defect_failures, repeated_rewrite_prompts

    co_failures = co_defect_failures.failures_by_file(co_defects, root, may_write or (lambda _: True))
    #: Every request sent, so each is counted once as failed when no candidate passes (`repeated_rewrite_prompts`).
    sent: list[str] = []

    def one(path_and_index: tuple[str, int]) -> tuple[int, str, str]:
        path, index = path_and_index
        try:
            active_model = model
            if active_model is None:
                try:
                    from app.models import build_default_chat_model

                    active_model = build_default_chat_model()
                except Exception:  # noqa: BLE001
                    active_model = None
            if active_model is None or not hasattr(active_model, "invoke"):
                return index, path, ""
            asked = fix_request(root, path, defect, failure, specification, stack,
                                [f for f in files if f != path], [], co_failures.get(path, ""))
            if repeated_rewrite_prompts.exhausted(root, asked):
                return index, path, ""
            sent.append(asked)
            reply = active_model.invoke([
                SystemMessage(content=_system_for(originals[path])),
                HumanMessage(content=asked),
            ], **config_for_this_run("defect_fix"))
            # A long file's anchored edits that cannot be made leave this
            # candidate without the file, like a reply that failed.
            return index, path, _the_reply_s_file(path, originals[path], reply)
        except Exception as error:  # noqa: BLE001 - one candidate fewer
            logger.info("A candidate rewrite of %s failed: %s", path, str(error)[:200])
            return index, path, ""

    with ThreadPoolExecutor(max_workers=max(1, candidates * len(files))) as pool:
        written = mapped_in_this_context(pool, one, [(path, index) for index in range(candidates) for path in files])
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
    for asked in sent:
        repeated_rewrite_prompts.failed(root, asked)
    logger.info("No candidate fix of %d passed its tests; the agent loop takes the defect", candidates)
    return None
