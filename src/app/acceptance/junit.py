"""Read a JUnit XML report into one result per test.

JUnit XML is the one report format every runner the stack packs use can write:
Playwright (`junit` reporter), `node --test` (`--test-reporter=junit`), pytest
(`--junitxml`), Vitest, Jest (through `jest-junit`), Go and Cargo through
converters. Reading it - rather than each runner's console output - is what
lets the harness judge a run without knowing which runner produced it.

Everything here degrades rather than raises: a missing or malformed report is
an empty result, and the caller decides what an absent report means.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

#: A criterion or change-request id inside a test's name. A runner whose test
#: names are free text writes `[AC-3]`; one whose names are identifiers writes
#: `test_ac3_...` or `test_AC_3_...`. Several may appear in one name, since a
#: test may prove more than one criterion. Not preceded by a letter or digit, so
#: `pac3` and `access` are not tags.
#:
#: Any dash a model types: on one run every id in a milestone review was
#: written `AC\u20112` (a non-breaking hyphen), so the harness saw no criterion
#: in it, could not tell that all four belonged to later sprints, and the
#: sprint was sent back three times and escalated over work not yet due.
TAG = re.compile(
    r"(?<![A-Za-z0-9])(AC|CR)[-_\u2010-\u2015\u2212\ufe58\ufe63\uff0d]?(\d+)(?![0-9])", re.I
)


def tags_in(text: str) -> tuple[str, ...]:
    """The criterion and change-request ids `text` names, as `AC-3`, in order."""
    found = (f"{kind.upper()}-{int(number)}" for kind, number in TAG.findall(text))
    return tuple(dict.fromkeys(found))


#: How much of a failure message is kept per test. A stack trace past this is
#: rarely what a fix stage needs, and many failures make a long report.
MAX_MESSAGE_CHARS = 1_500


@dataclass(frozen=True)
class TestResult:
    """One test case as the runner reported it."""

    name: str
    suite: str = ""
    file: str = ""
    outcome: str = "passed"  # passed | failed | skipped
    message: str = ""
    seconds: float = 0.0

    @property
    def tags(self) -> tuple[str, ...]:
        """The criterion and change-request ids this test names, in order."""
        return tags_in(f"{self.suite} {self.name}")


@dataclass
class Report:
    """Every test in one report."""

    tests: list[TestResult] = field(default_factory=list)
    found: bool = False  # whether a parseable report existed at all

    @property
    def passed(self) -> int:
        return sum(1 for test in self.tests if test.outcome == "passed")

    @property
    def failed(self) -> int:
        return sum(1 for test in self.tests if test.outcome == "failed")

    @property
    def skipped(self) -> int:
        return sum(1 for test in self.tests if test.outcome == "skipped")


def _text_of(element: ET.Element) -> str:
    """A failure's message attribute and body, joined and trimmed."""
    parts = [element.get("message") or "", element.text or ""]
    text = "\n".join(part.strip() for part in parts if part and part.strip())
    return text[:MAX_MESSAGE_CHARS]


def parse(text: str) -> Report:
    """Parse a JUnit XML document. A malformed document is an empty report."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return Report()
    report = Report(found=True)
    for case in root.iter("testcase"):
        outcome = "passed"
        message = ""
        for child in case:
            tag = child.tag.lower()
            if tag in {"failure", "error"}:
                outcome = "failed"
                message = _text_of(child)
                break
            if tag == "skipped":
                outcome = "skipped"
                message = _text_of(child)
        try:
            seconds = float(case.get("time") or 0)
        except ValueError:
            seconds = 0.0
        report.tests.append(
            TestResult(
                name=(case.get("name") or "").strip(),
                suite=(case.get("classname") or "").strip(),
                file=(case.get("file") or "").strip(),
                outcome=outcome,
                message=message,
                seconds=seconds,
            )
        )
    return report


def read(path: str | Path) -> Report:
    """Parse the report at `path`; an absent or unreadable file is an empty report."""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return Report()
    return parse(text)
