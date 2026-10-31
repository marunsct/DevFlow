"""At a suite's first green round, each of its files is run alone, last file first; a test failing only then is recorded (plan item 20, behind `ORDER_PROBE`).

`unstable.py` catches a criterion that fails in the whole suite and passes alone, after the fact, once fixers have been
sent: measured on a gate run, criteria were raised, closed and raised again on one product across three attempts. The
opposite shape is never seen at all: a test that passes only because an earlier file left data behind stays green until
a repair or a new sprint changes what runs before it, and is then charged to the product.

Runners differ in what they let a caller reorder (some sort the files they are given), so the probe uses what every
runner the packs declare can do: run one file. A run of one file on its own starts from an empty product, which is the
order with nothing before it. It cannot see a dependency between two tests of one file, so a suite of one file is not
probed. It only records, for the measure of unstable disputes per run: no verdict and no request changes.
"""

from __future__ import annotations

import fnmatch
import json
import logging
from pathlib import Path
from typing import Any, Callable, Sequence

from app.switches import is_on

logger = logging.getLogger(__name__)

#: `ORDER_PROBE` set to on or off overrides this.
ON_BY_DEFAULT = False
#: Where the result is kept, relative to the workspace.
FILE = ".harness/order_probe.json"
MOST_FILES = 40
MOST_MESSAGE_CHARACTERS = 300

Runner = Callable[[Sequence[str], str, str], dict[str, Any]]


def enabled() -> bool:
    return is_on("ORDER_PROBE", ON_BY_DEFAULT)


def _the_suite_s_files(base: Path, pattern: str) -> list[Path]:
    from app.analysis.walk import files_under

    return sorted(p for p in files_under(base, ("node_modules",)) if fnmatch.fnmatch(p.name, pattern))


def probe(repo_root: str | Path, record: dict[str, Any], run: Runner) -> dict[str, Any]:
    """{files_run, files_without_a_report, unstable: [{file, test, message}]}; the suite's own report is left as it was."""
    from app.acceptance import junit, per_file

    project = str(record.get("project") or "")
    directory = str(record.get("acceptance_dir") or "")
    pattern = str(record.get("acceptance_pattern") or "*")
    argv = list(record.get("acceptance_test") or [])
    named_report = str(record.get("acceptance_report") or "")
    base = Path(repo_root) / project / directory
    if not argv or not named_report or not base.is_dir():
        return {}
    files = _the_suite_s_files(base, pattern)
    if len(files) < 2:
        return {}
    report = Path(repo_root) / project / named_report
    kept = per_file._the_report_as_it_is(report)  # noqa: SLF001 - the same protection the per-file runs need
    found: dict[str, Any] = {"files_run": 0, "files_without_a_report": 0, "unstable": []}
    try:
        for path in reversed(files[-MOST_FILES:]):
            relative = path.relative_to(Path(repo_root) / project).as_posix()
            junit.clear(report)
            run(per_file._the_command_for(argv, relative, directory, pattern), "probe", project)  # noqa: SLF001
            measured = junit.read(report)
            if not measured.found or not measured.tests:
                # A runner that takes no file, or a run stopped short, says nothing about order.
                found["files_without_a_report"] += 1
                continue
            found["files_run"] += 1
            found["unstable"].extend(
                {"file": relative, "test": test.name, "message": str(test.message or "")[:MOST_MESSAGE_CHARACTERS]}
                for test in measured.tests if test.outcome == "failed"
            )
    finally:
        per_file._put_back(report, kept)  # noqa: SLF001
    return found


def at_a_green_round(repo_root: str | Path, run: Runner | None = None) -> dict[str, Any]:
    """Probe once for each locked suite, at the first green round that sees it; {} when off or already done. Never raises."""
    try:
        if not enabled():
            return {}
        from app.acceptance import suite
        from app.stacks import contract

        root = Path(repo_root)
        record = contract.read(root) or {}
        if not record or not suite.is_locked(root):
            return {}
        identity = _digest(suite.suite_files(root))
        path = root / FILE
        if path.is_file() and json.loads(path.read_text(encoding="utf-8")).get("suite") == identity:
            return {}
        found = probe(root, record, run or suite._sandbox_runner(root))  # noqa: SLF001
        if not found:
            return {}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"suite": identity, **found}, indent=1) + "\n", encoding="utf-8")
        if found["unstable"]:
            logger.warning("%d test(s) of a green suite fail when their file runs alone", len(found["unstable"]))
        return found
    except Exception:  # noqa: BLE001 - a probe never costs the round
        logger.debug("The order probe did not run", exc_info=True)
        return {}


def _digest(files: list[Path]) -> str:
    import hashlib

    digest = hashlib.sha256()
    for path in files:
        try:
            digest.update(path.name.encode() + b"\0" + path.read_bytes())
        except OSError:
            continue
    return digest.hexdigest()[:20]


__all__ = ["FILE", "ON_BY_DEFAULT", "at_a_green_round", "enabled", "probe"]
