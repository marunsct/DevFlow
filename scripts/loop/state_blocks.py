"""STATE.md's live and last-runs block, written from the run database, `data/bench` and the ledger (harness review HR2.O.2).

    scripts/loop/loop.sh state      (rewrites the block between the markers in docs/STATE.md)

Hand-kept, the block went stale: its As-of line read 10-29 on 11-08, and its last runs were ten days old. The block
between `<!-- state:generated -->` and `<!-- /state:generated -->` is replaced whole; everything else in STATE.md
stays as written. No model, no secrets: run ids, families, scores and the harness commits only.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
START, END = "<!-- state:generated -->", "<!-- /state:generated -->"
LIVE_STATUSES = ("running", "queued", "pending", "paused", "waiting_for_approval", "waiting_for_review")


def _jst(epoch: float) -> str:
    return time.strftime("%m-%d %H:%M JST", time.gmtime(epoch + 9 * 3600))


def recent_scores(bench: Path, ledger: Path, count: int = 3) -> list[dict]:
    """The last `count` scored runs, newest first, with their ledger's active minutes and mixed flag."""
    rows: dict[str, dict] = {}
    try:
        with ledger.open(encoding="utf-8") as handle:
            rows = {r["run"]: r for r in csv.DictReader(handle)}
    except (OSError, KeyError):
        pass
    out = []
    for path in sorted(bench.glob("run-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:count]:
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        row = rows.get(path.stem, {})
        out.append({
            "run": path.stem, "family": result.get("benchmark") or "?", "passed": result.get("passed"),
            "total": result.get("total"), "false_acceptance": bool(result.get("false_acceptance")),
            "status": (result.get("harness") or {}).get("status", ""), "scored": _jst(path.stat().st_mtime),
            "active": row.get("active_minutes", ""), "mixed": row.get("mixed_versions", "") == "True",
            "handoff": result.get("handoff_score"),
        })
    return out


def render(now: float, head: str, deployed: str, live: list[tuple[str, str, str]], recent: list[dict]) -> list[str]:
    lines = [START,
             f"**As of:** {_jst(now)} (written by `loop.sh state`). Harness {head[:8] or '?'} committed; "
             f"{deployed[:8] or '?'} deployed" + ("" if head[:8] == deployed[:8] else " (not the same)") + "."]
    if live:
        lines.append("**Live, and stopped in the last day:** " + "; ".join(f"{run[:12]} {status} at {stage or '?'}" for run, status, stage in live))
    else:
        lines.append("**Live, and stopped in the last day:** none.")
    lines.append("**Last scored:** " + ("; ".join(
        f"{r['run'][:12]} {r['family']} {r['passed']}/{r['total']} ({r['status'] or '?'}"
        + (", FALSE ACCEPTANCE" if r["false_acceptance"] else "") + (", mixed" if r["mixed"] else "")
        + (f", {float(r['active']):.0f} active min" if r["active"] not in ("", None) else "")
        + (f", handoff {r['handoff']}" if r.get("handoff") is not None else "") + f"; scored {r['scored']})"
        for r in recent) or "none") + ".")
    lines.append(END)
    return lines


def rewrite(state: Path, block: list[str]) -> bool:
    """Replace the block between the markers (or the first `**As of:**` line, the first time); True when written."""
    text = state.read_text(encoding="utf-8").splitlines()
    if START in text and END in text:
        a, b = text.index(START), text.index(END)
        text = text[:a] + block + text[b + 1:]
    else:
        at = next((i for i, line in enumerate(text) if line.startswith("**As of:**")), None)
        if at is None:
            return False
        text = text[:at] + block + text[at + 1:]
    state.write_text("\n".join(text) + "\n", encoding="utf-8")
    return True


def _live_runs() -> list[tuple[str, str, str]]:
    # Live now, and stopped (paused or failed) in the last day: an old paused run is history, not state.
    since = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 86400))
    query = ("select run_id, status, coalesce(current_stage,'') from runs where status in ("
             + ",".join(f"'{s}'" for s in LIVE_STATUSES if s != "paused") + ") "
             f"or (status in ('paused','failed') and updated_at > '{since}') order by updated_at desc limit 6")
    try:
        out = subprocess.run(["docker", "exec", "langchain-db-1", "psql", "-U", "postgres", "-d", "langchain", "-tAF|", "-c", query],
                             capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [tuple((line.split("|") + ["", "", ""])[:3]) for line in out.splitlines() if line.strip()]


def _deployed() -> str:
    try:
        env = subprocess.run(["docker", "image", "inspect", "langchain-worker", "--format",
                              "{{range .Config.Env}}{{println .}}{{end}}"], capture_output=True, text=True, timeout=30).stdout
        return next((line.split("=", 1)[1] for line in env.splitlines() if line.startswith("HARNESS_COMMIT=")), "")
    except (OSError, subprocess.SubprocessError):
        return ""


def main(argv: list[str]) -> int:
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    block = render(time.time(), head, _deployed(), _live_runs(),
                   recent_scores(ROOT / "data" / "bench", ROOT / "data" / "kpi" / "ledger.csv"))
    if not rewrite(ROOT / "docs" / "STATE.md", block):
        print("STATE.md has neither the markers nor an As-of line; nothing written", file=sys.stderr)
        return 1
    print("\n".join(block[1:-1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
