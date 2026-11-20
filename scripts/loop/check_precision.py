"""How often each cross-file check fires over stored products, and how often wrongly.

Run inside the worker, where the workspaces are:

    scripts/loop/loop.sh checks [labels.json]

For every workspace under the workspace root, every registered check is run and
its findings counted. With a labels file - {"<workspace name>": {"<check
name>": "false"}} marking findings a person has judged wrong - each check's
precision is printed too. A check that is not mechanical (see
`integration_checks._MECHANICAL`) and fires falsely is a hint at best; one that
is mechanical and fires falsely is a bug.

Prints one line per check, most-firing first, then the workspaces each flagged.

With `--write`, each check's precision is also measured without labels, from the
scored benchmark runs (`data/bench/<run>.json`): a check that called a product
broken when every hidden test of that product passed was wrong (Initiative
AO.5). The result goes to `data/loop/check_precision.json`, which
`integration_checks.checks_too_imprecise_to_block` reads: a check under 90% over
five or more scored products can no longer block.

`--write` also measures the acceptance suite's own checks (`.harness/check-findings.jsonl`, written by
`app.acceptance.check_findings`): a finding on a test that stayed in the suite as it was last locked, in a run that
scored full hidden marks, was wrong - the test it doubted judged a right product. A finding naming no test is not
counted. The result goes to `data/loop/suite_check_precision.json`; it is a report and nothing reads it.
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from app.analysis.integration_checks import _CHECKS, _MECHANICAL, _grade, _source_files

ROOT = Path("/app/data/workspaces/default")
BENCH = Path("/app/data/bench")
#: A check about the product's own tests - a file no runner collects, a suite
#: registered twice - is not contradicted by a product whose hidden tests pass:
#: those judge the product. Measured on the first pass: "test files against the
#: project's own test command" read 19 of 26 as wrong, all of them true facts
#: about the tests.
ABOUT_THE_TESTS = re.compile(r"\b(?:tests?|suites?|runners?)\b", re.I)
OUT = Path("/app/data/loop/check_precision.json")
SUITE_OUT = Path("/app/data/loop/suite_check_precision.json")
#: Where the suite as last locked is kept, and the record of every suite check's finding, in a workspace.
SNAPSHOT = Path(".harness") / "acceptance-snapshot"
FINDINGS = Path(".harness") / "check-findings.jsonl"


def hidden_scores(bench: Path = BENCH) -> dict[str, float]:
    """Workspace folder name -> the share of its hidden tests that passed, for every scored run."""
    scores: dict[str, float] = {}
    for path in sorted(bench.glob("run-*.json")):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        product, score = str(row.get("product") or ""), row.get("score")
        parts = Path(product).parts
        workspace = next((part for part in parts if part.startswith("workspace-")), "")
        if workspace and isinstance(score, (int, float)) and not row.get("brief_mismatch"):
            scores[workspace] = float(score)
    return scores


def precision(breaking: dict[str, list[str]], scores: dict[str, float]) -> dict[str, dict]:
    """Per check: products it called broken that were scored, how many of those passed every hidden test, and its precision."""
    measured: dict[str, dict] = {}
    for name, hits in breaking.items():
        if ABOUT_THE_TESTS.search(name):
            continue  # the hidden tests judge the product, not its tests
        scored = [ws for ws in hits if ws in scores]
        if not scored:
            continue
        false = sum(1 for ws in scored if scores[ws] >= 1.0)
        measured[name] = {"fired": len(scored), "false": false, "precision": round(1 - false / len(scored), 3)}
    return measured


def _stayed_locked(snapshot: Path, cited: list[str]) -> bool:
    """Whether a test a finding names is in the suite as last locked: a file of that name, or a test of that name."""
    try:
        files = [path for path in snapshot.rglob("*") if path.is_file()]
    except OSError:
        return False
    for name in cited:
        if "." in name and any(path.as_posix().endswith(name) for path in files):
            return True
        if "." not in name and any(name in path.read_text(encoding="utf-8", errors="replace") for path in files):
            return True
    return False


def suite_check_precision(workspaces: Path, scores: dict[str, float]) -> dict[str, dict]:
    """Per suite check: its findings on locked tests of scored runs, how many in runs with full hidden marks, precision.

    One finding is counted once per run however many rounds raised it.
    """
    fired: dict[str, int] = defaultdict(int)
    false: dict[str, int] = defaultdict(int)
    for workspace in sorted(p for p in workspaces.glob("workspace-*") if p.name in scores):
        try:
            lines = (workspace / FINDINGS).read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        seen: set[tuple[str, str]] = set()
        for line in lines:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            check, cited = str(row.get("check") or ""), [str(t) for t in row.get("tests") or []]
            if row.get("kind") in ("filtered", "withheld") or not check or not cited:
                continue
            key = (check, str(row.get("fingerprint")))
            if key in seen or not _stayed_locked(workspace / SNAPSHOT, cited):
                continue
            seen.add(key)
            fired[check] += 1
            false[check] += scores[workspace.name] >= 1.0
    return {check: {"fired": n, "false": false[check], "precision": round(1 - false[check] / n, 3)}
            for check, n in fired.items()}


def main() -> None:
    labels: dict[str, dict[str, str]] = {}
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--") and Path(sys.argv[1]).is_file():
        labels = json.loads(Path(sys.argv[1]).read_text())
    brief = ""
    flagged: dict[str, list[str]] = defaultdict(list)
    breaking: dict[str, list[str]] = defaultdict(list)
    workspaces = sorted(p for p in ROOT.iterdir() if p.is_dir() and p.name.startswith("workspace-"))
    for workspace in workspaces:
        try:
            files = _source_files(workspace)
        except Exception:  # noqa: BLE001
            continue
        for name, check in _CHECKS:
            try:
                found = check(files, workspace, None, brief)
            except Exception:  # noqa: BLE001 - a check that raises is reported as such
                found = ["(raised)"]
            if found:
                flagged[name].append(workspace.name)
                # What it would block on: graded as the release and the rounds grade it.
                if any(_grade((name, check), problem, False) == "BREAKS" for problem in found if problem != "(raised)"):
                    breaking[name].append(workspace.name)
    print(f"{len(workspaces)} workspaces, {len(_CHECKS)} checks\n")
    print(f"{'fires':>5}  {'false':>5}  kind        check")
    for name, _ in sorted(_CHECKS, key=lambda entry: -len(flagged.get(entry[0], []))):
        hits = flagged.get(name, [])
        false = sum(1 for ws in hits if labels.get(ws, {}).get(name) == "false")
        kind = "mechanical" if name in _MECHANICAL else "inferred"
        print(f"{len(hits):>5}  {false if labels else '-':>5}  {kind:<10}  {name}")
    if "--write" in sys.argv:
        measured = precision(breaking, hidden_scores())
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(measured, indent=1, sort_keys=True))
        print(f"\nprecision against hidden tests ({len(measured)} checks that blocked a scored product) -> {OUT}")
        for name, row in sorted(measured.items(), key=lambda item: item[1]["precision"]):
            print(f"  {row['precision']:.2f}  {row['false']}/{row['fired']}  {name}")
        suite_measured = suite_check_precision(ROOT, hidden_scores())
        SUITE_OUT.write_text(json.dumps(suite_measured, indent=1, sort_keys=True))
        print(f"\nsuite checks on tests that stayed locked ({len(suite_measured)} checks) -> {SUITE_OUT}")
        for name, row in sorted(suite_measured.items(), key=lambda item: item[1]["precision"]):
            print(f"  {row['precision']:.2f}  {row['false']}/{row['fired']}  {name}")
    print()
    for name, hits in sorted(flagged.items(), key=lambda item: -len(item[1])):
        print(f"{name}:")
        for ws in hits:
            print(f"    {ws}")


if __name__ == "__main__":
    main()
