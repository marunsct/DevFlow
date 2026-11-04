"""Check runs against what must always hold; print each finding, worst first.

Runs INSIDE the worker: `scripts/loop/loop.sh deep-audit [run-id ...]` (no ids: every run updated in the last day).
Owner, 2026-11-04: audit recent and upcoming runs in every aspect, so a fault like a suite that fell from 17/17 to
3/17 with clean code is never missed again. The routine audit read stages and defects; this reads the numbers and the
product itself. Never prints a key or a setting's value.

Each check is one invariant:
  measured-worse   the same product measured worse than it did (the suite's history)
  stale-cache      a compiled cache that matches its source's size and time but not its content
  mutation-left    a deliberate change's journal still in the workspace
  uncommitted      product files differing from the last commit
  other-model      a model request to a model other than the run's own
  slow-reply       a model reply that took over 20 minutes
  long-stage       one stage's visits spanning over 60 minutes
  refusal-storm    over 10 refused tool calls in one stage
  lost-reply       replies cut off with nothing kept
  shipped-gap      a release with criteria deferred, unit tests failing, or a suite locked with problems open
  failed           the run failed, and why
"""
import datetime
import glob
import importlib.util
import json
import marshal
import os
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, "/app/src")

WORKSPACES = "/app/data/workspaces/default"
TRANSCRIPTS = "/app/data/transcripts"
SLOW_REPLY_SECONDS = 20 * 60
LONG_STAGE_SECONDS = 60 * 60
REFUSAL_STORM = 10


def _at(text):
    try:
        return datetime.datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None


def _jst(moment):
    return (moment + datetime.timedelta(hours=9)).strftime("%m-%d %H:%M") if moment else "?"


def _runs(asked):
    from app.server.run_store import RunStore

    store = RunStore.shared()
    if asked:
        return [r for r in (store.get(run_id) for run_id in asked) if r is not None]
    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
    return [r for r in store.list_all(limit=200) if (_at(r.updated_at) or since) >= since]


def _project(workspace):
    try:
        return workspace / (workspace / ".project-directory").read_text().strip()
    except OSError:
        return None


def _stale_caches(project):
    """Python bytecode whose header matches its source but whose code does not."""
    found = []
    magic = importlib.util.MAGIC_NUMBER
    for pyc in project.rglob("__pycache__/*.pyc"):
        if ".venv" in pyc.parts or "node_modules" in pyc.parts:
            continue
        source = pyc.parent.parent / (pyc.name.split(".")[0] + ".py")
        try:
            data = pyc.read_bytes()
            if not source.is_file() or data[:4] != magic or int.from_bytes(data[4:8], "little") & 1:
                continue
            mtime, size = int.from_bytes(data[8:12], "little"), int.from_bytes(data[12:16], "little")
            stat = source.stat()
            if mtime != int(stat.st_mtime) or size != stat.st_size & 0xFFFFFFFF:
                continue  # Python would recompile it
            current = compile(source.read_bytes(), str(source), "exec", dont_inherit=True)
            if marshal.loads(data[16:]).co_code != current.co_code:
                found.append(str(source.relative_to(project)))
        except Exception:  # noqa: BLE001 - a cache that cannot be read is not a finding
            continue
    return found


def _uncommitted(workspace, project):
    try:
        out = subprocess.run(["git", "-C", str(workspace), "status", "--porcelain", "--", str(project)],
                             capture_output=True, text=True, timeout=30).stdout
    except Exception:  # noqa: BLE001
        return []
    return [line[3:] for line in out.splitlines() if line and not line.startswith("??")]


def _transcript(run_id):
    files = glob.glob(f"{TRANSCRIPTS}/{run_id}*.jsonl")
    rows = []
    for path in files[:1]:
        for line in open(path, encoding="utf-8", errors="replace"):
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def audit(record):
    findings = []  # (severity, check, text)
    run_id = record.run_id
    workspace = Path(WORKSPACES) / f"workspace-{run_id}"
    project = _project(workspace) if workspace.is_dir() else None
    pinned = {}
    try:
        from app.models.model_pin import summary_of  # noqa: F401
        from app.server.run_store import RunStore

        pinned = (RunStore.shared().model_states([run_id]).get(run_id) or (False, {}))[1] or {}
    except Exception:  # noqa: BLE001
        pinned = {}

    if record.status == "failed":
        findings.append((0, "failed", str(record.error or "")[:240]))
    if workspace.is_dir():
        try:
            from app.acceptance import suite

            for entry in suite.same_product_measured_worse(workspace):
                findings.append((0, "measured-worse",
                                 f"{entry['passed']} of {entry['tests']} at {entry['at']}, the same product had done "
                                 f"better at {entry['worse_than_the_same_product_at']}"))
        except Exception:  # noqa: BLE001
            pass
        if (workspace / ".harness" / "mutation-in-flight.json").exists():
            findings.append((0, "mutation-left", "a deliberate change's journal is still in the workspace"))
    if project and project.is_dir():
        for path in _stale_caches(project):
            findings.append((0, "stale-cache", f"{path}: its compiled cache matches its time and size, not its code"))
        dirty = _uncommitted(workspace, project)
        if dirty and record.status in ("completed", "failed"):
            findings.append((1, "uncommitted", ", ".join(dirty[:5])))

    rows = _transcript(run_id)
    own_model = str(pinned.get("OPENAI_MODEL") or "")
    served = Counter(str(r.get("served_model") or "") for r in rows if r.get("kind") == "provenance")
    if own_model:
        for name, count in served.items():
            if name and own_model not in name and name not in own_model:
                findings.append((0, "other-model", f"served by {name} in {count} segment(s); the run's own model is "
                                                   f"{own_model}"))
    last_request = {}
    active = defaultdict(float)
    previous = {}
    refusals = Counter()
    lost = 0
    for r in rows:
        at = _at(r.get("at"))
        stage = str(r.get("stage") or "-")
        if not at or stage == "-":
            continue
        # A stage's own working time: gaps over a quarter of an hour are another visit, or waiting, not work.
        if stage in previous and (at - previous[stage]).total_seconds() < 15 * 60:
            active[stage] += (at - previous[stage]).total_seconds()
        previous[stage] = at
        if r.get("kind") == "model_request":
            last_request[stage] = at
        elif r.get("kind") == "model_response":
            asked_at = last_request.pop(stage, None)
            if asked_at and (at - asked_at).total_seconds() > SLOW_REPLY_SECONDS:
                findings.append((2, "slow-reply", f"{stage}: {int((at - asked_at).total_seconds() // 60)} min, "
                                                  f"from {_jst(asked_at)} JST"))
            if r.get("finish_reason") == "length" and not (r.get("text") or r.get("tool_calls")) and not r.get("salvaged"):
                lost += 1
        elif r.get("kind") == "tool_result":
            content = str(r.get("content") or "")
            if str(r.get("status") or "") == "error" or content.lstrip().startswith(("Refusing", '{"error"', "Error")):
                refusals[stage] += 1
    for stage, seconds in active.items():
        if seconds > LONG_STAGE_SECONDS:
            findings.append((2, "long-stage", f"{stage}: {int(seconds // 60)} min of its own working time"))
    for stage, count in refusals.items():
        if count > REFUSAL_STORM:
            findings.append((2, "refusal-storm", f"{stage}: {count} refused tool calls"))
    if lost:
        findings.append((1, "lost-reply", f"{lost} reply(ies) cut off with nothing kept"))
    if record.status == "completed":
        for gap in list(getattr(record, "completion_gaps", None) or []):
            text = str(gap)
            if any(word in text for word in ("deferred", "still fail", "locked with this still open")):
                findings.append((1, "shipped-gap", text[:200]))
    return findings


def main():
    asked = [a for a in sys.argv[1:] if a.startswith("run-")]
    records = _runs(asked)
    names = {0: "MUST FIX", 1: "CHECK", 2: "WASTE"}
    for record in records:
        found = sorted(audit(record))
        name = getattr(record, "run_name", "") or ""
        print(f"##### {record.run_id} {name} [{record.status}] - {len(found)} finding(s)")
        for severity, check, text in found:
            print(f"  {names[severity]:8} {check:15} {text}")
    print(f"audited {len(records)} run(s)")


if __name__ == "__main__":
    main()
