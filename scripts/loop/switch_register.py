"""One row per switch in docs/measuring.md, written from the records: the ledger's runs and their scores.

    scripts/loop/loop.sh measuring      (rewrites the block between the markers in docs/measuring.md)

Hand-kept, the register named 5 of 58 switches: the rest sat in group rows whose state read "see `loop.sh
switches`". Each switch's row here says its group, whether it is on by default, how many scored runs had it on and
off and how often it fired, and the mean hidden score and active minutes on each side - "not measured" until both
sides have at least `LEAST_RUNS` runs on one harness commit or more. No model, no secrets.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
START, END = "<!-- switches:generated -->", "<!-- /switches:generated -->"
LEAST_RUNS = 2


def _runs(ledger: Path, bench: Path) -> list[dict]:
    out = []
    try:
        rows = list(csv.DictReader(ledger.open(encoding="utf-8")))
    except OSError:
        return out
    for row in rows:
        try:
            result = json.loads((bench / f"{row['run']}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, KeyError):
            continue
        try:
            minutes = float(row.get("active_minutes") or "nan")
        except ValueError:
            minutes = float("nan")
        out.append({"on": set((row.get("switches_on") or "").split()), "fired": set((row.get("switches_fired") or "").split()),
                    "score": float(result.get("score") or 0.0), "minutes": minutes})
    return out


def _signalled() -> set[str]:
    """The switches whose acting leaves a text of their own in a transcript; the rest cannot be counted as fired."""
    try:
        sys.path.insert(0, str(ROOT / "src"))
        from app.observability.switch_firing import SIGNALS

        return set(SIGNALS)
    except Exception:  # noqa: BLE001 - every switch then reads as having no signal
        return set()


def _mean(values: list[float]) -> str:
    values = [v for v in values if v == v]
    return f"{sum(values) / len(values):.2f}" if values else "-"


def rows(switches: dict[str, tuple[str, bool]], runs: list[dict]) -> list[str]:
    """`switches`: name -> (group, on by default). One markdown row each."""
    lines = []
    for name in sorted(switches, key=lambda n: (switches[n][0], n)):
        group, default = switches[name]
        # Off only after the switch first ran: a run from before it existed is another harness, not its off arm.
        first = next((i for i, r in enumerate(runs) if name in r["on"]), None)
        on = [r for r in runs if name in r["on"]]
        off = [] if first is None else [r for r in runs[first:] if name not in r["on"]]
        fired = sum(name in r["fired"] for r in on) if name in _signalled() else "no signal"
        verdict = ("measured: hidden " + _mean([r["score"] for r in on]) + " on / " + _mean([r["score"] for r in off])
                   + " off; minutes " + _mean([r["minutes"] for r in on]) + " / " + _mean([r["minutes"] for r in off])
                   if len(on) >= LEAST_RUNS and len(off) >= LEAST_RUNS else
                   f"not measured: needs {max(0, LEAST_RUNS - len(on))} more on and {max(0, LEAST_RUNS - len(off))} more off")
        lines.append(f"| `{name}` | {group} | {'on' if default else 'off'} | {len(on)} | {fired} | {len(off)} | {verdict} |")
    return lines


def render(switches: dict[str, tuple[str, bool]], runs: list[dict]) -> list[str]:
    return [START, f"Written by `loop.sh measuring` from {len(runs)} scored runs in the ledger. On and off counts are "
            "over every run, across commits: a verdict here says where to look, not that a pair on one commit was run.",
            "", "| Switch | Group | Default | Runs on | Fired | Runs off | Verdict |", "| --- | --- | --- | --- | --- | --- | --- |",
            *rows(switches, runs), END]


def rewrite(doc: Path, block: list[str]) -> None:
    text = doc.read_text(encoding="utf-8").splitlines()
    if START in text and END in text:
        a, b = text.index(START), text.index(END)
        text = text[:a] + block + text[b + 1:]
    else:
        at = next((i for i, line in enumerate(text) if line.startswith("## Measurement schedule")), len(text))
        text = text[:at] + ["## Every switch (generated)", "", *block, ""] + text[at:]
    doc.write_text("\n".join(text) + "\n", encoding="utf-8")


def _the_switches() -> dict[str, tuple[str, bool]]:
    sys.path.insert(0, str(ROOT / "src"))
    from app import switches as s

    found: dict[str, tuple[str, bool]] = {}
    for bundle, members in s.BUNDLES.items():
        found[bundle] = ("Bundles", True)
        for member in members:
            found[member] = (f"bundle {bundle}", True)
    for group, members in s.GROUPS.items():
        for member in members:
            found[member] = (group, member in s.EXPERIMENTS_ON)
    # What is deployed: the compose file's own default, where it names one.
    try:
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    except OSError:
        compose = ""
    import re

    for name, value in re.findall(r"^\s+([A-Z][A-Z0-9_]+): \$\{\1:-(on|off)\}\s*$", compose, re.M):
        if name in found:
            found[name] = (found[name][0], value == "on")
    return found


def main(argv: list[str]) -> int:
    block = render(_the_switches(), _runs(ROOT / "data" / "kpi" / "ledger.csv", ROOT / "data" / "bench"))
    rewrite(ROOT / "docs" / "measuring.md", block)
    print(f"{len(block) - 6} switch rows written to docs/measuring.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
