"""Which side a failing unit test's cause is on, read from the failure (PA.15, behind `UNIT_TEST_FIX_BY_FAILURE`).

`TESTS_ONLY_WRITES` holds the first fix of a failing unit test beside a green acceptance suite to test files: the
suite already passes, so the unit test is the first thing to look at. Measured over the ledger (per-agent audit,
2026-11-25): 44 defects were first worked tests-only, 1 was fixed by that attempt, 2 were closed by the next round and
9 were left open or unverified; 29 later records allowed product code. Many of those first attempts were lost stages
for failures whose cause the failure itself put in the product: an import that fails inside a product module, a
product file that does not compile, an exception raised from a product file before any assertion was reached.

So the failure decides the side before the first attempt:

- **the product's** when no assertion was reached, no stand-in is named, and the failure locates the error in an
  application file of the project (a trace frame, a compiler diagnostic, `File "...", line n`): product code is
  allowed at once;
- **the test's** otherwise - an assertion that fails (the test's own check, a count other tests' records changed, an
  out-of-date expectation), a stand-in's expectation, or an error located only in test files: the attempt stays
  tests-only, as the owner's rule says.

What an assertion looks like differs by runner, so its patterns are the language table's (`assertion_failed`). Nothing
here names a language, a framework or a runner. Never raises.
"""

from __future__ import annotations

import os
import re
import threading
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any

from app.stacks.languages import LANGUAGES, NOT_THE_PRODUCT, Gap
from app.switches import is_on

NAME = "UNIT_TEST_FIX_BY_FAILURE"
#: `UNIT_TEST_FIX_BY_FAILURE` set to on or off overrides this; off in code until measured.
ON_BY_DEFAULT = False
#: What the admin page says this switch does.
explanation = ("The first fix of a failing unit test beside a green suite chooses its side from the failure: an error "
               "raised in a product file before any assertion allows product code at once; an assertion that fails "
               "stays tests-only.")

#: How the fixer's section opens; the switch's firing signal (`switch_firing.SIGNALS`).
HEADING = "--- The failure is raised in the product's code ---"
#: The ledger's words for the mode the switch chose.
MODE = "product code allowed at once: the failure is raised in the product's code before any assertion"
#: Characters of a defect's text read.
MOST_TEXT = 20_000
#: Product files named in the section.
MOST_NAMED = 3
#: Workspace files listed when a trace names a file by its name alone.
MOST_FILES = 5_000

#: The sandbox's mount: a path under it is the workspace's.
_MOUNT = "/workspace/"
#: A stand-in named in the failure itself: `'_MockRequest' object has no attribute`, `MagicMock`, `FakeStore`.
_A_STAND_IN = re.compile(r"\b\w*(?:Mock|Stub|Fake|Spy)(?:[A-Z_]\w*)?\b|\b(?:mock|stub|fake|spy)(?:ed|s)?\b")


@lru_cache(maxsize=1)
def _assertions() -> tuple[re.Pattern[str], ...]:
    found: dict[str, re.Pattern[str]] = {}
    for row in LANGUAGES:
        if isinstance(row.assertion_failed, Gap):
            continue
        for pattern in row.assertion_failed:
            found.setdefault(pattern, re.compile(pattern))
    return tuple(found.values())


@lru_cache(maxsize=1)
def _locations() -> tuple[re.Pattern[str], ...]:
    """A file and a line, as a trace frame or a diagnostic writes it, for every language's source suffixes."""
    suffixes = sorted({suffix.lstrip(".") for row in LANGUAGES for suffix in row.suffixes}, key=len, reverse=True)
    ext = "|".join(re.escape(s) for s in suffixes)
    path = rf"(?P<path>(?:[A-Za-z]:)?[\w.@+\-/\\]*?[\w@+\-]+\.(?:{ext}))"
    return (
        # `File "notes_api/database.py", line 16` and pytest's `file /x/tests/conftest.py, line 9`.
        re.compile(rf"\b[Ff]ile \"?{path}\"?, line \d+"),
        # `notes_api/database.py:16:`, `src/main.rs:12:5`, `(NoteStorage.java:42)`, `X.java:[12,5]`, `app.ts(12,5)`.
        re.compile(rf"(?<![\w.@+\-/\\]){path}(?::\[?|\()\d+"),
    )


def assertion_reached(text: str) -> bool:
    """Whether a failure's text says an assertion was reached and failed, in any runner's wording."""
    shown = str(text or "")[:MOST_TEXT]
    return any(pattern.search(shown) for pattern in _assertions())


def _workspace_relative(path: str, root: str | Path | None) -> str:
    """`path` relative to the workspace, or "" when it lies outside it (a runtime's or a system's file)."""
    shown = str(path or "").replace("\\", "/")
    if shown.startswith(_MOUNT):
        return shown[len(_MOUNT):]
    if root is not None:
        here = str(Path(root)).replace("\\", "/").rstrip("/") + "/"
        if shown.startswith(here):
            return shown[len(here):]
    if shown.startswith("/") or re.match(r"^[A-Za-z]:/", shown):
        return ""
    return shown.lstrip("./")


def _not_installed(parts: tuple[str, ...]) -> bool:
    return not any(part in NOT_THE_PRODUCT or part.startswith(".") for part in parts[:-1])


def _source_files(root: Path) -> list[str]:
    """The workspace's own source files, workspace-relative; installed and tool folders left out."""
    found: list[str] = []
    for folder, folders, files in os.walk(root):
        folders[:] = sorted(f for f in folders if f not in NOT_THE_PRODUCT and not f.startswith("."))
        found.extend((Path(folder) / name).relative_to(root).as_posix() for name in sorted(files))
        if len(found) >= MOST_FILES:
            break
    return found


def _in_the_workspace(relative: str, root: str | Path | None, files: list[str] | None) -> str:
    """The workspace file `relative` names: itself, or the one file whose path ends with it (a trace writes a path
    from the project's folder, or a frame only the file's name); "" when none or several do. Without a `root`, the
    name as written."""
    if root is None:
        return relative
    if (Path(root) / relative).is_file():
        return relative
    ending = [f for f in files or () if f == relative or f.endswith("/" + relative)]
    return ending[0] if len(ending) == 1 else ""


def _is_the_product_s(relative: str) -> bool:
    from app.analysis.file_kinds import classify_file, is_scratch

    if not relative or ".." in PurePosixPath(relative).parts or not _not_installed(PurePosixPath(relative).parts):
        return False
    return classify_file(relative) == "application" and not is_scratch(relative)


def product_files_located(text: str, root: str | Path | None = None) -> list[str]:
    """The project's application files a failure's trace or diagnostics locate its error in, in order, once each.

    Given the workspace's `root`, only files that are in it: a frame of an installed library names its file alone
    (`(PoolBase.java:121)`), and a runtime's own files lie outside the workspace."""
    shown = str(text or "")[:MOST_TEXT]
    files = _source_files(Path(root)) if root is not None and Path(root).is_dir() else None
    found: dict[str, None] = {}
    for pattern in _locations():
        for match in pattern.finditer(shown):
            relative = _workspace_relative(match.group("path"), root)
            if not _is_the_product_s(relative):
                continue
            here = _in_the_workspace(relative, root, files)
            if here and _is_the_product_s(here):
                found.setdefault(here, None)
    return list(found)


def _a_failing_test_replaces_a_component(text: str, root: str | Path | None) -> bool:
    """Whether a failing test's file, as the failure names it, puts a stand-in in place of a component."""
    if root is None:
        return False
    try:
        from app.analysis import stand_in_tests

        workspace = Path(root)
        failing = stand_in_tests.failing_tests(text)
        if not failing:
            return False
        files = stand_in_tests.test_files(workspace)
        for test in failing[:20]:
            found = stand_in_tests.the_file_of(workspace, test, files)
            if found is not None and stand_in_tests.stand_ins_in(str(found[0]), found[1]):
                return True
    except Exception:  # noqa: BLE001 - a check that cannot read the tests says nothing of them
        return False
    return False


def the_product_s(text: str, root: str | Path | None = None) -> list[str]:
    """The product files a failing unit test's error is raised in, when its cause is the product's; [] otherwise.

    The product's when no assertion was reached, no stand-in is named in the failure or in a failing test's file, and
    the error is located in an application file of the project. Never raises."""
    try:
        shown = str(text or "")[:MOST_TEXT]
        if not shown.strip() or assertion_reached(shown) or _A_STAND_IN.search(shown):
            return []
        located = product_files_located(shown, root)
        if not located or _a_failing_test_replaces_a_component(shown, root):
            return []
        return located
    except Exception:  # noqa: BLE001 - a failure that cannot be read stays with the owner's rule
        return []


def enabled() -> bool:
    return is_on(NAME, ON_BY_DEFAULT)


_lock = threading.Lock()
_sent: dict[tuple[str, str], list[str]] = {}


def send_to_the_product(run_id: str | None, stage: str, files: list[str]) -> None:
    """From now on `stage` of `run_id` is told its failure is raised in `files`, the product's code."""
    with _lock:
        _sent[(str(run_id or ""), stage)] = list(files)


def release(run_id: str | None, stage: str) -> None:
    with _lock:
        _sent.pop((str(run_id or ""), stage), None)


def briefing(run_id: str | None, stage: str) -> str:
    """The fixer's section for a stage sent to the product by its failure; "" for any other."""
    with _lock:
        files = list(_sent.get((str(run_id or ""), stage)) or ())
    return section(files)


def section(files: list[str]) -> str:
    """The fixer's section when the failure puts the cause in the product; "" when it names no file."""
    if not files:
        return ""
    named = ", ".join(f"`{f}`" for f in files[:MOST_NAMED])
    return (
        f"\n{HEADING}\n"
        f"No assertion was reached: the error is raised in the product's own code ({named}) before any test could "
        "check a result. So this attempt may change the product: start where the error is raised, put the product "
        "right, and run the failing unit tests again. Correct a test only where it calls the product in a way the "
        "specification does not allow, and say in your answer which you changed.\n"
    )


def effects_lines(records: Any) -> list[str]:
    """`loop.sh effects` (PA.15): first attempts at a failing unit test sent to the product by their failure, and what
    became of those defects."""
    rows = [r for r in records or () if isinstance(r, dict)]
    chosen = {str(r.get("defect_id") or "") for r in rows
              if r.get("kind") == "defect" and r.get("event") == "mode" and MODE in str(r.get("detail") or "")}
    head = "PA.15 first unit-test fixes sent to the product by their failure"
    if not chosen:
        return [f"     -  {head}: not reached"]
    fixed = {str(r.get("defect_id") or "") for r in rows
             if r.get("kind") == "defect" and r.get("event") == "fixed"} & chosen
    reverted = {str(r.get("defect_id") or "") for r in rows
                if r.get("kind") == "defect" and r.get("event") == "reverted"} & chosen
    return [f"  {len(chosen):>4}  {head} ({len(fixed)} fixed, {len(reverted)} reverted)"]


__all__ = ["HEADING", "MODE", "NAME", "ON_BY_DEFAULT", "assertion_reached", "briefing", "effects_lines", "enabled",
           "explanation", "product_files_located", "release", "section", "send_to_the_product", "the_product_s"]
