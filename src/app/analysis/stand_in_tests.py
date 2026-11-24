"""A failing unit test that expects a refusal its own stand-in hides, while the product keeps the rule (LF.1312).

Measured over 60 scored runs: 12 shipped their own unit tests failing or set aside while every hidden test passed. On
the run that cost a "deliverable" verdict, a controller slice test replaced the service with a stand-in and asserted
that an empty title is refused with 400; the rule lives in the service, which the stand-in replaces, so the controller
answered 201 and the test could never pass. The product refused the empty title - the locked acceptance tests and the
hidden tests passed - and the fix rounds in tests-only mode did not repair the test.

So a fixer of failing unit tests is told, when the evidence is there: a failing unit test expected a refusal (a 4xx
status, an error) and got a success; its file puts a stand-in in place of a component; and a locked acceptance test
that refuses the same input passed. Then the rule is kept by the product and hidden by the stand-in, and the test is
to check it where it lives. Without all three, nothing is said: a unit test failing for a real product fault is the
fixer's to work as before.

Stand-in declarations and runner messages differ by language; their patterns are the language table's
(`app.stacks.languages`, `stand_ins` and `refusal_not_given`).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from app.stacks.languages import LANGUAGES, NOT_THE_PRODUCT, Gap, LanguageSupport

#: How the fixer's section begins: the effects report counts it (`loop.sh effects`).
HEADING = "--- A stand-in hides the rule this unit test expects ---"

#: Characters of a failing test's message read for a refusal that did not come.
MOST_MESSAGE = 2_000
#: Test files read when looking for the one a failing test is in.
MOST_FILES = 400
#: Characters of one test file read.
MOST_FILE_CHARACTERS = 200_000
#: Failing tests and stand-ins named in the section.
MOST_NAMED = 3

#: Words that say a test is about refusing an input.
_REFUSING = frozenset({
    "invalid", "empty", "blank", "missing", "reject", "rejects", "rejected", "rejecting", "refuse", "refuses", "refused",
    "refusing", "bad", "validation", "validate", "validates", "required", "malformed", "unprocessable", "error",
    "errors", "throws", "throw", "raises", "raise", "negative", "too", "long", "short", "wrong", "without", "null",
    "none", "duplicate", "conflict", "forbidden", "unauthorized", "not", "no", "fails", "fail",
})
#: Words in a test's name that say nothing of what is refused.
_PLAIN = frozenset({
    "test", "tests", "should", "returns", "return", "returned", "when", "with", "the", "and", "of", "is", "it", "given",
    "then", "a", "an", "be", "on", "for", "to", "in", "that", "if", "are", "its", "create", "creates", "creating",
    "update", "updates", "updating", "post", "put", "patch", "get", "delete", "request", "response", "status", "code",
    "api", "controller", "service", "spec", "can", "ac", "cr", "endpoint", "route", "handler", "unit", "case", "at",
    "by", "as", "or", "from", "into", "answers", "responds", "gives",
})
#: A status the client is refused with, written in a test's name ("returns400").
_A_REFUSAL_STATUS = re.compile(r"^4\d\d$")
_WORDS = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")
#: A failing test as `ci.what_the_failing_unit_tests_say` lists it: "- [within › ]name (file): message".
#: Its message runs to the next listed test, as a short message is shown whole, blank lines and all.
_LISTED = re.compile(r"^- (?:(?P<within>[^\n]*?) › )?(?P<name>[^\n(]+?)(?: \((?P<file>[^)\n]+)\))?: "
                     r"(?P<message>.*?)(?=^- |^\.\.\. and |^Distinct causes|\Z)", re.M | re.S)
#: Characters of a listed test's message read: the listing shows at most about this much of one.
MOST_LISTED_MESSAGE = 700


@dataclass(frozen=True)
class Failing:
    """One failing unit test: its name, where the report says it lives, and what it said."""

    name: str
    where: str
    message: str


def _patterns(field: str, rows: Iterable[LanguageSupport] = LANGUAGES) -> list[re.Pattern[str]]:
    found: dict[str, re.Pattern[str]] = {}
    for row in rows:
        value = getattr(row, field)
        if isinstance(value, Gap):
            continue
        for pattern in value:
            found.setdefault(pattern, re.compile(pattern))
    return list(found.values())


def expects_a_refusal_it_did_not_get(message: str) -> bool:
    """Whether a failure's message says a refusal was expected (a 4xx, an error) and a success came instead."""
    text = str(message or "")[:MOST_MESSAGE]
    return any(pattern.search(text) for pattern in _patterns("refusal_not_given"))


def _row_for(path: str) -> LanguageSupport | None:
    suffix = Path(path).suffix.lower()
    return next((row for row in LANGUAGES if suffix in row.suffixes), None)


def stand_ins_in(path: str, text: str) -> list[str]:
    """What a test file puts stand-ins in place of, in its language's own spelling; [] when none or unknown."""
    row = _row_for(path)
    if row is None or isinstance(row.stand_ins, Gap):
        return []
    found: dict[str, None] = {}
    for pattern in _patterns("stand_ins", (row,)):
        for match in pattern.finditer(text):
            groups = {key: value for key, value in match.groupdict().items() if value}
            replaced = groups.pop("name", "") or next((v for k, v in groups.items() if k != "attr"), "")
            if not replaced:
                continue
            attr = groups.get("attr", "")
            found.setdefault(f"{replaced}.{attr}" if attr else replaced, None)
    return list(found)


def _words(text: str) -> set[str]:
    """The words of a test's name or a criterion, lower case, a plural's trailing s taken off."""
    words = {word.lower() for word in _WORDS.findall(str(text or ""))}
    return {word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word for word in words}


def _says_it_refuses(text: str) -> bool:
    words = {word.lower() for word in _WORDS.findall(str(text or ""))}
    return bool(words & _REFUSING) or any(_A_REFUSAL_STATUS.match(word) for word in words)


def _subject(text: str) -> set[str]:
    """What a test's name says is refused - the field, the thing - without the words that say it is refused."""
    return {word for word in _words(text)
            if len(word) > 2 and not word.isdigit() and word not in _REFUSING and word not in _PLAIN}


def failing_tests(text: str) -> list[Failing]:
    """The failing tests a unit failure's text lists, with their messages."""
    return [Failing(name=m.group("name").strip(), where=(m.group("file") or m.group("within") or "").strip(),
                    message=m.group("message").strip()[:MOST_LISTED_MESSAGE])
            for m in _LISTED.finditer(str(text or ""))]


def _failing_in_the_pack_s_report(root: Path) -> list[Failing]:
    try:
        from app.acceptance import junit
        from app.stacks import contract

        found = contract.the_pack(root)
        if found is None or not getattr(found[0], "unit_report", ""):
            return []
        report = junit.read(root / str(found[1].get("project") or "") / found[0].unit_report)
        return [Failing(name=t.name, where=(t.file or t.suite or "").strip(), message=str(t.message or ""))
                for t in report.tests if t.outcome == "failed"]
    except Exception:  # noqa: BLE001 - the defect's own text is read instead
        return []


def _test_files(root: Path) -> list[Path]:
    from app.analysis.file_kinds import classify_file

    found: list[Path] = []
    for folder, folders, files in os.walk(root):
        folders[:] = sorted(f for f in folders if f not in NOT_THE_PRODUCT and not f.startswith("."))
        for name in sorted(files):
            relative = (Path(folder) / name).relative_to(root).as_posix()
            if _row_for(name) is not None and classify_file(relative) == "test":
                found.append(Path(folder) / name)
                if len(found) >= MOST_FILES:
                    return found
    return found


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:MOST_FILE_CHARACTERS]
    except OSError:
        return ""


def _bare_name(name: str) -> str:
    """A test's own name: the last part of `Class.method`, `file::test`, `suite › test`, without its parameters."""
    name = re.sub(r"\[.*\]$|\(.*\)$", "", str(name or "").strip())
    return re.split(r"::|›|#|\.|/", name)[-1].strip()


def the_file_of(root: Path, test: Failing, files: list[Path]) -> tuple[Path, str] | None:
    """The test file `test` is in, with its text: by where the report says, else the file that defines its name."""
    where = test.where.replace("\\", "/")
    if where:
        named = root / where
        if named.is_file():
            return named, _read(named)
        # A file's path, or a class's qualified name (`app.notes.NotesControllerTest`).
        stem = Path(where).stem if _row_for(where) else re.split(r"[./]", where.rstrip("/"))[-1]
        for path in files:
            if path.stem == stem or path.as_posix().endswith(where):
                return path, _read(path)
    bare = _bare_name(test.name)
    if len(bare) < 3:
        return None
    defined = re.compile(rf"\b{re.escape(bare)}\b")
    for path in files:
        text = _read(path)
        if defined.search(text):
            return path, text
    return None


def _acceptance_tests(root: Path) -> list[tuple[str, str, str]]:
    """Each locked acceptance test of the last run: (name, its criterion's text, outcome)."""
    try:
        from app.acceptance import suite

        saved = suite.last_result(root) or {}
    except Exception:  # noqa: BLE001
        return []
    tests: list[tuple[str, str, str]] = []
    for group in ("criteria", "change_requests"):
        for criterion in (saved.get(group) or {}).values():
            for test in (criterion or {}).get("tests") or []:
                tests.append((str(test.get("name") or ""), str((criterion or {}).get("text") or ""),
                              str(test.get("outcome") or "")))
    return tests


def the_acceptance_test_that_refuses(root: Path, unit_test: str) -> str:
    """The passing locked acceptance test that refuses what `unit_test` expects refused; "" when none does.

    One that says it refuses (in its name or its criterion) and shares with the unit test's name a word of what is
    refused - the field or the thing - that is not in most of the suite's tests (the product's own noun is in all of
    them and says nothing of which input).
    """
    tests = _acceptance_tests(root)
    if not tests:
        return ""
    common: dict[str, int] = {}
    for name, criterion, _ in tests:
        for word in _subject(f"{name} {criterion}"):
            common[word] = common.get(word, 0) + 1
    everywhere = {word for word, count in common.items() if len(tests) > 1 and count > len(tests) / 2}
    wanted = _subject(unit_test) - everywhere
    best, best_shared = "", 0
    for name, criterion, outcome in tests:
        if outcome != "passed" or not _says_it_refuses(f"{name} {criterion}"):
            continue
        shared = len(wanted & _subject(f"{name} {criterion}"))
        if shared > best_shared:
            best, best_shared = name, shared
    return best


def _named(items: Iterable[str]) -> str:
    return ", ".join(f"`{item}`" for item in list(items)[:MOST_NAMED])


def for_a_fixer(root: str | Path, defect: Any) -> str:
    """The fixer's section for a failing unit test whose stand-in hides a rule the product keeps; "" otherwise.

    Never raises: a fixer is better without it than without its request.
    """
    try:
        from app.agents.stand_in_rule import FOR_A_FIXER

        root = Path(root)
        text = "\n".join(str(getattr(defect, field, "") or "") for field in ("description", "actual_behavior"))
        failing = [t for t in [*_failing_in_the_pack_s_report(root), *failing_tests(text)]
                   if expects_a_refusal_it_did_not_get(t.message)]
        if not failing:
            return ""
        files = _test_files(root)
        lines: list[str] = []
        seen: set[str] = set()
        for test in failing:
            if test.name in seen or len(lines) >= MOST_NAMED:
                continue
            seen.add(test.name)
            located = the_file_of(root, test, files)
            if located is None:
                continue
            path, source = located
            stand_ins = stand_ins_in(path.name, source)
            if not stand_ins:
                continue
            refusing = the_acceptance_test_that_refuses(root, f"{test.name} {test.where}")
            if not refusing:
                continue
            lines.append(
                f"- The product already refuses this: the locked acceptance test `{refusing}` passes. "
                f"`{_bare_name(test.name)}` in `{path.relative_to(root).as_posix()}` expected a refusal and got a "
                f"success, because this test's stand-in for {_named(stand_ins)} hides the rule: test it where it "
                "lives (that component's own test) or without the stand-in, and keep this test to what the code "
                "under test does itself."
            )
        if not lines:
            return ""
        return f"\n{HEADING}\n" + "\n".join(lines) + f"\n{FOR_A_FIXER}\n"
    except Exception:  # noqa: BLE001
        return ""


__all__ = [
    "Failing", "HEADING", "expects_a_refusal_it_did_not_get", "failing_tests", "for_a_fixer", "stand_ins_in",
    "the_acceptance_test_that_refuses", "the_file_of",
]
