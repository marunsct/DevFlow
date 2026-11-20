"""A dispute's ruling past the reclassification cap, confirmed by the harness itself (behind `CONTESTED_TESTS_CONFIRMED`).

Measured on one run: two locked tests sent the whole sign-in answer (`{"token": ...}`) as the bearer token, so the
product's 401 was right. The dispute called both wrong, but six earlier rulings on the same mistake - each quoting the
same inline call, none naming a helper - had each taken a place under the cap, so both stayed locked and the sprint
sat at 20 of 21 criteria for about an hour until its attempts ran out.

The cap stops reclassify-to-ship: a model's word alone must never rewrite what the product is checked against. So
past the cap a ruling counts only when the harness confirms the repair it implies, with no model in the loop:

1. The ruling quotes the code at fault in the test's own file, character for character, and its correction. The
   correction touches no line that asserts and adds no assertion, skip, early exit, branch or comment.
2. The locked test's file, run alone in the project's own runner against the product as it is, fails that test.
3. A copy of the file with the correction - written beside it under a name of its own, the locked file untouched,
   removed afterwards - passes that test, read by its name from the runner's report.
4. The copy fails that test against a deliberately broken product: one of a few deliberate changes (the release
   probe's operators, `acceptance.mutation`) to the product files holding the most of the test file's own string
   literals, the product still starting. A correction that makes a test pass whatever the product does is refuted.

Any leg that cannot be measured refutes: unknown is not confirmed. A confirmed ruling goes to QA through the suite's
own repair with the confirmed correction named, and the repaired suite is reviewed and locked as every repair is; the
harness never writes the locked file itself. Rulings that quote the same code at fault are one cause for the cap, as
rulings blaming one helper are (`acceptance_nodes.by_shared_cause`).
"""
from __future__ import annotations

import fnmatch
import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from app.observability.degraded import degraded

logger = logging.getLogger(__name__)

#: `CONTESTED_TESTS_CONFIRMED` set to on or off overrides this; off until measured.
ON_BY_DEFAULT = False
#: What the admin page says this switch does.
explanation = ("A dispute ruling past the reclassification cap may still send a locked test back to QA, but only when "
               "the harness confirms the repair it quotes: the locked test fails alone, a copy with the quoted "
               "correction passes, and the copy fails against a deliberately broken product. Rulings quoting the same "
               "faulty code count as one cause for the cap. Off until measured.")

#: What a confirmed ruling's repair line says; the switch's firing signal (`switch_firing.SIGNALS`).
SAYS = "The harness ran a copy of this test with"
#: The most runs of the project's runner one dispute may spend confirming rulings.
MOST_RUNS = 12
#: The most deliberate changes tried against one corrected copy.
MOST_MUTANTS = 3
#: The fewest characters quoted code must have to be told from prose, and to stand as one cause.
LEAST_CODE_CHARS = 6
#: In the name of a corrected copy, so one left behind by a stopped worker is found and removed.
COPY_MARK = "contested_copy"

Runner = Callable[[Sequence[str], str, str], dict[str, Any]]


def enabled() -> bool:
    from app.switches import is_on

    return is_on("CONTESTED_TESTS_CONFIRMED", ON_BY_DEFAULT)


@dataclass(frozen=True)
class Repair:
    """A repair a dispute proposes for one test: the code at fault, quoted, and what it should be."""

    test: str
    faulty: str
    corrected: str


def proposed_repairs(answer: Any) -> list[Repair]:
    """The repairs a dispute's answer proposes, each with a test, quoted code and a different correction. Never raises."""
    found: list[Repair] = []
    try:
        for item in getattr(answer, "repairs", None) or []:
            test = " ".join(str(getattr(item, "test", "") or "").split())
            faulty = str(getattr(item, "the_faulty_code", "") or "").strip()
            corrected = str(getattr(item, "the_corrected_code", "") or "").strip()
            if test and faulty and corrected and faulty != corrected:
                found.append(Repair(test, faulty, corrected))
    except Exception:  # noqa: BLE001 - no repair proposed
        return []
    return found


_TAGS = re.compile(r"^(?:\s*\[[^\]]+\])+\s*")
_LEADING_NAME = re.compile(r"^\s*`([^`]+)`")


def _plain(text: Any) -> str:
    return " ".join(str(text or "").split()).casefold()


def _short(name: str) -> str:
    """A test's own title: its last ` › ` or `::` part, without criterion tags."""
    last = re.split(r" › |::", str(name))[-1]
    return _TAGS.sub("", last).strip()


def _the_same_test(one: str, other: str) -> bool:
    return _plain(one) == _plain(other) or (bool(_short(one)) and _plain(_short(one)) == _plain(_short(other)))


def _test_of(line: str) -> str:
    found = _LEADING_NAME.match(str(line))
    return (found.group(1) if found else str(line)).strip()


def repair_for(line: str, repairs: Sequence[Repair]) -> Repair | None:
    """The repair proposed for the test a dispute's repair line names, or None."""
    test = _test_of(line)
    return next((repair for repair in repairs if _the_same_test(repair.test, test)), None)


def _code_like(text: str) -> bool:
    """Whether quoted text is code to compare, not a word: long enough, with a mark no prose word has."""
    return len(text) >= LEAST_CODE_CHARS and bool(re.search(r"[()\[\].=<>{}]", text))


def _suite_text(root: Any) -> str:
    from app.acceptance import suite

    parts = []
    for path in suite.suite_files(root):
        try:
            parts.append(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return "\n".join(parts)


def by_shared_expression(groups: list[list[str]], repairs: Sequence[Repair], root: Any) -> list[list[str]]:
    """`groups` with the rulings that quote the same code at fault, standing alone, made one group.

    Only identical code the suite holds, character for character: the same call written inline in several tests is
    one cause, as one helper is; two different faults stay apart. A group `by_shared_cause` made is kept as it is.
    Never raises; on any doubt the groups are returned unchanged.
    """
    try:
        text = _suite_text(root)
        merged: dict[str, list[str]] = {}
        out: list[list[str]] = []
        for group in groups:
            if isinstance(group, list) and len(group) == 1:
                repair = repair_for(group[0], repairs)
                if repair is not None and _code_like(repair.faulty) and repair.faulty in text:
                    if repair.faulty in merged:
                        merged[repair.faulty].append(group[0])
                        continue
                    merged[repair.faulty] = [group[0]]
                    out.append(merged[repair.faulty])
                    continue
            out.append(group)
        return out
    except Exception as error:  # noqa: BLE001 - each ruling its own cause, as before
        degraded("contested_tests.by_shared_expression", error)
        return groups


#: A line that checks something, in the runners' common words: such a line must be the same in the corrected copy.
_A_CHECK = re.compile(r"\b(?:assert\w*|expect\w*|should\w*|verify\w*|t\.(?:Error|Fatal|Fail)\w*|require\.\w+)", re.I)
#: What a correction may not bring in that its quoted code did not have: a check, a skip, an exit, a branch, a comment.
_NOT_A_PLAIN_CHANGE = re.compile(
    r"\b(?:assert\w*|expect\w*|should\w*|verify\w*|skip\w*|xfail|only|todo|fixme|pending|ignore\w*|disabled?|"
    r"return|yield|raise|throw|exit|quit|abort|panic|pass|try|catch|except|finally|if|else|unless|mock\w*|"
    r"patch\w*|stub\w*|fake\w*)\b|#|//|/\*|\*/|--|;", re.I)


def _why_not_a_plain_change(original: str, corrected: str, repair: Repair) -> str:
    """Why the correction may change what the test checks, or "" when it changes only the quoted code."""
    brought = {m.group(0).lower() for m in _NOT_A_PLAIN_CHANGE.finditer(repair.corrected)}
    had = {m.group(0).lower() for m in _NOT_A_PLAIN_CHANGE.finditer(repair.faulty)}
    if brought - had:
        return f"the correction brings in {', '.join(sorted(brought - had))}"
    before = [line.strip() for line in original.splitlines() if _A_CHECK.search(line)]
    after = [line.strip() for line in corrected.splitlines() if _A_CHECK.search(line)]
    if not before:
        return "the test's file has no line that checks anything"
    if before != after:
        return "the correction changes a line that checks something"
    return ""


def _the_record(root: Any) -> dict[str, Any]:
    from app.stacks import contract

    return contract.read(root) or {}


def _the_product(root: Any) -> tuple[Path, set[str]] | None:
    """The product's directory and the runner files the harness keeps, or None."""
    from app.stacks import contract

    found = contract.the_pack(root)
    if found is None:
        return None
    pack, record = found
    return Path(root) / str(record.get("project") or ""), set(pack.kept_files)


#: A string literal of a test, which the product files it reaches tend to hold too (a path, a header, a field).
_A_LITERAL = re.compile(r"""["'`]([^"'`\n]{3,80})["'`]""")


def _mutants(root: Any, test_text: str) -> tuple[Path | None, list[dict]]:
    """Deliberate changes to the product files most like the test: those holding the most of its string literals."""
    from app.acceptance import mutation

    product = _the_product(root)
    if product is None:
        return None, []
    project, kept = product
    files = mutation.source_files(project, kept)
    literals = {lit for lit in _A_LITERAL.findall(test_text) if lit.strip()}

    def held(path: Path) -> int:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return 0
        return sum(1 for lit in literals if lit in text)

    scored = sorted(((held(path), str(path), path) for path in files), key=lambda item: (-item[0], item[1]))
    nearest = [path for score, _, path in scored if score > 0][:3] or [path for _, _, path in scored]
    return project, mutation.spread(mutation.sites(nearest, project), MOST_MUTANTS)


def _a_copy_name(path: Path, pattern: str, text: str) -> str | None:
    """A name for the corrected copy that the suite's file pattern still selects, or None."""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    head, dot, rest = path.name.partition(".")
    for name in (f"{head}_{COPY_MARK}_{digest}{dot}{rest}", f"{COPY_MARK}_{digest}_{path.name}"):
        if fnmatch.fnmatch(name, pattern or "*"):
            return name
    return None


def _remove_left_copies(base: Path) -> None:
    for path in base.rglob(f"*{COPY_MARK}*"):
        if path.is_file() and "node_modules" not in path.parts:
            path.unlink(missing_ok=True)


class _Run:
    """One file of the suite run alone in the project's runner, read test by test from its report."""

    def __init__(self, root: Any, record: dict[str, Any], run: Runner) -> None:
        self.root = Path(root)
        self.project = str(record.get("project") or "")
        self.directory = str(record.get("acceptance_dir") or "")
        self.pattern = str(record.get("acceptance_pattern") or "*")
        self.argv = list(record.get("acceptance_test") or [])
        report = record.get("acceptance_report")
        self.report = self.root / self.project / str(report) if report else None
        self.run = run
        self.used = 0

    def outcomes(self, path: Path, tests: Sequence[str]) -> tuple[dict[str, str], str]:
        """Each of `tests` as this run of `path` reported it ("passed", "failed", "skipped" or "" for unreported)."""
        from app.acceptance import junit
        from app.acceptance.per_file import _the_command_for

        relative = path.relative_to(self.root / self.project).as_posix()
        if self.report is not None:
            junit.clear(self.report)
        self.used += 1
        outcome = self.run(_the_command_for(self.argv, relative, self.directory, self.pattern), "probe",
                           self.project) or {}
        output = "".join(str(outcome.get(key) or "") for key in ("stdout", "stderr", "error"))
        reported = junit.read(self.report).tests if self.report is not None else []
        found = {}
        for test in tests:
            hit = next((t for t in reported if _the_same_test(t.name, test)), None)
            found[test] = hit.outcome if hit is not None else ""
        return found, output


def _the_file_of(test: str, files: dict[Path, str]) -> Path | None:
    """The one suite file holding both the quoted code and the test's own title, or None."""
    short = re.sub(r"\[[^\]]*\]$", "", _short(test)).strip()
    holding = [path for path, text in files.items() if short and short in text]
    return holding[0] if len(holding) == 1 else None


def _confirm_in_file(runs: _Run, path: Path, tests: list[str], repair: Repair, root: Any) -> str:
    """Why the repair is not confirmed for `tests` in `path`, or "" when every leg holds."""
    from app.acceptance import mutation
    from app.acceptance.per_file import _put_back, _the_report_as_it_is
    from app.acceptance.suite import the_product_did_not_start

    original = path.read_text(encoding="utf-8", errors="replace")
    corrected = original.replace(repair.faulty, repair.corrected)
    if why := _why_not_a_plain_change(original, corrected, repair):
        return why
    name = _a_copy_name(path, runs.pattern, corrected)
    if name is None:
        return "no name for a copy that the suite's runner would select"
    copy = path.with_name(name)
    kept = _the_report_as_it_is(runs.report)
    try:
        found, _ = runs.outcomes(path, tests)
        if any(found[test] != "failed" for test in tests):
            return "the locked test does not fail when its file runs alone"
        copy.write_text(corrected, encoding="utf-8")
        found, _ = runs.outcomes(copy, tests)
        if any(found[test] != "passed" for test in tests):
            return "the corrected copy does not pass against the product as it is"
        project, sites = _mutants(root, corrected)
        killed: set[str] = set()
        for site in sites:
            if runs.used >= MOST_RUNS:
                break
            before = mutation._journal_before_changing(runs.root, project, site)  # noqa: SLF001 - its own journal
            try:
                found, output = runs.outcomes(copy, tests)
            finally:
                mutation._restore_and_close_the_journal(runs.root, project / site["file"], before)  # noqa: SLF001
            if the_product_did_not_start(output):
                continue
            killed |= {test for test in tests if found[test] == "failed"}
            if killed == set(tests):
                return ""
        return "the corrected copy still passes against a deliberately broken product"
    finally:
        copy.unlink(missing_ok=True)
        _put_back(runs.report, kept)


def confirm(root: Any, tests: list[str], repair: Repair, runs: _Run) -> str:
    """Why `repair` is not confirmed for `tests`, or "" when the harness confirmed it. Never raises."""
    from app.acceptance import mutation, suite

    try:
        if not runs.argv or runs.report is None:
            return "the suite's runner cannot be asked for one file and its report"
        if not _code_like(repair.faulty):
            return "the quoted code is not code"
        files = {}
        for path in suite.suite_files(root):
            text = path.read_text(encoding="utf-8", errors="replace")
            if repair.faulty in text:
                files[path] = text
        if not files:
            return "the quoted code is not in the locked suite"
        by_file: dict[Path, list[str]] = {}
        for test in tests:
            path = _the_file_of(test, files)
            if path is None:
                return f"no one file of the suite holds both `{test}` and the quoted code"
            by_file.setdefault(path, []).append(test)
        mutation.restore_an_interrupted_probe(root)
        for path, here in by_file.items():
            if runs.used + 3 > MOST_RUNS:
                return "too many runs to confirm in one dispute"
            if why := _confirm_in_file(runs, path, here, repair, root):
                return why
        return ""
    except Exception as error:  # noqa: BLE001 - unknown is not confirmed
        degraded("contested_tests.confirm", error)
        return "the confirmation could not run"


def with_the_confirmation(line: str, repair: Repair) -> str:
    """A ruling's repair line with what the harness confirmed, for QA's repair."""
    return (
        f"{line} {SAYS} `{repair.faulty}` changed to `{repair.corrected}`, its checks unchanged: the locked test "
        "failed against the product as it is, the copy passed, and the copy failed against a deliberately broken "
        "product. Change the locked test the same way, keeping every check it makes."
    )


def confirmed_past_the_cap(
    root: Any, groups: list[list[str]], past_the_cap: list[str], repairs: Sequence[Repair], *, run: Runner | None = None,
) -> tuple[list[str], list[str], int, list[tuple[str, str]]]:
    """(the confirmed repair lines, the rulings still past the cap, how many causes were confirmed, (test, why) refuted).

    Each group past the cap is confirmed as one: every ruling in it must propose the same repair. Never raises; on
    any doubt every ruling stays past the cap.
    """
    try:
        past = set(past_the_cap)
        candidates = [group for group in groups if isinstance(group, list) and group and all(r in past for r in group)]
        if not candidates or not repairs:
            return [], list(past_the_cap), 0, []
        from app.acceptance import suite

        base = suite.directory(root)
        if base is not None and base.is_dir():
            _remove_left_copies(base)
        if run is None:
            from app.stacks.scaffold import sandbox_runner

            run = sandbox_runner(root)
        runs = _Run(root, _the_record(root), run)
        confirmed: list[str] = []
        done: set[str] = set()
        refuted: list[tuple[str, str]] = []
        causes = 0
        for group in candidates:
            found = [repair_for(line, repairs) for line in group]
            if any(repair is None for repair in found) or len({(r.faulty, r.corrected) for r in found}) != 1:
                refuted.extend((_test_of(line), "no one repair proposed for its cause") for line in group)
                continue
            repair = found[0]
            why = confirm(root, [_test_of(line) for line in group], repair, runs)
            if why:
                logger.warning("A ruling past the cap on %s is not confirmed: %s; it stays locked",
                               ", ".join(_test_of(line) for line in group), why)
                refuted.extend((_test_of(line), why) for line in group)
                continue
            logger.warning("The harness confirmed the ruling past the cap on %s", ", ".join(map(_test_of, group)))
            confirmed.extend(with_the_confirmation(line, repair) for line in group)
            done.update(group)
            causes += 1
        return confirmed, [line for line in past_the_cap if line not in done], causes, refuted
    except Exception as error:  # noqa: BLE001 - every ruling stays past the cap, as before
        degraded("contested_tests.confirmed_past_the_cap", error)
        return [], list(past_the_cap), 0, []


__all__ = [
    "COPY_MARK", "MOST_MUTANTS", "MOST_RUNS", "ON_BY_DEFAULT", "Repair", "SAYS", "by_shared_expression", "confirm",
    "confirmed_past_the_cap", "enabled", "explanation", "proposed_repairs", "repair_for", "with_the_confirmation",
]
