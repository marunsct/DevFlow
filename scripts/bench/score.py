"""Score a product against a benchmark's hidden acceptance tests.

Runs inside the worker (it has Node, Chromium and Python):

    python score.py <product dir> <benchmark dir> <result.json>

The hidden tests were written by a person from the benchmark's brief and are
never shown to the harness. They reach the product only through the interface
the brief states - labelled controls on a page, endpoints of a service started
by its `start.sh`, a module run with `python -m`, a package imported by name -
so any implementation of the brief can pass them.

`<benchmark dir>/bench.json` says how:

    {"kind": "browser_app" | "fullstack" | "http_api" | "cli" | "library",
     "runner": "playwright" | "pytest",
     "module": "<python module, for cli and library>"}

The result is JSON: totals, the score (passed / total), and every test - and
beside them what the harness itself concluded (`harness`): the run's status
and what its release knew it did not prove (`completion_gaps`), both passed to
this script by `loop.sh score`, and its locked acceptance suite's last
result. A run the harness finished while its product fails hidden tests
is a *false acceptance* (`false_acceptance`), the number that says how far the
harness's own "done" can be trusted. `report.py` totals them across runs.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

RUNNERS = Path(os.environ.get("BENCH_RUNNERS", "/tmp/bench-runners"))
PLAYWRIGHT = "1.64.0"


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _run(argv: list[str], cwd: Path, env: dict | None = None, timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(argv, cwd=cwd, env={**os.environ, **(env or {})}, capture_output=True, text=True, timeout=timeout)


def _node_runner() -> Path:
    home = RUNNERS / "node"
    if not (home / "node_modules" / "@playwright" / "test").is_dir():
        home.mkdir(parents=True, exist_ok=True)
        (home / "package.json").write_text(json.dumps({
            "name": "bench-runner", "private": True, "type": "module",
            "devDependencies": {"@playwright/test": PLAYWRIGHT},
        }))
        _run(["npm", "install", "--no-audit", "--no-fund"], home)
    return home


def _python_runner() -> Path:
    """The runner's interpreter, with pytest and httpx importable.

    Ready only when they import, not when the interpreter exists: an install
    cut off part-way (a scoring command whose output pipe closed early) left
    the interpreter without pytest, every later score reused it, and a run
    whose product passed its suite was scored 0/10 as a false acceptance.
    """
    home = RUNNERS / "py"
    python = home / "bin" / "python"
    if not python.exists():
        _run([sys.executable, "-m", "venv", str(home)], RUNNERS if RUNNERS.exists() else Path("/tmp"))
    if _run([str(python), "-c", "import pytest, httpx"], home).returncode != 0:
        _run([str(python), "-m", "pip", "install", "--quiet", "pytest", "httpx"], home)
    return python


def _browser_root(product: Path, notes: list[str]) -> Path:
    """The directory to serve for a page: a build's output when the product has a build."""
    manifest = product / "package.json"
    if manifest.is_file():
        try:
            scripts = json.loads(manifest.read_text()).get("scripts", {})
        except ValueError:
            scripts = {}
        if "build" in scripts:
            if not (product / "node_modules").is_dir():
                _run(["npm", "install", "--no-audit", "--no-fund"], product)
            built = _run(["npm", "run", "build"], product)
            if built.returncode != 0:
                notes.append("npm run build failed: " + (built.stdout + built.stderr)[-500:])
            for candidate in ("dist", "build"):
                if (product / candidate / "index.html").is_file():
                    return product / candidate
    return product


def _junit(path: Path) -> list[dict]:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return []
    tests = []
    for case in root.iter("testcase"):
        outcome, message = "passed", ""
        for child in case:
            if child.tag in {"failure", "error"}:
                outcome, message = "failed", (child.get("message") or child.text or "")[:400]
            elif child.tag == "skipped":
                outcome = "skipped"
        tests.append({"name": case.get("name", ""), "outcome": outcome, "message": message})
    return tests


def harness_verdict(product: Path, status: str = "", completion_gaps: list[str] | None = None) -> dict:
    """What the harness concluded about this product: its run status, what the
    release knew it did not prove, and its locked suite result."""
    verdict: dict = {
        "status": status or "unknown",
        "completion_gaps": [str(gap) for gap in completion_gaps or []],
    }
    try:
        locked = json.loads((product.parent / ".harness" / "acceptance-result.json").read_text())
    except (OSError, ValueError):
        return verdict
    criteria = locked.get("criteria") or {}
    verdict.update({
        "locked_passed": int(locked.get("passed") or 0),
        "locked_failed": int(locked.get("failed") or 0),
        "criteria_passed": sum(1 for c in criteria.values() if c.get("status") == "passed"),
        "criteria_deferred": sum(1 for c in criteria.values() if c.get("status") == "deferred"),
        "criteria": len(criteria),
    })
    return verdict


def brief_pairing(own_brief: str) -> dict:
    """Whether the run was started from this benchmark's own brief: `yes`, `no` or unknown.

    The hidden tests are written against the benchmark's own brief - its
    interface section names what they find. A run started from another brief
    and scored here measures the pairing, not the harness: three runs given a
    shorter brief scored 1, 1 and 5 of 10 here while the one given the real
    brief scored 10. Such a score is kept, marked, and never counted as a false
    acceptance.
    """
    # "yes" or "no", optionally with how alike the briefs were: "yes:0.998".
    answer, _, ratio = (own_brief or "").strip().lower().partition(":")
    found = {
        "brief": {"yes": "own", "no": "other"}.get(answer, "unknown"),
        "brief_mismatch": answer == "no",
    }
    try:
        found["brief_similarity"] = float(ratio)
    except ValueError:
        pass
    return found


def _the_quality_set(bench: Path, work: Path, runner: str, env: dict, notes: list[str]) -> list[dict] | None:
    """The benchmark's quality tests (`<bench>/quality`), run beside the hidden ones; None when it has none.

    The hidden tests check that the product does what the brief says; on a
    benchmark every run now passes, they no longer tell one product from a
    better one. The quality set holds the same brief to its edges.
    """
    if not (bench / "quality").is_dir() or runner == "playwright":
        return None
    shutil.copytree(bench / "quality", work / "quality")
    if not (work / "quality" / "conftest.py").exists() and (bench / "hidden" / "conftest.py").exists():
        shutil.copy(bench / "hidden" / "conftest.py", work / "quality" / "conftest.py")
    report = work / "quality.xml"
    data = work / "quality-data"
    data.mkdir(exist_ok=True)
    ran = _run([str(_python_runner()), "-m", "pytest", str(work / "quality"), "-q", f"--junitxml={report}",
                "-p", "no:cacheprovider"], work, {**env, "DATA_DIR": str(data)}, timeout=1200)
    found = _junit(report)
    if not found:
        notes.append("the quality tests produced no report: " + (ran.stdout + ran.stderr)[-800:])
    return found


def score(
    product: Path, bench: Path, out: Path, status: str = "", completion_gaps: list[str] | None = None,
    own_brief: str = "",
) -> dict:
    spec = json.loads((bench / "bench.json").read_text())
    kind, runner = spec["kind"], spec["runner"]
    notes: list[str] = []
    work = Path(f"/tmp/bench-work/{bench.name}-{int(time.time())}")
    shutil.copytree(product, work / "product", symlinks=True)
    shutil.copytree(bench / "hidden", work / "hidden")
    target = work / "product"
    report = work / "report.xml"
    data_dir = work / "data"
    data_dir.mkdir(parents=True)

    if runner == "playwright":
        home = _node_runner()
        port = _free_port()
        if kind == "browser_app":
            served = _browser_root(target, notes)
            server = f"{sys.executable} -m http.server {port} --bind 127.0.0.1 --directory {served}"
        else:
            if not (target / "start.sh").is_file():
                notes.append("no start.sh: the brief requires one")
            server = f"cd {target} && PORT={port} DATA_DIR={data_dir} sh start.sh"
        config = work / "playwright.config.mjs"
        config.write_text(
            "export default {\n"
            f"  testDir: {json.dumps(str(work / 'hidden'))},\n"
            "  timeout: 30000, workers: 1, retries: 0,\n"
            f"  reporter: [['list'], ['junit', {{ outputFile: {json.dumps(str(report))} }}]],\n"
            f"  outputDir: {json.dumps(str(work / 'results'))},\n"
            f"  use: {{ baseURL: 'http://127.0.0.1:{port}' }},\n"
            f"  webServer: {{ command: {json.dumps(server)}, url: 'http://127.0.0.1:{port}/', "
            "reuseExistingServer: false, timeout: 60000, ignoreHTTPSErrors: true },\n"
            "};\n"
        )
        # Hidden specs import @playwright/test from the runner's install.
        (work / "hidden" / "node_modules").symlink_to(home / "node_modules")
        ran = _run(["npx", "playwright", "test", "-c", str(config)], home, timeout=1200)
    else:
        python = _python_runner()
        env = {
            "PRODUCT_DIR": str(target),
            "DATA_DIR": str(data_dir),
            "BENCH_MODULE": str(spec.get("module", "")),
        }
        if kind == "library":
            env["PYTHONPATH"] = str(target)
        ran = _run([str(python), "-m", "pytest", str(work / "hidden"), "-q", f"--junitxml={report}", "-p", "no:cacheprovider"], work, env, timeout=1200)
    tests = _junit(report)
    if not tests:
        notes.append("the hidden tests produced no report: " + (ran.stdout + ran.stderr)[-1500:])
    quality = _the_quality_set(bench, work, runner, env if runner != "playwright" else {}, notes)
    passed = sum(t["outcome"] == "passed" for t in tests)
    total = len(tests) or int(spec.get("tests", 0))
    result = {
        "benchmark": bench.name,
        "product": str(product),
        "passed": passed,
        "failed": sum(t["outcome"] == "failed" for t in tests),
        "total": total,
        "score": round(passed / total, 3) if total else 0.0,
        "tests": tests,
        "notes": notes,
    }
    if quality is not None:
        # Apart from the headline score, which stays comparable across runs.
        result["quality_passed"] = sum(t["outcome"] == "passed" for t in quality)
        result["quality_total"] = len(quality)
        result["quality_tests"] = quality
    result["harness"] = harness_verdict(product, status, completion_gaps)
    result.update(brief_pairing(own_brief))
    # No report means the tests never ran - a broken runner, not a broken
    # product. Scored 0 it read as a false acceptance and went into the KPI
    # ledger as one; unscored, it says what happened and is left out.
    result["unscored"] = not tests
    if result["unscored"]:
        result["score"] = None
    result["false_acceptance"] = (
        not result["unscored"] and result["harness"]["status"] == "completed"
        and result["score"] < 1.0 and not result["brief_mismatch"]
    )
    # What the release knew it did not prove, top level as well: the outcome
    # dashboard and `report.py` read the export without walking `harness`.
    result["completion_gaps"] = result["harness"]["completion_gaps"]
    out.write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    product, bench, out = (Path(a) for a in sys.argv[1:4])
    gaps: list[str] = []
    if len(sys.argv) > 5 and sys.argv[5].strip():
        try:
            parsed = json.loads(sys.argv[5])
            gaps = [str(gap) for gap in parsed] if isinstance(parsed, list) else []
        except ValueError:
            gaps = []
    result = score(
        product, bench, out, sys.argv[4] if len(sys.argv) > 4 else "", gaps, sys.argv[6] if len(sys.argv) > 6 else "",
    )
    if result["unscored"]:
        print(f"{result['benchmark']}: UNSCORED - the hidden tests produced no report; see the notes below")
    else:
        print(f"{result['benchmark']}: {result['passed']}/{result['total']} hidden tests pass (score {result['score']})")
    if "quality_total" in result:
        print(f"  quality: {result['quality_passed']}/{result['quality_total']} of the brief's edges held")
    if result["brief_mismatch"]:
        print("  BRIEF MISMATCH: the run was not started from this benchmark's brief; not a false acceptance")
    harness = result["harness"]
    print(
        f"  harness: run {harness['status']}, locked suite {harness.get('locked_passed', '?')} passed / "
        f"{harness.get('locked_failed', '?')} failed"
        + ("  <- FALSE ACCEPTANCE: the harness finished a product that fails hidden tests" if result["false_acceptance"] else "")
    )
    if result["completion_gaps"]:
        print(f"  completed with {len(result['completion_gaps'])} gap(s) the release knew it did not prove:")
        for gap in result["completion_gaps"]:
            print(f"    - {gap[:300]}")
    for test in result["tests"]:
        if test["outcome"] != "passed":
            print(f"  FAIL {test['name']}: {test['message'][:200]}")
    for note in result["notes"]:
        print(f"  note: {note[:600]}")
