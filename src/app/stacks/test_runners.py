"""One row per test runner a suite is run with: which of its words choose the tests a command runs (LF.1589).

`sandbox` compares test commands by their argv. That is too fine for a runner whose options mostly change how it runs
rather than what: measured on a page product, the suite's writer ran `npm run test:e2e`, then `npx playwright test`,
then `npx playwright test --reporter=line --workers=4` - three spellings of one whole-suite run, each to the
300-second limit, a quarter of an hour in one stage - and no exact-argv check could see they were one run.

So a runner says here, once, what the mechanisms need of it: the words that name it, the options that choose which
tests run (and those that only change how they run), whether its positional words name test files, the option that
holds each test to a time limit of its own, and how a command asks it for fewer tests. A runner missing here is
compared by its argv, as before. Runner-specific words belong here, in a pack or in `app.plugins.seed`; the mechanisms
read them from this table (`app.tools.suite_timeouts`).
"""

from __future__ import annotations

import json
import os
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence


@dataclass(frozen=True)
class TestRunner:
    #: Its name, as the stack tables and the custom setup name it.
    name: str
    #: The language its suites are written in (`app.stacks.languages`).
    language: str
    #: The words that run it, after any launcher (`npx`) or manifest script is read through.
    words: tuple[str, ...]
    #: Options that choose which tests run: one more of these is a narrower run.
    selecting: frozenset[str]
    #: Options, selecting or not, that take the next word as their value when not written `--option=value`.
    valued: frozenset[str]
    #: Short spellings of an option, read as the long one.
    aliases: Mapping[str, str] = field(default_factory=dict)
    #: Whether a word that is not an option names test files or folders to run: a narrower run.
    positional_selects: bool = True
    #: The option holding each test to a limit of its own, `{ms}` the milliseconds; "" when it has none.
    per_test_limit: str = ""
    #: The limit a run of a suite gets while nothing it tests is built yet (`app.tools.suite_timeouts`).
    short_limit_ms: int = 5_000
    #: The option asking for the tests whose names match a pattern, followed by the pattern.
    by_name: str = ""
    #: Whether its tests run in a browser.
    browser: bool = False


RUNNERS: tuple[TestRunner, ...] = (
    TestRunner(
        name="playwright",
        language="javascript",
        words=("playwright", "test"),
        selecting=frozenset({
            "--grep", "--grep-invert", "--project", "--shard", "--last-failed", "--only-changed", "--test-list",
            "--test-list-invert", "--max-failures", "--list", "--config",
        }),
        valued=frozenset({
            "--grep", "--grep-invert", "--project", "--shard", "--test-list", "--test-list-invert", "--max-failures",
            "--config", "--reporter", "--workers", "--timeout", "--global-timeout", "--retries", "--repeat-each",
            "--output", "--trace", "--tsconfig", "--browser",
        }),
        aliases={"-g": "--grep", "-c": "--config", "-j": "--workers", "-x": "--max-failures=1"},
        per_test_limit="--timeout={ms}",
        by_name="--grep",
        browser=True,
    ),
)

#: Launchers that run the executable named after them (and its own options before it).
_LAUNCHERS = {"npx": (), "pnpx": (), "bunx": (), "pnpm": ("exec", "dlx"), "yarn": ("exec", "dlx"), "bun": ("x",)}
#: Package managers that run a script of `package.json` by name: (the words before the name, whether the arguments
#: after it reach the script only after a `--`).
_SCRIPT_RUNNERS: dict[str, tuple[frozenset[str], bool]] = {
    "npm": (frozenset({"run", "run-script"}), True),
    "pnpm": (frozenset({"run"}), False),
    "yarn": (frozenset({"run"}), False),
    "bun": (frozenset({"run"}), False),
}
#: `npm test` and its short form run the script named `test`.
_TEST_SCRIPT_SHORTHANDS = {"test": "test", "t": "test"}
#: What a script chains its commands with: only the last command receives the arguments a script runner appends.
_CHAINED = re.compile(r"\s*(?:&&|\|\||;)\s*")


@dataclass(frozen=True)
class RunnerCall:
    """A command read as a run of a table runner: the runner, the words it receives after its own, and how a
    word is added for it (after a `--` for a script runner that needs one)."""

    runner: TestRunner
    arguments: tuple[str, ...]
    needs_separator: bool = False


def _script_of(project_dir: Path, name: str) -> str | None:
    try:
        scripts = json.loads((project_dir / "package.json").read_text(encoding="utf-8")).get("scripts") or {}
    except (OSError, ValueError, AttributeError):
        return None
    script = scripts.get(name) if isinstance(scripts, dict) else None
    return script if isinstance(script, str) else None


def _through_a_script(argv: list[str], project_dir: Path) -> tuple[list[str], bool] | None:
    """(the words the manifest script runs, with the command's own appended; whether the command needs `--`), or None."""
    head = os.path.basename(argv[0]) if argv else ""
    if head not in _SCRIPT_RUNNERS:
        return None
    before_the_name, needs_separator = _SCRIPT_RUNNERS[head]
    rest = argv[1:]
    if rest and rest[0] in before_the_name and len(rest) > 1:
        name, extra = rest[1], rest[2:]
    elif head == "npm" and rest and rest[0] in _TEST_SCRIPT_SHORTHANDS:
        name, extra = _TEST_SCRIPT_SHORTHANDS[rest[0]], rest[1:]
    elif head != "npm" and rest and not rest[0].startswith("-") and rest[0] not in _LAUNCHERS.get(head, ()):
        name, extra = rest[0], rest[1:]
    else:
        return None
    script = _script_of(project_dir, name)
    if script is None:
        return None
    if needs_separator:
        extra = extra[extra.index("--") + 1:] if "--" in extra else []
    elif extra[:1] == ["--"]:
        extra = extra[1:]
    try:
        last = shlex.split(_CHAINED.split(script.strip())[-1])
    except ValueError:
        return None
    return [*last, *extra], needs_separator


def _past_a_launcher(argv: list[str]) -> list[str]:
    head = os.path.basename(argv[0]) if argv else ""
    if head not in _LAUNCHERS:
        return argv
    rest = argv[1:]
    subcommands = _LAUNCHERS[head]
    if subcommands:
        if not rest or rest[0] not in subcommands:
            return argv
        rest = rest[1:]
    while rest and rest[0].startswith("-"):
        rest = rest[1:]
    return rest


def read(argv: Sequence[str], project_dir: str | Path) -> RunnerCall | None:
    """This command as a run of a runner in the table - directly, through a launcher or through a manifest script -
    or None. Never raises."""
    try:
        words = [str(part) for part in argv]
        needs_separator = False
        scripted = _through_a_script(words, Path(project_dir))
        if scripted:
            words, needs_separator = scripted
        words = _past_a_launcher(words)
        if words:
            words = [os.path.basename(words[0]), *words[1:]]
        for runner in RUNNERS:
            if tuple(words[: len(runner.words)]) == runner.words:
                return RunnerCall(runner, tuple(words[len(runner.words):]), needs_separator)
    except Exception:  # noqa: BLE001 - an unread command is compared by its argv, as before
        return None
    return None


def selection(call: RunnerCall) -> frozenset[str]:
    """The words of a run that choose which of its tests run, each option with its value (`--grep=AC-6`)."""
    runner = call.runner
    chosen: set[str] = set()
    words = list(call.arguments)
    index = 0
    while index < len(words):
        word = runner.aliases.get(words[index], words[index])
        index += 1
        if word == "--":
            continue
        if word.startswith("-"):
            name, has_value, value = word.partition("=")
            if not has_value and name in runner.valued and index < len(words):
                value, index = words[index], index + 1
            if name in runner.selecting:
                chosen.add(f"{name}={value}" if (has_value or name in runner.valued) else name)
        elif runner.positional_selects:
            chosen.add(word)
    return frozenset(chosen)


def holds_each_test_to_a_limit(call: RunnerCall) -> bool:
    """Whether the run already names its own per-test limit."""
    option = call.runner.per_test_limit.split("=", 1)[0]
    return bool(option) and any(word == option or word.startswith(option + "=") for word in call.arguments)


def with_words(argv: Sequence[str], call: RunnerCall, *added: str) -> list[str]:
    """The command with `added` passed to its runner (after a `--` where its script runner needs one)."""
    words = [str(part) for part in argv]
    separator = ["--"] if call.needs_separator and "--" not in words else []
    return [*words, *separator, *added]


def with_a_short_limit_per_test(argv: Sequence[str], call: RunnerCall) -> tuple[list[str], str]:
    """(the command with each test held to the runner's short limit, the option added); the command as it is and ""
    when the runner has no such option or the command names its own."""
    runner = call.runner
    if not runner.per_test_limit or holds_each_test_to_a_limit(call):
        return [str(part) for part in argv], ""
    option = runner.per_test_limit.format(ms=runner.short_limit_ms)
    return with_words(argv, call, option), option


def narrower_forms(argv: Sequence[str], call: RunnerCall, *, name: str = "", file: str = "") -> list[str]:
    """Commands that run fewer of these tests: those whose names carry `name`, and one test file `file`."""
    runner = call.runner
    forms = []
    if runner.by_name and name:
        forms.append(" ".join(with_words(argv, call, runner.by_name, name)))
    if runner.positional_selects and file:
        forms.append(" ".join(with_words(argv, call, file)))
    return forms
