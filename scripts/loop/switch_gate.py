"""Each switch against the runs without it: runs on, runs it acted in, what moved, and which to think of parking (plan item 22).

    python3 scripts/loop/switch_gate.py data/kpi/ledger.csv [N] [docs/improvement-plan.md]

or `loop.sh effects gate [N]`. It only reports: nothing here changes a switch; parking stays the owner's and the main
session's decision. The measure/fix rule says a change that moves no hidden score or KPI is parked, and until now
nothing counted that: 66 switches were on in the last run and no report said which had earned it.

The arms are compared within one benchmark, because a held-out family takes three times as long as a small one, and
a run of several harness versions is left out as every comparison here leaves it out (`kpi_ledger.the_arm`). A KPI has
moved when the on arm's mean is outside everything the off arm did and differs by at least `SMALLEST_CHANGE`, so
ordinary run-to-run spread does not count. Switches that always changed together cannot be told apart, and say so.
"""
from __future__ import annotations

import csv
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

#: The KPIs a switch may move, and whether more is better.
KPIS: dict[str, bool] = {
    "hidden_score": True, "quality_score": True, "mutation_score": True,
    "active_minutes": False, "model_calls": False, "fixes_reverted": False, "defects_left_open": False,
    "tool_failure_rate": False, "tokens_per_accepted_criterion": False,
}
#: The least relative change that counts as movement.
SMALLEST_CHANGE = 0.10
#: Runs a switch needs on before it can be named a candidate.
RUNS_BEFORE_PARKING = 3
#: Runs each arm needs in one comparison (plan MF.5, as `kpi_ledger.compare_arms`).
MINIMUM_RUNS_PER_ARM = 2


@dataclass
class Report:
    """One switch's line."""

    name: str
    runs_on: int = 0
    runs_off: int = 0
    runs_with_a_firing_record: int = 0
    runs_fired: int = 0
    moved: dict[str, str] = field(default_factory=dict)
    verdict: str = ""
    together_with: list[str] = field(default_factory=list)


def _number(row: dict, key: str) -> float | None:
    try:
        value = float(row.get(key, ""))
    except (TypeError, ValueError):
        return None
    return value if value == value else None


def clean(rows: list[dict]) -> list[dict]:
    """The runs of one harness version that recorded their switches."""
    return [r for r in rows if str(r.get("mixed_versions") or "False") != "True" and str(r.get("switches_on") or "").strip()]


def _cell(row: dict) -> str:
    """What must match for two runs to be compared: the benchmark and the model that served it."""
    return f"{row.get('benchmark') or ''}@{row.get('served_model') or ''}".rstrip("@")


def movement(on: list[dict], off: list[dict]) -> tuple[dict[str, str], int]:
    """Each KPI the on arm moved past the off arm's whole range, as "better/worse off-mean -> on-mean", and the comparable off runs.

    Compared only where each arm has `MINIMUM_RUNS_PER_ARM` runs of one benchmark on one model. Replayed on the real
    ledger without the model in the comparison, every switch turned on after a model change read as making things worse.
    """
    moved: dict[str, str] = {}
    comparable = 0
    for cell in sorted({_cell(r) for r in on} & {_cell(r) for r in off}):
        with_it = [r for r in on if _cell(r) == cell]
        without = [r for r in off if _cell(r) == cell]
        if len(with_it) < MINIMUM_RUNS_PER_ARM or len(without) < MINIMUM_RUNS_PER_ARM:
            continue
        comparable += len(without)
        for key, higher_is_better in KPIS.items():
            x = [v for r in with_it if (v := _number(r, key)) is not None]
            y = [v for r in without if (v := _number(r, key)) is not None]
            if not x or not y:
                continue
            mean_on, mean_off = sum(x) / len(x), sum(y) / len(y)
            if min(y) <= mean_on <= max(y):
                continue
            if abs(mean_on - mean_off) < SMALLEST_CHANGE * max(abs(mean_off), 1e-9):
                continue
            better = (mean_on > mean_off) == higher_is_better
            moved[f"{cell}:{key}"] = f"{'better' if better else 'worse'} {mean_off:.3g} -> {mean_on:.3g}"
    return moved, comparable


def _verdict(report: Report, minimum: int, has_a_signal: bool) -> str:
    """What the numbers say of this switch; a candidate only with enough runs on and an off arm to compare with."""
    if report.runs_on < minimum:
        return f"too few runs on (under {minimum})"
    if not report.runs_off:
        return "no off arm to compare with"
    if report.moved:
        if all(text.startswith("worse") for text in report.moved.values()):
            return "PARK CANDIDATE: only made KPIs worse"
        return "keep: moved a KPI"
    if not has_a_signal:
        return "PARK CANDIDATE: moved no KPI (leaves no signal, so whether it acted is unknown)"
    if report.runs_with_a_firing_record < minimum:
        return "PARK CANDIDATE: moved no KPI (too few runs recorded whether it acted)"
    if not report.runs_fired:
        return f"PARK CANDIDATE: never acted in {report.runs_with_a_firing_record} runs"
    return f"PARK CANDIDATE: acted in {report.runs_fired} runs and moved no KPI"


def reports(rows: list[dict], signals: set[str] | frozenset[str] = frozenset(), minimum: int = RUNS_BEFORE_PARKING,
            built_in: set[str] | frozenset[str] = frozenset()) -> list[Report]:
    """One report per switch that was on in a clean run, candidates first; a built-in fix is no switch to park."""
    runs = clean(rows)
    on_sets = [set(str(r.get("switches_on") or "").split()) - set(built_in) for r in runs]
    names = sorted(set().union(*on_sets)) if on_sets else []
    # Which runs had it on, as the key that tells switches apart: an identical key cannot be separated.
    arms = {name: tuple(name in s for s in on_sets) for name in names}
    groups: dict[tuple, list[str]] = defaultdict(list)
    for name, arm in arms.items():
        groups[arm].append(name)
    out = []
    for name in names:
        on = [r for r, s in zip(runs, on_sets) if name in s]
        off = [r for r, s in zip(runs, on_sets) if name not in s]
        # An older row's cell is empty once the column exists; a run that recorded nothing acting says "none" (`kpi.py`).
        recorded = [r for r in on if str(r.get("switches_fired") or "").strip()]
        moved, comparable = movement(on, off)
        report = Report(
            name=name, runs_on=len(on), runs_off=comparable, runs_with_a_firing_record=len(recorded),
            runs_fired=sum(1 for r in recorded if name in str(r.get("switches_fired") or "").split()),
            moved=moved,
            together_with=[other for other in groups[arms[name]] if other != name] if off else [],
        )
        report.verdict = _verdict(report, minimum, name in signals)
        out.append(report)
    return sorted(out, key=lambda r: (not r.verdict.startswith("PARK"), r.name))


#: A row of the plan's fix list.
_A_FIX_ROW = re.compile(r"^\| (LF\.\d+\w*) \|(.*)$", re.M)


def rows_without_a_predicted_flip(plan: str) -> list[str]:
    """The fix rows naming no test file: nothing says which test was to flip, so the fix cannot be checked against one."""
    return [m.group(1) for m in _A_FIX_ROW.finditer(plan) if not re.search(r"\btest_\w+|tests/", m.group(2))]


def lines(rows: list[dict], signals: set[str] | frozenset[str] = frozenset(), minimum: int = RUNS_BEFORE_PARKING, plan: str = "",
          built_in: set[str] | frozenset[str] = frozenset()) -> list[str]:
    """The report's text."""
    runs = clean(rows)
    out = [f"{len(runs)} clean runs of {len(rows)} in the ledger; a mixed-version run is not compared. This report changes no switch."]
    shown_groups: set[tuple[str, ...]] = set()
    for report in reports(rows, signals, minimum, built_in):
        out.append(f"{report.name}: on {report.runs_on}, comparable off {report.runs_off}, acted in "
                   f"{report.runs_fired}/{report.runs_with_a_firing_record} recorded - {report.verdict}")
        out.extend(f"    {key}: {text}" for key, text in sorted(report.moved.items()))
        group = tuple(sorted([report.name, *report.together_with]))
        if report.together_with and group not in shown_groups:
            shown_groups.add(group)
            out.append(f"    always on together, so not told apart: {' '.join(report.together_with)}")
    missing = rows_without_a_predicted_flip(plan)
    if missing:
        out.append(f"{len(missing)} fix rows name no test that flips, latest: {' '.join(missing[-5:])}")
    return out


def _from_the_application() -> tuple[frozenset[str], frozenset[str]]:
    """The switches with a firing signal, and the built-in fixes; empty when the application cannot be imported on this host."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
    try:
        from app.observability.switch_firing import SIGNALS
        from app.switches import BUILT_IN

        return frozenset(SIGNALS), frozenset(BUILT_IN)
    except ImportError:
        return frozenset(), frozenset()


def main(ledger: str = "data/kpi/ledger.csv", minimum: str = str(RUNS_BEFORE_PARKING), plan: str = "") -> int:
    with open(ledger, newline="") as handle:
        rows = list(csv.DictReader(handle))
    text = Path(plan).read_text(encoding="utf-8", errors="replace") if plan and Path(plan).is_file() else ""
    signals, built_in = _from_the_application()
    print("\n".join(lines(rows, signals, int(minimum), text, built_in)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:4]))
