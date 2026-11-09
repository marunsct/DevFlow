"""The standing blind-spot report: hidden tests that keep failing, and whether they failed again after a fix named them.

    scripts/loop/loop.sh blind-spots [family]

Harness review HR2.Q.11 (owner: sum recurring notes). Reads every scored run in `data/bench/run-*.json`, groups the
hidden tests that failed by family, and finds the last row of `docs/improvement-plan.md` that names the test (its
words in the row's text). A failure in a run scored after that row was committed is a recurrence: the fix did not
hold, or it fixed another cause. A test no row names is an open blind spot. Report only; no run code reads it.
"""
from __future__ import annotations

import collections
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "data" / "bench"
PLAN = ROOT / "docs" / "improvement-plan.md"
_ROW = re.compile(r"^\| (LF\.\d+) \|")


def failures(bench: Path = BENCH) -> list[tuple[str, str, float, str]]:
    """(family, hidden test, when scored, run) for each hidden test that failed in a partial-score run."""
    out = []
    for path in sorted(bench.glob("run-*.json")):
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        family = str(result.get("benchmark") or "?")
        # Partial-score runs only: a run whose every hidden test failed had a product that did not start or answer,
        # one cause the per-test count would repeat once per test.
        try:
            score = float(result.get("score"))
        except (TypeError, ValueError):
            continue
        if not 0 < score < 1:
            continue
        for test in result.get("tests") or []:
            if str(test.get("outcome")) in ("failed", "error"):
                out.append((family, str(test.get("name")), path.stat().st_mtime, path.stem))
    return out


def _words(name: str) -> str:
    """A test's name as a row would quote it: its words, lower case, underscores as spaces."""
    words = re.findall(r"[a-z0-9]+", name.lower().replace("_", " "))
    return " ".join(words[1:] if words[:1] == ["test"] else words)


def rows_naming(names: list[str], plan: Path = PLAN) -> dict[str, str]:
    """The last plan row (its LF id) whose text holds each test's words."""
    try:
        lines = plan.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    rows = [(m.group(1), _words(line)) for line in lines if (m := _ROW.match(line))]
    found = {}
    for name in names:
        words = _words(name)
        if len(words.split()) < 3:
            continue
        for row, text in rows:
            if words in text:
                found[name] = row
    return found


def committed_at(row: str) -> float:
    """When the commit that added the plan row was made (epoch seconds); 0 when not found."""
    found = _the_commit_of(row)
    return found[1] if found else 0.0


def _the_commit_of(row: str) -> tuple[str, float] | None:
    """(hash, epoch seconds) of the commit that added the plan row; None when not found."""
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "log", "--reverse", "--format=%H %ct", "-S", f"| {row} |", "--", str(PLAN.relative_to(ROOT))],
            capture_output=True, text=True, timeout=60,
        ).stdout.split()
        return (out[0], float(out[1])) if len(out) >= 2 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def first_commits(ledger: Path = ROOT / "data" / "kpi" / "ledger.csv") -> dict[str, str]:
    """Each run's first harness commit, from the KPI ledger."""
    import csv

    try:
        with ledger.open(encoding="utf-8") as handle:
            return {row["run"]: (row.get("harness_commits") or "").split()[0]
                    for row in csv.DictReader(handle) if (row.get("harness_commits") or "").split()}
    except (OSError, KeyError):
        return {}


def ran_with(run_commit: str, fix_commit: str) -> bool | None:
    """Whether a run's first harness commit already held the fix's commit; None when git cannot tell."""
    try:
        code = subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", fix_commit, run_commit],
                              capture_output=True, timeout=30).returncode
        return {0: True, 1: False}.get(code)
    except (OSError, subprocess.SubprocessError):
        return None


#: Filled by `main`: each run's first harness commit and each row's commit; tests leave them empty.
RUN_COMMITS: dict[str, str] = {}
ROW_COMMITS: dict[str, str] = {}


def _after(run: str, at: float, row: str, when: dict[str, float]) -> bool:
    """Whether the run ran with the row's fix: by commit ancestry when both are known, else by the time it was scored.

    The score file's time is when it was scored, and old runs are scored again later; ancestry is the real test.
    """
    if RUN_COMMITS.get(run) and ROW_COMMITS.get(row):
        held = ran_with(RUN_COMMITS[run], ROW_COMMITS[row])
        if held is not None:
            return held
    return at > when.get(row, 0)


def report(found: list[tuple[str, str, float, str]], named: dict[str, str], when: dict[str, float]) -> list[str]:
    by = collections.defaultdict(list)
    for family, name, at, run in found:
        by[(family, name)].append((at, run))
    rows = []
    for (family, name), seen in by.items():
        row = named.get(name, "")
        since = [run for at, run in seen if row and _after(run, at, row, when)]
        rows.append((family, name, len(seen), row, since))
    rows.sort(key=lambda r: (r[0], -(len(r[4]) if r[3] else r[2]), -r[2]))
    out = []
    family_now = None
    for family, name, total, row, since in rows:
        if family != family_now:
            out.append(f"== {family}")
            family_now = family
        if row:
            state = f"named by {row}; failed {len(since)} time(s) since" + (f" (last {since[-1][:12]})" if since else "")
        else:
            state = "no plan row names it - an open blind spot"
        last = time.strftime("%m-%d", time.localtime(max(at for at, _ in by[(family, name)])))
        out.append(f"  {total:>3} failed (last {last})  {name[:80]:<80}  {state}")
    return out


def main(argv: list[str]) -> int:
    only = argv[1] if len(argv) > 1 else ""
    found = [f for f in failures() if not only or f[0] == only]
    if not found:
        print("no hidden test has failed in a scored run" + (f" of {only}" if only else ""))
        return 0
    named = rows_naming(sorted({name for _, name, _, _ in found}))
    commits = {row: _the_commit_of(row) for row in set(named.values())}
    when = {row: found_[1] for row, found_ in commits.items() if found_}
    ROW_COMMITS.update({row: found_[0] for row, found_ in commits.items() if found_})
    RUN_COMMITS.update(first_commits())
    print("\n".join(report(found, named, when)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
