"""How often each kind of completion gap preceded a lost hidden test (harness review HR2.G.3, the measurement G1 asked for).

    scripts/loop/gap_precision.py [data/bench] [run.json]

A gap's kind is its first six words with numbers, quoted names and backticked names taken out ("N line(s) of the
interface contract"). Over every scored run in `data/bench`, each kind's precision is the share of runs that carried
it and lost at least one hidden test, beside the share of all scored runs that lost one. Given a run's own result
file, it prints that run's gap kinds with their precision instead of the whole table: `loop.sh score` does, so a
reader of a score sees what each of its gaps has meant before. Report only.
"""
from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

LEAST_RUNS = 3


def kind_of(gap: str) -> str:
    plain = re.sub(r"`[^`]*`|\"[^\"]*\"|\d+", "N", str(gap))
    return " ".join(plain.split()[:6])


def _scored(path: Path) -> tuple[float, list[str]] | None:
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        return float(result.get("score")), [str(g) for g in result.get("completion_gaps") or []]
    except (OSError, ValueError, TypeError):
        return None


def table(bench: Path) -> tuple[dict[str, tuple[int, int]], float, int]:
    """({kind: (runs that lost a hidden test, runs that carried it)}, the share of all runs that lost one, runs)."""
    carried: collections.Counter = collections.Counter()
    lost: collections.Counter = collections.Counter()
    runs = losing = 0
    for path in sorted(bench.glob("run-*.json")):
        found = _scored(path)
        if found is None:
            continue
        score, gaps = found
        runs += 1
        losing += score < 1
        for kind in {kind_of(gap) for gap in gaps}:
            carried[kind] += 1
            lost[kind] += score < 1
    return {kind: (lost[kind], n) for kind, n in carried.items()}, (losing / runs if runs else 0.0), runs


def lines_for(gaps: list[str], precision: dict[str, tuple[int, int]], base: float) -> list[str]:
    out = []
    for kind in dict.fromkeys(kind_of(gap) for gap in gaps):
        lost, n = precision.get(kind, (0, 0))
        out.append(f"  {kind[:60]:<60} " + (f"preceded a lost hidden test in {lost} of {n} runs ({lost / n:.0%})"
                                             if n >= LEAST_RUNS else f"too few runs to say ({n})"))
    if out:
        out.insert(0, f"gap kinds (runs that lost a hidden test: {base:.0%} of all scored runs):")
    return out


def main(argv: list[str]) -> int:
    bench = Path(argv[1]) if len(argv) > 1 else Path("data/bench")
    precision, base, runs = table(bench)
    if len(argv) > 2:
        found = _scored(Path(argv[2]))
        print("\n".join(lines_for(found[1] if found else [], precision, base)))
        return 0
    print(f"{runs} scored runs; {base:.0%} lost at least one hidden test")
    for kind, (lost, n) in sorted(precision.items(), key=lambda item: -item[1][1]):
        if n >= LEAST_RUNS:
            print(f"{lost:>4}/{n:<4} {lost / n:>4.0%}  {kind}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
