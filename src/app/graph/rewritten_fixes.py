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

from app.tools.version_control import git_safely  # noqa: E402

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
_A_FILE_NAMED = re.compile(r"(?<![\w/.@-])((?:[\w@-]+/)*[\w@-]+(?:\.[A-Za-z][A-Za-z0-9]{0,7})+)(?![\w/-])")


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


def files_mentioned_in(text: str) -> list[str]:
    """The file names `text` gives, in its order, with a line or without - but not where a line only warns.

    Measured live: a service failed at start-up in the module that opens its database, the one product file its
    output named was a deprecation warning's, and the rewrite fixed that.
    """
    return [name.lstrip("./") for _, name in sorted(
        (m.start(), m.group(1))
        for pattern in (_AN_ERROR_LOCATION, _A_FILE_NAMED)
        for m in pattern.finditer(text)
        if not _only_warns(text, m.start())
    )]


def files_to_fix(
    defect: Any, failure: str, repo_root: str | Path, may_write: Callable[[str], bool], *,
    aimed_at: Sequence[str] = (), refused: dict[str, str] | None = None,
) -> list[str]:
    """The workspace files a fix rewrites: the ones the defect names, then the ones its failure points at.

    `aimed_at`: the files a fixer that gave up wrote, tried to write or named (`surrender_evidence.aimed_at`), taken
    after the defect's own evidence and under the same rules. `refused`, when given, is told each file left out and the
    rule that left it out (LF.1402).
    """
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
    # the workspace's files under its root, or under the sandbox's mount.
    failure = _relative_to_the_workspace(failure, root)
    # The defect's own evidence first; the run's last failing command only when
    # that names no file. Measured live: a page check's "the interface is not
    # styled" was rewritten as its stylesheet and `tests/test_tasks.py` - named
    # by another fixer's unit-test run, the run's last failure - the test file
    # broke 17 tests, and the revert took the stylesheet with it.
    own, _, last = failure.partition(THE_LAST_FAILING_COMMAND)

    mentioned_in = files_mentioned_in
    # What the fixer aimed at, as the workspace spells it: a write's path, or a name its answer gave.
    aimed = [_relative_to_the_workspace(str(name), root).lstrip("./") for name in aimed_at if str(name).strip()]

    def files(mentioned: list[str]) -> list[str]:
        return _the_files(root, named, mentioned, judged_by_the_suite, tests_from_the_text, may_write, refused)

    # The defect's own words name files too, the words other checks merged into it not. Measured on one run: a failing
    # unit run named its test file only in the description, a cross-file finding merged into the defect brought the
    # manifest as its one affected file, and six fixes in a row rewrote the manifest and nothing else.
    from app.graph.engineering import SAME_PROBLEM_ELSEWHERE

    described = str(getattr(defect, "description", "") or "").partition(SAME_PROBLEM_ELSEWHERE)[0]
    own_words = mentioned_in(_relative_to_the_workspace(described, root))
    found = files(own_words + mentioned_in(own) + aimed)
    # Where nothing named or mentioned is the product's code, the code graph says where the failure is handled
    # (LF.1528): the handler of the route a failing test requests, the files its trace names, a page's renderer.
    # Measured on a Go notes service: its fixers used this path, the failure named only its test file, and the graph's
    # route-to-handler links (KG.4) never reached them - no localisation was recorded in the run.
    found = _with_where_the_graph_says_it_is_handled(root, defect, own, named, found, files,
                                                     own_words + mentioned_in(own) + aimed)
    if last and len(found) == len(files([])):
        found = files(own_words + mentioned_in(own) + aimed + mentioned_in(last))
    owing = [name for name in _modules_missing_an_export(own, root) if may_write(name)]
    if owing:
        # The module that should export it is the file to write; the test that imports it is left as it is.
        from app.analysis.file_kinds import classify_file

        found = [*owing, *(name for name in found if name not in owing and classify_file(name) != "test")][:MOST_FILES]
    kept = _without_other_ecosystems_manifests(root, found)
    if refused is not None:
        for name in found:
            if name not in kept:
                refused.setdefault(name, "a manifest of an ecosystem the project does not build its product with")
    return kept


def _with_where_the_graph_says_it_is_handled(
    root: Path, defect: Any, evidence: str, named: list[str], found: list[str],
    files: Callable[[list[str]], list[str]], mentioned: list[str],
) -> list[str]:
    """`found`, with the files the code graph localises the failure to when none of `found` is the product's code.

    Chosen under the same rules as every other file here (`files`), and recorded as a fixer's localisation. Never
    raises: `found` as it was.
    """
    try:
        from app.analysis.file_kinds import classify_file

        if any(classify_file(name) == "application" for name in found):
            return found
        from app.graph import localised_fix
        from app.observability.transcript import _stage_from_config

        located = localised_fix.where(root, evidence, named=named, defect=defect)
        localised_fix.noted(_stage_from_config("defect_fix"), located, defect)
        if not located.found:
            return found
        return files([*mentioned, *located.found])
    except Exception:  # noqa: BLE001 - the files as the defect and its failure name them
        logger.debug("Could not localise a rewrite's failure from the code graph", exc_info=True)
        return found


def _relative_to_the_workspace(text: str, root: Path) -> str:
    """`text` with the workspace's absolute paths made relative: under its root, or under the sandbox's mount.

    Measured over 45 runs (LF.1402): a command run in the sandbox prints `/workspace/<project>/...`, and every such
    path was read as `workspace/<project>/...`, which names no file - the failing test of each criterion the
    acceptance suite judges was "not in the workspace", and so was any product file a trace named that way.
    """
    from app.agents.workspace_paths import THE_SANDBOX_S_MOUNT

    text = text.replace(str(root).rstrip("/") + "/", "")
    return re.sub(rf"(?<![\w./@-]){re.escape(THE_SANDBOX_S_MOUNT)}/", "", text)


def _without_other_ecosystems_manifests(root: Path, files: list[str]) -> list[str]:
    """`files` less the manifests of an ecosystem the project's pack does not build its product with (A5)."""
    try:
        from app.analysis.manifests import not_the_product_s
        from app.stacks import contract

        found = contract.the_pack(root)
        pack = found[0] if found is not None else None
        return [name for name in files if not not_the_product_s(name, pack)]
    except Exception:  # noqa: BLE001 - the files as found
        return files



def _the_project_ignores(root: Path, relative: str) -> bool:
    """Whether the project's own ignore rules exclude the file: a report, a build, a cache - never its source.

    Measured live: two fixes in a row took `test-results/acceptance.xml`,
    named in the failure text, as the file to rewrite, rewrote the runner's
    report, and left both defects open. Asked of git, so every stack's own
    ignore file answers. False when there is no repository to ask.
    """
    import subprocess

    try:
        done = subprocess.run([*git_safely(), "-C", str(root), "check-ignore", "-q", "--", relative],
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


#: Suffixes of a product's data, which a rewrite for a suite-judged criterion never takes from failure text alone.
_DATA_A_FIX_LEAVES = (".txt", ".csv", ".jsonl", ".ndjson", ".db", ".sqlite", ".sqlite3", ".log")


def _a_manifest(relative: str) -> bool:
    """Whether the file declares the project's dependencies (`dependency_drift.MANIFESTS`): a fix may have to change it."""
    from app.analysis.dependency_drift import MANIFESTS

    name = Path(relative).name
    return name in {m for names in MANIFESTS.values() for m in names}


def _the_files(
    root: Path, named: list[str], mentioned: list[str], judged_by_the_suite: bool, tests_from_the_text: bool,
    may_write: Callable[[str], bool], refused: dict[str, str] | None = None,
) -> list[str]:
    """The workspace files to rewrite: those the defect names, then those its failure text mentions.

    `refused`, when given, is told each name left out and the rule that left it out.
    """
    from app.analysis.file_kinds import classify_file, is_scratch
    from app.tools.repository import IGNORED_DIRECTORIES

    def left_out(name: str, why: str) -> None:
        if refused is not None:
            refused.setdefault(name, why)

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
        if target is None:
            left_out(name, "no such file in the workspace")
            continue
        if any(part in IGNORED_DIRECTORIES for part in target.parts):
            left_out(name, "in a folder of built or installed files")
            continue
        relative = target.relative_to(root).as_posix()
        # A stage's throwaway probe is no part of the product. Measured live:
        # one fixer's `tmp-check-*.py` failed, its traceback reached two later
        # fixes as what failed, and each rewrote the probe and was recorded
        # as having fixed its defect.
        is_a_test = classify_file(relative) == "test"
        why = ("a stage's scratch file" if is_scratch(relative, root)
               else "a test, and the acceptance suite judges this criterion" if judged_by_the_suite and is_a_test
               else "the project's ignore rules leave it out" if _the_project_ignores(root, relative)
               else "a test runner's report" if _a_test_report(root, relative, target)
               else "")
        # Nor data or a document, for a criterion the suite judges, unless the defect names it (HR2.fix.3): a rewrite
        # was aimed at `input.txt`, the product's data, which no change fixes.
        if not why and judged_by_the_suite and name not in own and not _a_manifest(relative) and (
                classify_file(relative) == "document" or relative.lower().endswith(_DATA_A_FIX_LEAVES)):
            why = "data or a document the defect does not name"
        if not why and is_a_test and name not in own and not tests_from_the_text:
            why = "a test the defect does not name as its own"
        if why:
            left_out(relative, why)
            continue
        if relative in found:
            continue
        if may_write(relative):
            found.append(relative)
        else:
            left_out(relative, "this stage may not write it")
        if len(found) >= MOST_FILES:
            break
    return found


def fix_request(root: Path, path: str, defect: Any, failure: str, specification: Any,
                stack: Any, others: list[str], diagnostics: list[str], co_failures: str = "", kept: str = "",
                model: Any = None) -> str:
    """What one file's rewrite is asked. `co_failures`: the other open defects that point at this file (`co_defect_failures`).

    Past its input budget (`request_budget.opening_target` for `model`'s window, LF.1274) it opens with the defect's
    evidence and the file to correct, keeps what binds the fix whole, and cuts its standing context to what the
    defect touches: the API to the routes its failing tests call, the facts to its files, the project to the files the
    failure names and what they import (`_fitted`). Within it, the request is as it was built.
    """
    from app.agents.shared_facts import the_facts_section
    from app.agents.specialists import specification_for_the_work_order
    from app.graph.drafting import _neighbours, _stack_line, _the_registry_s_releases, the_reference_code
    from types import SimpleNamespace

    from app.graph import anchored_edits

    detail = specification_for_the_work_order(
        specification, SimpleNamespace(files=[path], interfaces=[]), root) if specification else ""
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
        neighbours, held = project_memory.render(root, MEMORY_CHARACTERS, focus=f"{path}\n{failure}", for_a_fixer=True)
    else:
        neighbours, held = _neighbours(root, path, SimpleNamespace(files=others), detail), {}
    # What happened to the attempts before this one: a rewrite asked again
    # exactly as before wrote the same change, and was reverted for the same
    # broken test - measured on the first all-on run, two identical requests
    # and two identical reverts in one sprint attempt.
    from app.agents.ledger import earlier_attempts

    actual = str(getattr(defect, "actual_behavior", "") or "").strip()
    defect_part = (f"--- The defect ---\n{getattr(defect, 'description', '')}\n"
                   f"Expected: {getattr(defect, 'expected_behavior', '')}" + (f"\nActual: {actual}" if actual else ""))
    from app.agents.ledger import enabled as _ledger_on
    from app.agents.request_budget import EVIDENCE, KEPT
    from app.graph import what_a_revert_broke
    from app.graph.cause_journal import tried_before
    from app.stacks import api_cards

    # Each with what it is to the input budget: what the defect is, or what binds the fix.
    changing_parts = (
        (KEPT, earlier_attempts(defect).strip()),
        # What the changes reverted before this one broke: each test with its runner's words, and the change (LF.1547).
        (EVIDENCE, what_a_revert_broke.told(root, defect).strip()),
        # What was tried on its cause in earlier cycles too (deep review 1.4).
        (KEPT, tried_before(root, defect, shown=(getattr(defect, "attempts", None) or []) if _ledger_on() else ()).strip()),
        (EVIDENCE, f"--- What failed ---\n{failure}" if failure.strip() else ""),
        (EVIDENCE, co_failures),
        # The fixes made before this one, which a rewrite must not undo (`specialists.fixes_to_keep_section`).
        # Measured on one run: every fix of a page's list-structure check came through this rewrite, which was never
        # told of the fix it kept undoing for another test.
        (KEPT, kept.strip()),
        (EVIDENCE, ("--- The compiler still reports, in the files just written ---\n" + "\n".join(diagnostics))
         if diagnostics else ""),
        (EVIDENCE, ("--- Edits from the last pass that were not made, and why ---\n" + "\n".join(unapplied))
         if unapplied else ""),
        # The registry's current releases, for a rewrite of a dependency manifest (plan WL.4 T4).
        (KEPT, _the_registry_s_releases(root, path, specification, stack)),
        # The installed API of libraries newer than the model, when this file uses one (plan HK.7).
        (KEPT, api_cards.for_a_fixer(root, [path], failure, model).strip()),
    )
    changing = tuple(text for _, text in changing_parts)
    project = f"--- The project ---\n{neighbours}" if neighbours else ""
    the_file = ((anchored_edits.in_the_memory(path) if held.get(path) == now
                 else anchored_edits.excerpt(path, now, failure, _the_defect_s_words(defect))) if long_file
                else f"--- `{path}` as it is now ---\n{now}")
    # The facts every builder and judge reads (plan CM.1), and the pack's golden example for a file in its languages
    # (deep review 2026-11-18, item E4).
    the_facts, reference = the_facts_section(root).strip(), the_reference_code(root, path)
    facts = "\n\n".join(part for part in (the_facts, reference) if part)
    instruction = (anchored_edits.instruction(path) if long_file else
                   f"Reply with the complete corrected content of `{path}` and nothing else, in one fenced "
                   "code block. Change only what the failure needs; keep every name, signature and "
                   "message the specification gives. If this file needs no change for this failure, "
                   "reply with it unchanged.")
    from app.agents import stable_memory_order

    if stable_memory_order.enabled():
        # What every rewrite of the sprint shares first, then what this file and this failure change (LR.52).
        built = "\n\n".join(part for part in (
            "Correct one file of this product so the failure given below no longer happens. "
            f"The stack: {_stack_line(stack)}.",
            facts, project, detail.strip(),
            f"--- The file to correct: `{path}` ---", defect_part, *changing, the_file, instruction,
        ) if part)
    else:
        built = "\n\n".join(part for part in (
            f"Correct the file `{path}` of this product so the failure below no longer happens. "
            f"The stack: {_stack_line(stack)}.",
            defect_part, *changing, detail.strip(), project, the_file, facts, instruction,
        ) if part)
    return _within_its_budget(
        built, model=model, root=root, path=path, others=others, defect=defect, failure=failure,
        specification=specification, opening=f"Correct the file `{path}` of this product so the failure below no "
                                             f"longer happens. The stack: {_stack_line(stack)}.",
        defect_part=defect_part, changing=changing_parts, detail=detail, now=now, long_file=long_file,
        the_facts=the_facts, reference=reference, instruction=instruction,
        project=project, has_memory=bool(neighbours) and project_memory.enabled())


def _within_its_budget(built: str, *, model: Any, root: Path, path: str, others: list[str], defect: Any, failure: str,
                       specification: Any, opening: str, defect_part: str, changing: Sequence[tuple[str, str]],
                       detail: str, now: str, long_file: bool, the_facts: str, reference: str, instruction: str,
                       project: str, has_memory: bool) -> str:
    """`built` when it is within its input budget; past it, the same request fitted to it (`request_budget.fit`).
    Never raises: `built` as it is.

    Measured on small runs: one file's rewrite was asked in 84,000-99,000 characters, about 39,000 of them the
    project's other files, beside the whole API and every fact of the workspace.
    """
    try:
        from app.agents import project_memory, request_budget
        from app.agents.request_budget import EVIDENCE, INSTRUCTION, KEPT, STANDING, Part
        from app.graph import anchored_edits
        from app.graph import fixer_request_shape as shape
        from app.observability.transcript import _stage_from_config

        stage = str(_stage_from_config("defect_fix") or "defect_fix")
        target = request_budget.opening_target(model)
        if len(built) <= target:
            request_budget.noted(stage, built=len(built), target=target)
            return built
        evidence = "\n".join((defect_part, *(text for kind, text in changing if kind == EVIDENCE and text)))
        touched = shape.the_files_it_touches(root, evidence, [path, *others, *(getattr(defect, "affected_files", None)
                                                                              or [])])
        parts = [
            Part(INSTRUCTION, opening),
            Part(EVIDENCE, defect_part + "\n\n"),
            *(Part(EVIDENCE, text.strip("\n") + "\n\n") for kind, text in changing if kind == EVIDENCE and text),
            # The file to correct is what a rewrite answers with; a long one as the parts its failure points at.
            Part(EVIDENCE, anchored_edits.excerpt(path, now, failure, _the_defect_s_words(defect)) if long_file
                 else f"--- `{path}` as it is now ---\n{now}\n"),
            *(Part(KEPT, text) for kind, text in changing if kind == KEPT and text),
        ]
        if detail.strip():
            parts.append(Part(STANDING, detail, where="/docs/technical_specification.md",
                              cut=shape.specification_cut(specification, detail, [
                                  failure, str(getattr(defect, "actual_behavior", "") or ""),
                                  str(getattr(defect, "reproduction_steps", "") or "")])))
        # The rulings and the fixes undone for a start that broke bind every stage: kept whole; the facts are cut.
        if the_facts:
            parts.extend(shape.split_facts("\n" + the_facts + "\n", touched))
        if reference:
            parts.append(Part(STANDING, reference))
        if project and not has_memory:
            parts.append(Part(STANDING, project))  # the neighbouring files, without the project memory
        parts.append(Part(INSTRUCTION, instruction))

        def the_project(room: int) -> str:
            # The files the failure names and what they import, whole; the rest named, within the room left.
            memory, _ = project_memory.render(root, min(MEMORY_CHARACTERS, room), focus=f"{path}\n{evidence}",
                                              for_a_fixer=True, sliced=True)
            return f"--- The project ---\n{memory}" if memory else ""

        least = int(target * request_budget.MEMORY_LEAST_SHARE) if has_memory else 0
        fitted = request_budget.fit(parts, target=target, memory=least,
                                    memory_text=the_project if has_memory else None)
        request_budget.noted(stage, built=len(built), target=target, fitted=fitted)
        logger.info("Rewrite request for %s is past its input budget (%d characters, target %d); evidence first, "
                    "standing context cut to %d characters", path, len(built), target, fitted.sent)
        return fitted.text
    except Exception:  # noqa: BLE001 - the request as built
        logger.debug("Could not fit a rewrite request to its budget", exc_info=True)
        return built


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

    from app.models.reply_text import reply_text

    text = reply_text(reply)
    if anchored_edits.too_long_to_rewrite(original):
        return anchored_edits.applied(path, original, text)
    return the_content_in(text)


def _the_last_rewrite_changed_nothing(defect: Any, files: Sequence[str], records: Sequence[dict] | None = None) -> bool:
    """Whether this defect's last rewrite was shown exactly `files` and sent every one back unchanged. Never raises.

    Read from the ledger's `rewrite reply` records (HR2.fix.1): the last rewrite is the replies after this defect's
    last `shown` record that a rewrite made.
    """
    try:
        from app.observability.defect_ledger import defect_id

        if records is None:
            from app.observability.transcript import _run_id_from_config, read_live

            run = _run_id_from_config()
            if not run:
                return False
            records = read_live(run, {"defect"})
        mine = [r for r in records if r.get("defect_id") == defect_id(defect)
                and r.get("event") in ("shown", "rewrite reply")]
        replies: list[str] = []
        for record in reversed(mine):
            # The latest attempt only: an agent loop's `shown` after the rewrite means the loop came last.
            if record.get("event") == "shown":
                break
            replies.append(str(record.get("detail") or ""))
        if not replies:
            return False
        unchanged = {reply.split(": ", 1)[1] for reply in replies if reply.startswith("unchanged: ")}
        return len(unchanged) == len(replies) and unchanged == set(files)
    except Exception:  # noqa: BLE001 - then the rewrite is tried as before
        return False


def _note_the_reply(defect: Any, path: str, kind: str) -> None:
    """The ledger's record of what a one-file rewrite replied for `path`: changed, unchanged, no block, edit not
    applied (HR2.fix.1). Measured by reading message text over 123 runs: 42% of rewrite replies sent the file back
    unchanged, and the path a defect took had to be rebuilt by hand. Never raises."""
    try:
        from app.observability import defect_ledger
        from app.observability.transcript import _stage_from_config

        defect_ledger.note("rewrite reply", str(_stage_from_config("defect_fix") or "defect_fix"), defect=defect,
                           detail=f"{kind}: {path}")
    except Exception:  # noqa: BLE001 - a ledger must never fail the fix it records
        pass


def _note_what_the_rewrite_was_shown(defect: Any, asked: Any) -> None:
    """The ledger's `shown` record for a one-file rewrite, as every agent fixer has one. Never raises.

    Measured on a live run: two rewrites ran and were measured with no `shown` record, so the ledger read as if no
    fixer had run at all (harness review F8)."""
    try:
        from app.observability import defect_ledger
        from app.observability.transcript import _stage_from_config

        defect_ledger.shown(str(_stage_from_config("defect_fix") or "defect_fix"), defect, asked)
    except Exception:  # noqa: BLE001 - a ledger must never fail the fix it records
        pass


def fix_by_rewriting(
    defect: Any, repo_root: str | Path, model: Any, *, specification: Any = None, stack: Any = None,
    last_failure: Any = None, may_write: Callable[[str], bool] | None = None,
    write: Callable[[str, str, str], Any] | None = None,
    diagnose: Callable[[list[str]], list[str]] | None = None,
    files: list[str] | None = None, co_defects: Sequence[Any] = (), kept: str = "",
    why: dict[str, str] | None = None,
) -> Any | None:
    """The fix stage's output for a defect fixed by rewriting its files, or None for the agent loop.

    `co_defects`: the other open defects, whose failures that point at a file go into its rewrite (`co_defect_failures`).
    `why`, when given, is told under "why" what each file's rewrite came to when it returns None (LF.1403).

    `files`, when given, is used as the files to rewrite and no localisation
    call is made: a retry that already asked `fix_by_candidates` where the
    defect lives need not ask again. See `app.graph.nodes.fixes._fixed_by_rewriting`.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.agents.specialists import SpecialistOutput
    from app.graph.anchored_edits import AN_EDIT_NOT_APPLIED
    from app.tools.repository import RepositoryToolError

    root = Path(repo_root)
    # What each file's rewrite came to, said when nothing is written (LF.1403).
    came_to: dict[str, str] = {}

    def nothing(reason: str = "") -> None:
        if why is not None:
            why["why"] = reason or ("the rewrite wrote nothing: " + "; ".join(
                f"`{path}` {outcome}" for path, outcome in came_to.items()) if came_to else "the rewrite wrote nothing")
        return None

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
        return nothing("the rewrite found no file it may write")
    if _the_last_rewrite_changed_nothing(defect, files):
        # Not the same rewrite again (HR2.fix.4): rewrite after rewrite fixed 16%, a rewrite then the agent loop 33%.
        logger.info("The last whole-file rewrite of %s judged no change needed; this attempt goes to the agent loop",
                    ", ".join(files))
        try:
            from app.observability import defect_ledger
            from app.observability.transcript import _stage_from_config

            defect_ledger.note("rewrite skipped", str(_stage_from_config("defect_fix") or "defect_fix"), defect=defect,
                               detail="the last rewrite sent every file back unchanged: " + ", ".join(files))
        except Exception:  # noqa: BLE001 - a ledger must never fail the fix it records
            pass
        return nothing("the last rewrite sent every file back unchanged, so it is not asked again: " + ", ".join(files))
    from app.graph import co_defect_failures, repeated_rewrite_prompts

    co_failures = co_defect_failures.failures_by_file(co_defects, root, may_write or (lambda _: True))
    changed: list[str] = []
    diagnostics: list[str] = []
    from app.graph.fewest_findings import BestVersions

    best = BestVersions()
    # A file whose reply came back unchanged is not asked for again in this attempt (A5): measured, 194 of 462 replies
    # returned the file as it was, and every pass asked for every file the failure named.
    unchanged: set[str] = set()
    for _pass in range(MOST_PASSES):
        targets = files if not diagnostics else [f for f in files if any(f"`{f}`" in d for d in diagnostics)] or files
        targets = [path for path in targets if path not in unchanged]
        if not targets:
            break
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
                        return nothing("no chat model to rewrite with")
                    break
                current = (root / path).read_text(encoding="utf-8", errors="replace")
                asked = fix_request(root, path, defect, failure, specification, stack,
                                    [f for f in files if f != path], diagnostics, co_failures.get(path, ""), kept=kept,
                                    model=active_model)
                if repeated_rewrite_prompts.exhausted(root, asked):
                    logger.info("Rewrite of %s not sent: the same request has failed %d times", path,
                                repeated_rewrite_prompts.MOST_IDENTICAL)
                    came_to[path] = f"not asked: the same request failed {repeated_rewrite_prompts.MOST_IDENTICAL} times"
                    if not changed:
                        return nothing()
                    continue
                # Counted as failed when sent: a rewrite that holds closes its defect and is not asked again.
                repeated_rewrite_prompts.failed(root, asked)
                _note_what_the_rewrite_was_shown(defect, asked)
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
                    _note_the_reply(defect, path, "edit not applied")
                    came_to[path] = "came back as an edit that matched nowhere or more than once"
                    continue
                if not content.strip():
                    _note_the_reply(defect, path, "no block")
                    came_to[path] = "came back with no file in the reply"
                    continue
                if content != current and repeated_rewrite_prompts.reply_failed_before(root, {path: content}):
                    # The same file an earlier rewrite wrote and the harness measured failing (35 of 215 replies
                    # were byte-identical to an earlier one): not written and measured again.
                    _note_the_reply(defect, path, "repeated")
                    came_to[path] = "came back as the same file an earlier rewrite wrote, measured failing"
                    unchanged.add(path)
                    continue
                _note_the_reply(defect, path, "changed" if content != current else "unchanged")
                if content == current:
                    unchanged.add(path)
                    came_to[path] = "came back unchanged"
                if content != current:
                    try:
                        write(str(root), path, content)
                    except Exception as refused:  # noqa: BLE001 - the next pass is told what was refused
                        if "language service is sure of" not in str(refused):
                            raise
                        diagnostics = [*diagnostics, f"- In `{path}`: {refused}"]
                        came_to[path] = "was refused: it would add errors the language service is sure of"
                        continue
                    if path not in changed:
                        changed.append(path)
                    # Counted as failed when written, as its request is: a rewrite that holds closes its defect.
                    repeated_rewrite_prompts.reply_failed(root, {path: content})
                    # Made now: what an earlier pass was told of its edits is past.
                    diagnostics = [d for d in diagnostics if not (AN_EDIT_NOT_APPLIED in d and f"`{path}`" in d)]
            except Exception as error:  # noqa: BLE001 - the agent loop takes what this could not
                from app.models.call_gate import raise_if_the_run_stopped

                raise_if_the_run_stopped(error)  # a paused run fixes again on resume, not by the loop
                logger.info("Rewrite of %s for a fix failed: %s", path, str(error)[:200])
                came_to[path] = f"failed: {type(error).__name__}: {str(error)[:120]}"
                if not changed:
                    return nothing()
        refused = [line for line in diagnostics if "language service is sure of" in line or AN_EDIT_NOT_APPLIED in line]
        diagnostics = [*refused, *(diagnose(changed) if diagnose and changed else [])]
        best.offer_as_they_are(root, changed, diagnostics)
        if not diagnostics:
            break
    if not changed:
        return nothing()
    # The pass the compiler found fewest errors in is kept, not the last (A2): measured, a third pass broke what the
    # second had made compile and was kept with "The compiler still reports ...".
    if best.put_back(root, write):
        refused = [line for line in diagnostics if "language service is sure of" in line or AN_EDIT_NOT_APPLIED in line]
        diagnostics = [*refused, *(diagnose(changed) if diagnose else [])]
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
    candidates: int = CANDIDATES, files: list[str] | None = None, co_defects: Sequence[Any] = (), kept: str = "",
    holds: Callable[[list[str]], bool] | None = None, seed_base: int | None = None,
) -> Any | None:
    """A defect fixed by several candidate rewrites asked for at once, the first its tests pass kept; or None.

    `holds`, for a stuck defect (`candidate_fixes_when_stuck`, PF.2): a candidate whose own tests pass is kept only
    when it is also given its changed files and answers True - the regression set still passes - else the files are
    put back and the next is tried. `seed_base`: each candidate asked with its own seed (`seed_base` + its number),
    where the server takes one (`candidate_fixes_when_stuck.seed_for`).

    `files`, when given, is used as the files to change and no localisation
    call is made. See `app.graph.nodes.fixes._fixed_by_rewriting`.

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
                                [f for f in files if f != path], [], co_failures.get(path, ""), kept=kept,
                                model=active_model)
            if repeated_rewrite_prompts.exhausted(root, asked):
                return index, path, ""
            sent.append(asked)
            seeded: dict[str, Any] = {}
            if seed_base is not None:
                from app.graph.candidate_fixes_when_stuck import seed_for

                seeded = seed_for(active_model, seed_base + index)
            reply = active_model.invoke([
                SystemMessage(content=_system_for(originals[path])),
                HumanMessage(content=asked),
            ], **seeded, **config_for_this_run("defect_fix"))
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
        if repeated_rewrite_prompts.reply_failed_before(root, {path: version[path] for path in changed}):
            # The same files an earlier rewrite or candidate wrote and the defect's tests failed: not measured again.
            logger.info("Candidate %d skipped: it writes what an earlier rewrite wrote, measured failing", number)
            continue
        try:
            for path in changed:
                write(str(root), path, version[path])
        except Exception as error:  # noqa: BLE001 - this candidate is refused; the next is tried
            logger.info("Candidate %d refused: %s", number, str(error)[:200])
            put_back()
            continue
        passed = check()
        if passed is False:
            repeated_rewrite_prompts.reply_failed(root, {path: version[path] for path in changed})
        if passed is not False and holds is not None and not holds(changed):
            # Its own tests pass and it broke what passed before: the next candidate is tried (PF.2).
            logger.info("Candidate %d of %d passes its own tests and breaks others; not kept", number, candidates)
            put_back()
            continue
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
