"""Failing unit tests that share one store: a test counts or lists records other tests of its file stored (LF.1316).

Measured on a full-stack run: a store's unit tests failed with "6 !== 1" and with six records - titled as the file's
other tests titled the records they made - where an empty list was expected. One store file served the whole test
file, so each test's records stayed for the next. The fixer held to test files rewrote the file five times over two
rounds without giving each test an empty store; it was never told that the records came from the other tests.

So a fixer of failing unit tests is told, when the evidence is there: a failing test's message shows a count or a list
larger than it expected (its runner's wording, `app.stacks.languages` `more_than_expected`), and the message carries
values written as literals only in other tests of the same file - not in the failing test, not in the file's shared
setup, not in the product's own code - so they are records those tests stored. Then the section names the records,
the tests that made them, every failing test of the file that counts more than it expected, and how a test in that
language starts from an empty store (`fresh_store`). A unit test failing on a real fault - no value another test wrote
in its message, or no count or list larger than expected - is given nothing.

Where one test begins in a file is read by its language's `test_starts`.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from app.analysis.stand_in_tests import (
    Failing, bare_name, failing_in_the_pack_s_report, failing_tests, read_text, row_for, test_files, the_file_of,
)
from app.stacks.languages import NOT_THE_PRODUCT, Gap, LanguageSupport

#: How the fixer's section begins: the effects report counts it (`loop.sh effects`).
HEADING = "--- These unit tests share stored data ---"

#: Records, tests that made them and tests that count more, named in the section, each.
MOST_NAMED = 5
#: Files of the product's own code read for a value it writes itself (a default record it seeds).
MOST_PRODUCT_FILES = 300
#: Characters of a failure's message read.
MOST_MESSAGE = 4_000

#: A literal in a test file: quoted with ', " or `, on one line, holding a letter.
_LITERAL = re.compile(r"'([^'\\\n]{2,80})'|\"([^\"\\\n]{2,80})\"|`([^`\\\n$]{2,80})`")
_A_LETTER = re.compile(r"[A-Za-z]")


@dataclass(frozen=True)
class OneTest:
    """One test of a file: its name, and where its text starts and ends."""

    name: str
    start: int
    end: int


def _patterns(row: LanguageSupport, field: str) -> list[re.Pattern[str]]:
    value = getattr(row, field)
    return [] if isinstance(value, Gap) else [re.compile(pattern) for pattern in value]


def shows_more_than_expected(path: str, message: str) -> bool:
    """Whether a failure's message, from a test in the file `path`, says a count or a list came back larger than expected.

    A count's pattern reads both numbers, and only a larger one than expected counts; a list's says it by its shape.
    """
    row = row_for(path)
    if row is None:
        return False
    text = str(message or "")[:MOST_MESSAGE]
    for pattern in _patterns(row, "more_than_expected"):
        for match in pattern.finditer(text):
            found = {key: value for key, value in match.groupdict().items() if value is not None}
            if "expected" not in found or "got" not in found:
                return True
            if int(found["got"]) > int(found["expected"]):
                return True
    return False


def tests_in(path: str, text: str) -> list[OneTest]:
    """The tests a file defines, in order, each running to where the next begins; [] in a language not read."""
    row = row_for(path)
    if row is None:
        return []
    starts: dict[int, str] = {}
    for pattern in _patterns(row, "test_starts"):
        for match in pattern.finditer(text):
            name = match.groupdict().get("name") or match.groupdict().get("id") or ""
            if name.strip():
                starts.setdefault(match.start(), name.strip())
    ordered = sorted(starts.items())
    return [OneTest(name=name, start=start, end=ordered[i + 1][0] if i + 1 < len(ordered) else len(text))
            for i, (start, name) in enumerate(ordered)]


def _literals(text: str) -> list[str]:
    found: dict[str, None] = {}
    for match in _LITERAL.finditer(text):
        value = next(group for group in match.groups() if group is not None).strip()
        if value and _A_LETTER.search(value):
            found.setdefault(value, None)
    return list(found)


def _without_start_lines(text: str, start: int, end: int) -> str:
    """A test's text without the line that opens it, where its name is written."""
    body = text[start:end]
    return body.split("\n", 1)[1] if "\n" in body else ""


def _in_message(value: str, message: str) -> bool:
    return re.search(rf"(?<![\w]){re.escape(value)}(?![\w])", message) is not None


def the_test_named(tests: list[OneTest], name: str) -> OneTest | None:
    """The test of a file a runner reported by `name` (its own name, or the last part of a qualified one)."""
    wanted = {str(name or "").strip(), bare_name(name)}
    for test in tests:
        if test.name in wanted or bare_name(test.name) in wanted:
            return test
    whole = str(name or "").strip()
    return next((test for test in tests if whole.endswith(test.name) and len(test.name) >= 6), None)


def leaked_records(path: str, source: str, failing: str, message: str) -> dict[str, list[str]]:
    """The values in `message` that only other tests of the file write, each with the tests that write it.

    {} when the failing test cannot be found in the file. A value the failing test writes itself, or the file's shared
    setup before its first test, is not leaked; nor is a test's own name.
    """
    tests = tests_in(path, source)
    own = the_test_named(tests, failing)
    if own is None:
        return {}
    text = str(message or "")[:MOST_MESSAGE]
    shared = set(_literals(source[: tests[0].start])) if tests else set()
    names = {test.name for test in tests}
    mine = set(_literals(source[own.start:own.end]))
    made_by: dict[str, list[str]] = {}
    for test in tests:
        if test is own:
            continue
        for value in _literals(_without_start_lines(source, test.start, test.end)):
            if value in mine or value in shared or value in names or not _in_message(value, text):
                continue
            made_by.setdefault(value, [])
            if test.name not in made_by[value]:
                made_by[value].append(test.name)
    # In the order the message shows them.
    return dict(sorted(made_by.items(), key=lambda item: text.find(item[0])))


def _product_files(root: Path, row: LanguageSupport) -> Iterable[Path]:
    from app.analysis.file_kinds import classify_file

    count = 0
    for folder, folders, files in os.walk(root):
        folders[:] = sorted(f for f in folders if f not in NOT_THE_PRODUCT and not f.startswith("."))
        for name in sorted(files):
            if Path(name).suffix.lower() not in row.suffixes:
                continue
            relative = (Path(folder) / name).relative_to(root).as_posix()
            if classify_file(relative) == "test":
                continue
            yield Path(folder) / name
            count += 1
            if count >= MOST_PRODUCT_FILES:
                return


def _not_the_product_s_own(root: Path, path: Path, leaked: dict[str, list[str]]) -> dict[str, list[str]]:
    """`leaked` without the values the product's own code writes: a record it seeds is in every store."""
    row = row_for(path.name)
    if row is None or not leaked:
        return leaked
    left = dict(leaked)
    for file in _product_files(root, row):
        code = read_text(file)
        for value in list(left):
            if any(f"{quote}{value}{quote}" in code for quote in ("'", '"', "`")):
                del left[value]
        if not left:
            break
    return left


def _names_first(values: Iterable[str]) -> list[str]:
    """Values as a person names a record (a capital, a space) ahead of the others, each kind in its given order."""
    values = list(values)
    return sorted(values, key=lambda value: not (" " in value or any(c.isupper() for c in value)))


def _named(items: Iterable[str]) -> str:
    return ", ".join(f"`{item}`" for item in list(items)[:MOST_NAMED])


def _one_file(root: Path, path: Path, source: str, tests: list[Failing]) -> str:
    """The section's line for one test file, or "" when its failing tests show no records another test stored."""
    leaked: dict[str, list[str]] = {}
    showing: list[str] = []
    counting: list[str] = []
    for test in tests:
        if not shows_more_than_expected(path.name, test.message):
            continue
        found = leaked_records(path.name, source, test.name, test.message)
        own = bare_name(test.name)
        if found:
            showing.append(own)
            for value, makers in found.items():
                leaked.setdefault(value, [])
                leaked[value].extend(m for m in makers if m not in leaked[value])
        else:
            counting.append(own)
    leaked = _not_the_product_s_own(root, path, leaked)
    if not leaked:
        return ""
    makers = list(dict.fromkeys(maker for makers in leaked.values() for maker in makers))
    relative = path.relative_to(root).as_posix()
    line = (f"- `{relative}`: the failing {_named(dict.fromkeys(showing))} got back records that other tests of the "
            f"file store - {_named(_names_first(leaked))}, stored by {_named(makers)}")
    if counting:
        line += f"; the failing {_named(dict.fromkeys(counting))} counted more than expected for the same reason"
    return line + ". The tests of this file share one store, so each sees what the tests before it stored."


def for_a_fixer(root: str | Path, defect: Any) -> str:
    """The fixer's section for failing unit tests that share one store; "" otherwise. Never raises."""
    try:
        from app.agents.own_store_rule import FOR_A_FIXER

        root = Path(root)
        text = "\n".join(str(getattr(defect, field, "") or "") for field in ("description", "actual_behavior"))
        seen: dict[str, Failing] = {}
        # The runner's report first: its messages are whole where the defect shows their error lines.
        for test in [*failing_in_the_pack_s_report(root), *failing_tests(text)]:
            seen.setdefault(test.name, test)
        if not seen:
            return ""
        files = test_files(root)
        by_file: dict[Path, tuple[str, list[Failing]]] = {}
        for test in seen.values():
            located = the_file_of(root, test, files)
            if located is None:
                continue
            by_file.setdefault(located[0], (located[1], []))[1].append(test)
        lines: list[str] = []
        how: dict[str, None] = {}
        for path, (source, tests) in by_file.items():
            line = _one_file(root, path, source, tests)
            if not line:
                continue
            lines.append(line)
            row = row_for(path.name)
            if row is not None and not isinstance(row.fresh_store, Gap):
                how.setdefault(row.fresh_store, None)
        if not lines:
            return ""
        return f"\n{HEADING}\n" + "\n".join([*lines, *how]) + f"\n{FOR_A_FIXER}\n"
    except Exception:  # noqa: BLE001 - a fixer is better without it than without its request
        return ""


__all__ = ["HEADING", "OneTest", "for_a_fixer", "leaked_records", "shows_more_than_expected", "tests_in"]
