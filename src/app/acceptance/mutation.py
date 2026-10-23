"""How strong is the locked suite? Break the product on purpose and see whether it notices.

Plan item AF (owner decision 2026-10-18). A suite that passes says the product
does what the tests check; it does not say the tests check much. One run's
suite passed 8 of 9 while the product scored 2 of 10 on the hidden tests.

A small textual change to the product's own source - a comparison turned
round, a condition flipped, a constant moved by one - and the suite run the way
the harness runs it. A change no test notices is a behaviour no test holds the
product to.

Where it runs: at release, when criteria pass. The suite is locked against the
scaffold, before anything is built, so at lock time every test fails and no
change could be noticed. The owner's budget: about three changes, and only for
a suite that drives no browser - such a suite runs in seconds, a browser round
in minutes. A change can be equivalent (behave the same), so a survivor is
evidence to read, not proof; the finding is a completion gap, never a block.

`scripts/bench/mutate.py` is the offline version for the loop, over more changes.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: Changes tried at release (owner's budget).
CHANGES_AT_RELEASE = 3

#: Pack kinds whose suite drives a browser, which the release budget leaves out.
BROWSER_KINDS = frozenset({"browser_app", "fullstack"})

#: (pattern, replacement) pairs. Order matters only for reporting.
OPERATORS: list[tuple[str, str]] = [
    (r"===", "!=="),
    (r"!==", "==="),
    (r"(?<![=!<>])==(?!=)", "!="),
    (r"(?<![=!])!=(?!=)", "=="),
    (r"&&", "||"),
    (r"\|\|", "&&"),
    (r"\band\b", "or"),
    (r"\bor\b", "and"),
    (r"\btrue\b", "false"),
    (r"\bfalse\b", "true"),
    (r"\bTrue\b", "False"),
    (r"\bFalse\b", "True"),
    (r">=", "<"),
    (r"<=", ">"),
    (r"(?<![-=>])>(?![=>])", "<="),
    (r"(?<![<=-])<(?![=<])", ">="),
    (r"\+ 1\b", "- 1"),
    (r"- 1\b", "+ 1"),
]

#: Source a product's behaviour lives in.
SOURCE_SUFFIXES = {".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".py", ".rb", ".go", ".java", ".php"}

#: Directories that are not the product's own source.
SKIPPED_PARTS = {"node_modules", "dist", "build", "coverage", "__pycache__", ".venv", "venv", ".harness",
                 "tests", "test", "__tests__", "e2e", "acceptance", "docs", "public", "vendor"}

#: File names that are tests or configuration, not behaviour.
SKIPPED_NAME = re.compile(r"(\.test\.|\.spec\.|^test_|_test\.|\.config\.|^conftest\.py$|^setup\.py$)")


def source_files(project: Path, kept: set[str] | frozenset[str] = frozenset()) -> list[Path]:
    """The product's own source: not tests, not configuration, not the harness's kept files.

    `kept` are the pack's runner files (relative to the project), which the
    harness puts back before every suite run - a change there is undone
    before any test sees it.
    """
    from app.analysis.walk import files_under

    files = []
    for path in sorted(files_under(project, SKIPPED_PARTS, skip_hidden=True)):
        relative = path.relative_to(project)
        if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
            continue
        if relative.as_posix() in kept:
            continue
        if any(part in SKIPPED_PARTS or part.startswith(".") for part in relative.parts[:-1]):
            continue
        if SKIPPED_NAME.search(path.name):
            continue
        files.append(path)
    return files


def _in_comment_or_string(line: str, column: int) -> bool:
    before = line[:column]
    stripped = before.lstrip()
    if stripped.startswith(("//", "#", "*", "/*")) or "//" in before or " #" in before:
        return True
    return any(before.count(quote) % 2 for quote in ("'", '"', "`"))


def _lines_that_are_not_code(lines: list[str], suffix: str) -> set[int]:
    """The 1-based numbers of lines inside a docstring or a block comment.

    A break there changes nothing the product does, so the suite cannot notice
    it, and the probe reported that as a gap (Initiative AL).
    """
    inside: set[int] = set()
    if suffix == ".py":
        opener = None
        for number, line in enumerate(lines, start=1):
            text = line
            while True:
                if opener is None:
                    positions = [(text.find(q), q) for q in ('"""', "'''") if q in text]
                    if not positions:
                        break
                    at, quote = min(positions)
                    opener = quote
                    inside.add(number)
                    text = text[at + 3:]
                else:
                    inside.add(number)
                    end = text.find(opener)
                    if end == -1:
                        break
                    text = text[end + 3:]
                    opener = None
        return inside
    in_block = False
    for number, line in enumerate(lines, start=1):
        text = line
        if in_block:
            inside.add(number)
            end = text.find("*/")
            if end == -1:
                continue
            in_block, text = False, text[end + 2:]
        start = text.find("/*")
        if start != -1 and "*/" not in text[start + 2:]:
            in_block = True
            inside.add(number)
    return inside


def sites(files: list[Path], project: Path) -> list[dict]:
    """Every place an operator applies: file, line, column, the text it replaces and its replacement."""
    found = []
    for path in files:
        try:
            lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        except (OSError, UnicodeDecodeError):
            continue
        not_code = _lines_that_are_not_code(lines, path.suffix)
        for number, line in enumerate(lines, start=1):
            if number in not_code or line.lstrip().startswith(("import ", "from ", "export {", "require(")):
                continue
            for pattern, replacement in OPERATORS:
                for match in re.finditer(pattern, line):
                    if _in_comment_or_string(line, match.start()):
                        continue
                    found.append({
                        "file": str(path.relative_to(project)), "line": number, "column": match.start(),
                        "original": match.group(0), "replacement": replacement,
                    })
    return found


def spread(candidates: list[dict], count: int) -> list[dict]:
    """`count` sites spread evenly over the list, so every file gets its share."""
    if len(candidates) <= count:
        return candidates
    step = len(candidates) / count
    return [candidates[int(i * step)] for i in range(count)]


def apply(project: Path, site: dict) -> bytes:
    """Make the change in place; return the file's original bytes.

    Bytes both ways: reading as text turned a CRLF file into an LF one on the
    way back.
    """
    path = project / site["file"]
    original = path.read_bytes()
    lines = original.decode("utf-8").splitlines(keepends=True)
    line = lines[site["line"] - 1]
    column, length = site["column"], len(site["original"])
    lines[site["line"] - 1] = line[:column] + site["replacement"] + line[column + length:]
    path.write_bytes("".join(lines).encode("utf-8"))
    return original


#: Where a probe in progress is written down, and the bytes it will put back.
JOURNAL = ".harness/mutation-in-flight.json"
BACKUP = ".harness/mutation-backup"


def _journal_before_changing(root: Path, project: Path, site: dict) -> bytes:
    """Write down what is about to be changed, then change it; the original bytes.

    A process that dies between the change and the restore leaves a broken
    product that nothing else would notice. The journal and a byte copy are
    written first, so the next entry to the release puts the file back.
    """
    import hashlib
    import json

    path = project / site["file"]
    original = path.read_bytes()
    backup = root / BACKUP / hashlib.sha256(str(path).encode()).hexdigest()[:16]
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_bytes(original)
    (root / JOURNAL).write_text(json.dumps({
        "file": str(path.relative_to(root)),
        "sha256": hashlib.sha256(original).hexdigest(),
        "backup": str(backup.relative_to(root)),
    }), encoding="utf-8")
    apply(project, site)
    return original


def _restore_and_close_the_journal(root: Path, path: Path, original: bytes) -> None:
    import shutil

    path.write_bytes(original)
    (root / JOURNAL).unlink(missing_ok=True)
    shutil.rmtree(root / BACKUP, ignore_errors=True)


def restore_an_interrupted_probe(repo_root: str | Path) -> bool:
    """Put back a file a probe changed and did not restore; whether it did.

    Called when the release is entered: a worker that died mid-probe (a deploy,
    a crash) left the deliberate break in the workspace, and orphan recovery
    re-enters the release on the broken tree (Initiative AL).
    """
    import json

    root = Path(repo_root)
    journal = root / JOURNAL
    if not journal.is_file():
        return False
    try:
        note = json.loads(journal.read_text(encoding="utf-8"))
        original = (root / note["backup"]).read_bytes()
        _restore_and_close_the_journal(root, root / note["file"], original)
    except (OSError, ValueError, KeyError):
        logger.warning("A suite-strength probe was interrupted and could not be undone", exc_info=True)
        return False
    logger.warning("A suite-strength probe was interrupted; %s was put back as it was", note["file"])
    return True


def passing(result: Any) -> set[str]:
    """The names of the tests a suite result says passed."""
    report = getattr(result, "report", None)
    tests = getattr(report, "tests", None) or []
    return {getattr(t, "name", str(t)) for t in tests if getattr(t, "outcome", "") == "passed"}


def what_the_suite_does_not_notice(repo_root: str | Path, count: int = CHANGES_AT_RELEASE, *, run: Any = None) -> list[str]:
    """A completion gap for each deliberate change no locked test noticed; [] when none, or it cannot run.

    Changes the workspace in place, one at a time, and puts each file back
    before the next - the release is the run's last step, with nothing else
    writing. `run` is the suite runner, `app.acceptance.suite.run` by default.
    """
    try:
        from app.acceptance import suite
        from app.stacks import contract

        root = Path(repo_root)
        restore_an_interrupted_probe(root)
        found = contract.the_pack(root)
        if found is None or found[0].kind in BROWSER_KINDS or not suite.is_locked(root):
            return []
        run = run or (lambda: suite.run(root, save=False))
        project = root / str(found[1].get("project") or "")
        held = passing(run())
        if not held:
            return []
        chosen = spread(sites(source_files(project, set(found[0].kept_files)), project), count)
    except Exception:  # noqa: BLE001 - the release says nothing it cannot measure
        logger.debug("Could not probe the suite's strength", exc_info=True)
        return []
    gaps = []
    for site in chosen:
        original = _journal_before_changing(root, project, site)
        try:
            noticed = held - passing(run())
        except Exception:  # noqa: BLE001 - an unmeasured change is no finding
            logger.debug("A probe of the suite failed to run", exc_info=True)
            continue
        finally:
            _restore_and_close_the_journal(root, project / site["file"], original)
        if not noticed:
            gaps.append(
                f"The locked suite did not notice the product changed: `{site['file']}` line {site['line']}, "
                f"`{site['original']}` made `{site['replacement']}`, and every test that passed still passed. "
                "No test holds the product to that behaviour (or the change behaves the same)."
            )
    logger.info("Suite strength at release: %d of %d deliberate change(s) went unnoticed", len(gaps), len(chosen))
    return gaps
