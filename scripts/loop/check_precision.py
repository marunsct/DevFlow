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
    print()
    for name, hits in sorted(flagged.items(), key=lambda item: -len(item[1])):
        print(f"{name}:")
        for ws in hits:
            print(f"    {ws}")


if __name__ == "__main__":
    main()
