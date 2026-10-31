"""A dry run of a locked JavaScript suite: what its tests throw from their own code, with the product stood in for (plan item 18, behind `SPEC_DRY_RUN`).

`suite.tests_that_cannot_pass` holds regular expressions that read a test's text, and each new shape of a suite needed
a new one or an exception to an old one (`LF.289`, `300`, `302`, `328`, `329`, `333`...): a false "cannot pass" reopens
a right suite in a live run, and a shape nobody wrote a check for is charged to the product. Running the spec is the
oracle those checks approximate. `spec_dry_run.cjs` runs each spec with the runner, `request`, `page`, `fetch` and child
processes replaced by stand-ins that answer everything, and every assertion on a real matcher passing, so nothing the
product would decide can fail. What is left throws on every product: a name never defined, a matcher that does not
exist, a method called on the response that it does not have, the response's method compared instead of its result.

An error that could come from the stand-in's own answers (a thrown `Error`, a `JSON.parse` of its text, an index into a
list it returned as null) is counted as inconclusive, never as a finding. Replayed on the 30 stored locked suites,
each of which passed its hidden tests: see `tests/test_a_spec_dry_run_finds_what_throws_from_a_test_s_own_code.py`.

The regular expressions stay until a measurement says they can go. On a copy of the suite; node is only ever given the
copy, nothing starts, and no finding depends on the network.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.switches import is_on

logger = logging.getLogger(__name__)

#: `SPEC_DRY_RUN` set to on or off overrides this; `SPEC_DRY_RUN_<PACK>` overrides that for one pack.
ON_BY_DEFAULT = False
RUNNER = Path(__file__).with_name("spec_dry_run.cjs")
#: The whole dry run's limit: a spec that spins past it keeps what was written before it.
LIMIT_SECONDS = 60
MOST_FINDINGS = 6
_JAVASCRIPT = frozenset({".js", ".mjs", ".cjs", ".ts", ".mts", ".cts"})
_RUNNER_IMPORT = ("@playwright/test", "playwright/test")

_cache: dict[str, dict] = {}


def enabled(pack_name: str = "") -> bool:
    """Whether the dry run applies, for this pack when named: `SPEC_DRY_RUN_<PACK>` first, then `SPEC_DRY_RUN`."""
    default = is_on("SPEC_DRY_RUN", ON_BY_DEFAULT)
    if not pack_name:
        return default
    return is_on("SPEC_DRY_RUN_" + pack_name.upper().replace("-", "_"), default)


def _specs(directory: Path) -> list[Path]:
    """The suite's files that import the runner: a helper is run through the spec that uses it."""
    found = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _JAVASCRIPT or "node_modules" in path.parts:
            continue
        try:
            if any(name in path.read_text(encoding="utf-8", errors="replace") for name in _RUNNER_IMPORT):
                found.append(path)
        except OSError:
            continue
    return found


def run(directory: str | Path, *, limit_seconds: int = LIMIT_SECONDS) -> dict:
    """{files, tests, findings: [{file, line, test, error}], inconclusive: [...]} for this suite; {} when it cannot be run. Never raises."""
    base = Path(directory)
    node = shutil.which("node")
    if node is None or not base.is_dir():
        return {}
    specs = _specs(base)
    if not specs:
        return {}
    digest = hashlib.sha256()
    for path in sorted(p for p in base.rglob("*") if p.is_file() and "node_modules" not in p.parts):
        try:
            digest.update(path.relative_to(base).as_posix().encode() + b"\0" + path.read_bytes())
        except OSError:
            continue
    key = digest.hexdigest()
    if key in _cache:
        return _cache[key]
    try:
        with tempfile.TemporaryDirectory(prefix="spec-dry-run-") as temporary:
            copy = Path(temporary).resolve() / "suite"
            shutil.copytree(base, copy, ignore=shutil.ignore_patterns("node_modules", "test-results"))
            report = Path(temporary).resolve() / "report.json"
            try:
                subprocess.run(  # noqa: S603 - our runner over a copy, with stand-ins for the network and child processes
                    [node, str(RUNNER), str(copy), str(report), *[p.relative_to(base).as_posix() for p in specs]],
                    cwd=copy, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=limit_seconds, check=False,
                )
            except subprocess.TimeoutExpired:
                logger.info("The dry run of a suite stopped at its limit of %d s", limit_seconds)
            result = json.loads(report.read_text(encoding="utf-8")) if report.is_file() else {}
    except (OSError, ValueError, shutil.Error):
        logger.debug("Could not dry-run the suite", exc_info=True)
        return {}
    _cache[key] = result
    return result


def findings(repo_root: str | Path) -> list[str]:
    """One line per fault the dry run found in the locked suite; [] when off, or not a suite this runs. Never raises."""
    try:
        from app.acceptance import suite
        from app.stacks import contract

        found = contract.the_pack(repo_root)
        name = str(found[0].name) if found else ""
        if not enabled(name):
            return []
        directory = suite.directory(repo_root)
        if directory is None:
            return []
        shown = suite.relative_directory(repo_root)
        return [
            f"`{shown}/{item['file']}`" + (f" line {item['line']}" if item.get("line") else "")
            + f": the dry run of the suite, with the product replaced by a stand-in that answers everything and every "
            f"assertion passing, stopped at `{item['test'][:80]}` on `{item['error'][:200]}`. That is the test's own "
            "code: it fails the same way on every product, before the product's answer is looked at. Correct that line."
            for item in (run(directory).get("findings") or [])[:MOST_FINDINGS]
        ]
    except Exception:  # noqa: BLE001 - the other checks stand without this one
        logger.debug("The dry run's findings could not be read", exc_info=True)
        return []


__all__ = ["ON_BY_DEFAULT", "enabled", "findings", "run"]
