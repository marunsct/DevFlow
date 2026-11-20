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
import uuid
from pathlib import Path

from app.switches import is_on
from app.tools.sandbox import product_environment

logger = logging.getLogger(__name__)

#: `SPEC_DRY_RUN` set to on or off overrides this; `SPEC_DRY_RUN_<PACK>` overrides that for one pack.
ON_BY_DEFAULT = False
RUNNER = Path(__file__).with_name("spec_dry_run.cjs")
#: The whole dry run's limit: a spec that spins past it keeps what was written before it.
LIMIT_SECONDS = 30
MOST_HEAP_MEGABYTES = 256
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


def run(directory: str | Path, *, limit_seconds: int = LIMIT_SECONDS, repo_root: str | Path | None = None) -> dict:
    """{files, tests, findings: [{file, line, test, error}], inconclusive: [...]} for this suite; {} when it cannot be run. Never raises.

    In container mode the specs run in a command's own container through the sandbox, never in the worker (deep
    review 2026-11-18, item E1a): they are the suite writer's code. That needs the run's workspace (`repo_root`) for
    the copy to be where the container sees it; without one, nothing runs there.
    """
    from app.tools.sandbox import product_code_runs_in_its_own_container

    base = Path(directory)
    contained = product_code_runs_in_its_own_container()
    node = "node" if contained else shutil.which("node")
    if node is None or not base.is_dir() or (contained and repo_root is None):
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
    named = [p.relative_to(base).as_posix() for p in specs]
    try:
        if contained:
            result = _run_in_its_container(Path(repo_root), base, named)
        else:
            result = _run_here(node, base, named, limit_seconds)
    except (OSError, ValueError, shutil.Error):
        logger.debug("Could not dry-run the suite", exc_info=True)
        return {}
    _cache[key] = result
    return result


def _run_here(node: str, base: Path, specs: list[str], limit_seconds: int) -> dict:
    """The dry run as a child of this process, on a copy in a temporary directory."""
    with tempfile.TemporaryDirectory(prefix="spec-dry-run-") as temporary:
        copy = Path(temporary).resolve() / "suite"
        shutil.copytree(base, copy, ignore=shutil.ignore_patterns("node_modules", "test-results"))
        report = Path(temporary).resolve() / "report.json"
        try:
            subprocess.run(  # noqa: S603 - our runner over a copy, with stand-ins for the network and child processes
                # A loop on a stand-in's always-truthy answer allocates until stopped: bounded in memory as in time.
                [node, f"--max-old-space-size={MOST_HEAP_MEGABYTES}", str(RUNNER), str(copy), str(report), *specs],
                cwd=copy, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                # The spec files are the suite writer's code: none of the worker's secrets reach them.
                env=product_environment(temporary), timeout=limit_seconds, check=False,
            )
        except subprocess.TimeoutExpired:
            logger.info("The dry run of a suite stopped at its limit of %d s", limit_seconds)
        return json.loads(report.read_text(encoding="utf-8")) if report.is_file() else {}


#: Where the copy, the runner and the report go in container mode, from the workspace root: a container sees only it.
_IN_THE_WORKSPACE = ".harness/spec-dry-run"


def _run_in_its_container(repo_root: Path, base: Path, specs: list[str]) -> dict:
    """The dry run through the sandbox (category `dry-run`, its own time limit), on a copy inside the workspace."""
    from app.tools.sandbox import SandboxExecutor

    place = repo_root / _IN_THE_WORKSPACE / uuid.uuid4().hex[:12]
    try:
        shutil.copytree(base, place / "suite", ignore=shutil.ignore_patterns("node_modules", "test-results"))
        shutil.copyfile(RUNNER, place / RUNNER.name)
        SandboxExecutor.execute(
            ["node", f"--max-old-space-size={MOST_HEAP_MEGABYTES}", RUNNER.name, "suite", "report.json", *specs],
            repo_root=str(repo_root), role_name="testing_specialist", category="dry-run",
            working_directory=place.relative_to(repo_root).as_posix(), for_the_harness=True,
        )
        report = place / "report.json"
        return json.loads(report.read_text(encoding="utf-8")) if report.is_file() else {}
    finally:
        shutil.rmtree(place, ignore_errors=True)


#: Errors the suite's own runner is known to raise, by a phrase of the message, and their cause. Measured on a C#
#: run: the writer declared `const __filename = fileURLToPath(import.meta.url)` in a spec; the runner compiles
#: `import.meta.url` to code that reads `__filename`, so the declaration read itself before it was set, and three
#: rounds of "correct that line" moved the line without changing the cause.
SUITE_KNOWN_ERRORS: dict[str, str] = {
    **{
        f"cannot access '{name}' before initialization": (
            f"the test runner compiles `import.meta.url` to code that reads `{name}`, so a spec that declares its own "
            f"`{name}` reads that name before it is set. Do not declare `__filename` or `__dirname` in a spec: name "
            "the variable something else (`specFile`, `specDir`), or reach files with `path.resolve(...)` from the "
            "project folder."
        )
        for name in ("__filename", "__dirname")
    },
}


def _with_its_cause(error: str) -> str:
    """` The cause: ...` for an error the suite's runner is known to raise, else ''."""
    lowered = error.lower()
    return next((f" The cause: {cause}" for phrase, cause in SUITE_KNOWN_ERRORS.items() if phrase in lowered), "")


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
            + _with_its_cause(str(item.get("error") or ""))
            for item in (run(directory, repo_root=repo_root).get("findings") or [])[:MOST_FINDINGS]
        ]
    except Exception:  # noqa: BLE001 - the other checks stand without this one
        logger.debug("The dry run's findings could not be read", exc_info=True)
        return []


__all__ = ["ON_BY_DEFAULT", "enabled", "findings", "run"]
