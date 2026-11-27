"""Whether a setup's test runner reports a failing test, and whether a suite's runner crashed in the setup's own file.

Measured on one run of a library with no framework: the setup stage wrote its own runner, a wrapper that turns the
language's test results into JUnit XML. Its smoke tests passed, so the setup was proven and kept for later runs. The
wrapper crashed on the first failing test it ever saw (a type error in the branch that writes a failure), and a
failing acceptance test before the build is the normal case: the suite wrote no report, five rounds of the suite's
writers were spent on tests that were right, and the run failed. A runner that passes a passing smoke test proves
nothing about failures.

So a setup is proven against a failing test too (`reports_failures`): two short tests in the language of the setup's
test files - one that fails an assertion, one that raises - are written beside the smoke tests, the declared command
is run, and the report must name both as failed. They are removed straight after. The table of those tests is per
language, read from the test files' extension; a language not in it is not checked (said in the step).

And a suite whose runner crashed in a file the setup provides (`the_setup_s_runner_crashed`) is the setup's to
repair, not the suite's writers': see `app.graph.runner_repair`.
"""

from __future__ import annotations

import fnmatch
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Sequence

from app.acceptance import junit

logger = logging.getLogger(__name__)

#: The names the two tests carry, found in the report's test names.
FAILS = "fails_on_purpose"
RAISES = "raises_on_purpose"
#: The stem of the file they are written to, shaped to the declared pattern.
STEM = "harness_failure_report_check"

_PYTHON = f'''"""Written by the harness to check that the runner reports a failing test; removed straight after."""
import unittest


def test_{FAILS}():
    assert 1 == 2, "this test fails on purpose"


def test_{RAISES}():
    raise RuntimeError("this test raises on purpose")


class FailureReportCheck(unittest.TestCase):
    def test_{FAILS}(self):
        self.assertEqual(1, 2, "this test fails on purpose")

    def test_{RAISES}(self):
        raise RuntimeError("this test raises on purpose")
'''

_JS_BODY = f"""{{declare}}
{{test}}('{FAILS}', () => {{{{
  {{assertion}}
}}}});

{{test}}('{RAISES}', () => {{{{
  throw new TypeError('this test raises on purpose');
}}}});
"""

_EXPECT = "expect(1).toBe(2);"
_THROWN = "const error = new Error('this test fails on purpose: expected 1 to be 2'); error.name = 'AssertionError'; throw error;"
_ASSERT = "assert.equal(1, 2, 'this test fails on purpose');"

#: A JavaScript or TypeScript runner by the words that name it in its smoke test, its command or its scripts; each
#: with what its tests import (ESM, CommonJS), the call that declares a test and the failing assertion. First found wins.
_JS_RUNNERS = (
    ("vitest", (r"from\s+['\"]vitest['\"]", r"\bvitest\b"),
     ("import { test, expect } from 'vitest';\n", "const { test, expect } = require('vitest');\n"), "test", _EXPECT),
    ("playwright", (r"from\s+['\"]@playwright/test['\"]", r"\bplaywright\b"),
     ("import { test, expect } from '@playwright/test';\n", "const { test, expect } = require('@playwright/test');\n"),
     "test", _EXPECT),
    ("node", (r"['\"]node:test['\"]", r"node\s+(?:\S+\s+)*--test\b", r"\bnode:test\b"),
     ("import { test } from 'node:test';\nimport assert from 'node:assert/strict';\n",
      "const { test } = require('node:test');\nconst assert = require('node:assert/strict');\n"), "test", _ASSERT),
    ("jest", (r"\bjest\b",), ("", ""), "test", _EXPECT),
)
#: Mocha, Jasmine and any runner that gives its tests `it` without an import.
_JS_GLOBALS = ("", ""), "it", _THROWN

_RUBY_SPEC = f"""# Written by the harness to check that the runner reports a failing test; removed straight after.
RSpec.describe 'failure report check' do
  it '{FAILS}' do
    expect(1).to eq(2)
  end

  it '{RAISES}' do
    raise 'this test raises on purpose'
  end
end
"""
_RUBY_MINITEST = f"""# Written by the harness to check that the runner reports a failing test; removed straight after.
require 'minitest/autorun'

class FailureReportCheck < Minitest::Test
  def test_{FAILS}
    assert_equal 1, 2, 'this test fails on purpose'
  end

  def test_{RAISES}
    raise 'this test raises on purpose'
  end
end
"""

_JS_SUFFIXES = (".js", ".mjs", ".cjs", ".jsx", ".ts", ".mts", ".cts", ".tsx")


def _a_name_matching(pattern: str) -> str:
    """A file name the declared pattern matches, with the check's stem in its first wildcard; "" when none can be made."""
    last = PurePosixPath(str(pattern or "").strip() or "x").name
    last = re.sub(r"\{([^,}]*)(?:,[^}]*)?\}", r"\1", last)  # `*.{test,spec}.ts` -> `*.test.ts`
    if "*" not in last:
        return ""
    name = last.replace("*", STEM, 1).replace("*", "").replace("?", "x")
    name = re.sub(r"\[[^\]]*\]", "x", name)
    return name if fnmatch.fnmatch(name, re.sub(r"\{([^,}]*)(?:,[^}]*)?\}", r"\1", PurePosixPath(pattern).name)) else ""


def _words(project_root: Path, argv: Sequence[str], test_dir: str) -> str:
    """What names the runner: the smoke tests beside the check, the command, and the project's scripts."""
    parts = [" ".join(argv)]
    folder = project_root / test_dir
    if folder.is_dir():
        for path in sorted(folder.glob("*"))[:6]:
            if path.is_file() and path.suffix in _JS_SUFFIXES:
                parts.append(path.read_text(encoding="utf-8", errors="replace")[:2000])
    try:
        scripts = json.loads((project_root / "package.json").read_text(encoding="utf-8")).get("scripts") or {}
        parts.extend(str(value) for value in scripts.values())
    except (OSError, ValueError, AttributeError):
        pass
    return "\n".join(parts)


def _esm(project_root: Path, name: str) -> bool:
    suffix = PurePosixPath(name).suffix
    if suffix in {".mjs", ".mts", ".ts", ".tsx"}:
        return True
    if suffix in {".cjs", ".cts"}:
        return False
    try:
        return json.loads((project_root / "package.json").read_text(encoding="utf-8")).get("type") == "module"
    except (OSError, ValueError, AttributeError):
        return False


def failure_tests(project_root: str | Path, argv: Sequence[str], test_dir: str, pattern: str) -> dict[str, str]:
    """The check's test file for this runner, {project-relative path: text}; {} for a language not in the table."""
    root = Path(project_root)
    name = _a_name_matching(pattern)
    if not name:
        return {}
    relative = (PurePosixPath(str(test_dir or ".").strip("/") or ".") / name).as_posix()
    suffix = PurePosixPath(name).suffix
    if suffix == ".py":
        return {relative: _PYTHON}
    if suffix == ".rb":
        words = " ".join(argv) + " " + name
        return {relative: _RUBY_SPEC if ("rspec" in words or name.endswith("_spec.rb")) else _RUBY_MINITEST}
    if suffix in _JS_SUFFIXES:
        words = _words(root, argv, test_dir)
        imports, call, assertion = _JS_GLOBALS
        for _name, signs, its_imports, its_call, its_assertion in _JS_RUNNERS:
            if any(re.search(sign, words) for sign in signs):
                imports, call, assertion = its_imports, its_call, its_assertion
                break
        declare = imports[0] if _esm(root, name) else imports[1]
        header = "// Written by the harness to check that the runner reports a failing test; removed straight after.\n"
        return {relative: header + _JS_BODY.format(declare=declare, test=call, assertion=assertion)}
    return {}


@dataclass
class Checked:
    """What the check found: `ok`, or `problem` saying what the runner did with a failing test."""

    ok: bool
    problem: str = ""
    step: dict[str, Any] = field(default_factory=dict)
    checked: bool = True


def _named_failed(report: junit.Report, token: str) -> bool:
    return any(test.outcome == "failed" and token in f"{test.name} {test.suite} {test.within}".replace(" ", "_")
               for test in report.tests)


def reports_failures(
    project_root: str | Path,
    argv: Sequence[str],
    report: str,
    test_dir: str,
    pattern: str,
    run: Callable[[Sequence[str], str, str], dict[str, Any]],
    project: str,
    label: str = "unit",
) -> Checked:
    """Run the declared command with a failing and a raising test added; ok when its report names both as failed.

    `run(argv, category, project)` runs a command as the setup's proof does. The tests are removed and the report
    cleared afterwards, whatever happened. A language not in the table is not checked: ok, `checked` False.
    """
    from app.stacks.scaffold import _exit_code, _tail, where_it_failed

    root = Path(project_root)
    written = failure_tests(root, argv, test_dir, pattern)
    if not written:
        return Checked(ok=True, checked=False, step={
            "command": f"failure report check of the {label} runner", "exit_code": 0,
            "output": f"not checked: no failing test is written for `{pattern}` files"})
    for relative, text in written.items():
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_text(text, encoding="utf-8")
    try:
        junit.clear(root / report)
        outcome = run(list(argv), "test", project)
        code = _exit_code(outcome)
        output = _tail(outcome)
        parsed = junit.read(root / report)
    finally:
        for relative in written:
            (root / relative).unlink(missing_ok=True)
            for compiled in (root / relative).parent.glob(f"__pycache__/{PurePosixPath(relative).stem}.*"):
                compiled.unlink(missing_ok=True)
        junit.clear(root / report)
    step = {"command": " ".join(argv) + f" (with {', '.join(written)}: one failing, one raising test)",
            "exit_code": code, "output": output}
    fails, raises = _named_failed(parsed, FAILS), _named_failed(parsed, RAISES)
    if parsed.found and fails and raises:
        return Checked(ok=True, step=step)
    if not parsed.found:
        what = f"wrote no report at `{report}`"
    else:
        named = [token for token, seen in ((FAILS, fails), (RAISES, raises)) if seen]
        what = (f"wrote a report at `{report}` that names {'only ' + named[0] if named else 'neither of them'} "
                "as failed")
    problem = (
        f"The {label} runner cannot report a failing test. With `{', '.join(written)}` added - one test that fails "
        f"an assertion (`{FAILS}`) and one that raises an error (`{RAISES}`) - `{' '.join(argv)}` exited {code} and "
        f"{what}. Before the product is built most tests fail, so a runner that crashes or stays silent on a "
        "failure leaves every later run of the suite without a report. The runner must write each failing or "
        "erroring test into its report as failed and go on to the next. Its output ended:\n"
        f"{where_it_failed(output, 1200)}"
    )
    return Checked(ok=False, problem=problem, step=step)


# --- a suite whose runner crashed in the setup's own file -------------------------------------------------------

_PYTHON_FRAME = re.compile(r'File "(?P<path>[^"]+)", line (?P<line>\d+)')
#: `at f (/path/x.js:12:5)`, `/path/x.rb:12:in`, `x.go:12 +0x..`, `(X.java:12)`: a file and a line.
_ANY_FRAME = re.compile(r"(?P<path>[\w@~./\\-]+\.[A-Za-z]{1,5}):(?P<line>\d+)")
_TRACEBACK = "Traceback (most recent call last)"


@dataclass
class Crash:
    """A runner that crashed in a file the setup provides: the file, the line and the traceback."""

    file: str
    line: int
    traceback: str

    def as_dict(self) -> dict[str, Any]:
        return {"file": self.file, "line": self.line, "traceback": self.traceback}


def _the_innermost_frame(output: str) -> tuple[str, int, int] | None:
    """(path, line, where in the output) of the frame an error was raised in, or None."""
    text = str(output or "")
    at = text.rfind(_TRACEBACK)
    if at >= 0:
        frames = [m for m in _PYTHON_FRAME.finditer(text, at) if not m.group("path").startswith("<")]
        if frames:
            last = frames[-1]
            return last.group("path"), int(last.group("line")), at
    # Most other languages list the innermost frame first, after the error's own line.
    found = next((m for m in _ANY_FRAME.finditer(text)
                  if not m.group("path").startswith(("node:", "internal/"))), None)
    return (found.group("path"), int(found.group("line")), max(0, found.start() - 400)) if found else None


def _the_setup_s_files(repo_root: str | Path) -> tuple[str, list[str]]:
    """(project, project-relative files the proven setup provides): its kept files and the files its commands run."""
    from app.stacks import contract
    from app.stacks.custom_setup import PROVEN_SETUP

    record = contract.read(repo_root) or {}
    setup = record.get("setup")
    if record.get("pack") != PROVEN_SETUP or not isinstance(setup, dict):
        return "", []
    project = str(record.get("project") or "")
    files = [str(name) for name in dict(setup.get("kept") or {})]
    files.extend(str(name) for name in dict(setup.get("released_runner") or {}))
    project_root = Path(repo_root) / project
    for command in (setup.get("unit_test") or [], setup.get("acceptance_test") or []):
        argv = [str(part) for part in command]
        for index, part in enumerate(argv):
            module = argv[index + 1] if part == "-m" and index + 1 < len(argv) else ""
            for candidate in (part, module.replace(".", "/") + ".py" if module else ""):
                if candidate and not candidate.startswith("-") and (project_root / candidate).is_file():
                    files.append(PurePosixPath(candidate).as_posix().lstrip("./"))
    return project, list(dict.fromkeys(files))


def the_setup_s_runner_crashed(repo_root: str | Path, output: str) -> Crash | None:
    """The crash, when the error in `output` was raised inside a file the proven setup provides; None otherwise.

    The frame an error was raised in decides: a test file that fails to import, with the runner's own frames above
    it, is the suite's; an error raised in the runner itself is the setup's.
    """
    project, files = _the_setup_s_files(repo_root)
    frame = _the_innermost_frame(output)
    if not files or frame is None:
        return None
    path, line, at = frame
    shown = path.replace("\\", "/")
    for name in files:
        if shown == name or shown.endswith("/" + name):
            excerpt = str(output)[at:at + 2500].strip()
            return Crash(file=name, line=line, traceback=excerpt)
    return None


__all__ = ["Checked", "Crash", "FAILS", "RAISES", "failure_tests", "reports_failures", "the_setup_s_runner_crashed"]
