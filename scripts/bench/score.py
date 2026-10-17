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
    home = RUNNERS / "py"
    python = home / "bin" / "python"
    if not python.exists():
        _run([sys.executable, "-m", "venv", str(home)], RUNNERS if RUNNERS.exists() else Path("/tmp"))
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


def score(product: Path, bench: Path, out: Path, status: str = "", completion_gaps: list[str] | None = None) -> dict:
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
    result["harness"] = harness_verdict(product, status, completion_gaps)
    result["false_acceptance"] = result["harness"]["status"] == "completed" and result["score"] < 1.0
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
    result = score(product, bench, out, sys.argv[4] if len(sys.argv) > 4 else "", gaps)
    print(f"{result['benchmark']}: {result['passed']}/{result['total']} hidden tests pass (score {result['score']})")
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
