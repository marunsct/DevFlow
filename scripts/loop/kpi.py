"""One run's KPIs as JSON: the numbers every later change is measured against (Initiative W.4).

The audits print text for a person reading a check. A change claimed to cut
waste needs the same numbers for every run, in one shape, kept side by side -
`loop.sh kpi` writes this script's output to `data/kpi/<run>.json` and a row
of `data/kpi/ledger.csv` (`kpi_ledger.py`), and flags a KPI past 1.5x its
average over the five runs before.

Runs INSIDE the worker, where transcripts live, piped on stdin like
`audit_live.py`:

    docker compose exec -T worker python - <run-id> < scripts/loop/kpi.py

`kpis(records)` is the whole computation, so a test can hand it records.
"""
from __future__ import annotations

import glob
import json
import sys

# The computation lives in the application now, so the run page answers the
# same numbers (plan UI-S6); this script reads a transcript file and prints them.
from app.observability.run_kpis import (  # noqa: F401 - re-exported for the tests and older callers
    FAIL,
    HEAD_CHARS,
    INVALID_TOOL,
    LAYERS,
    ORPHAN_GAP_SECONDS,
    READS,
    REDUNDANT,
    TAIL_CHARS,
    kpis,
)


def main(run: str) -> int:
    paths = sorted(glob.glob(f"/app/data/transcripts/{run}*.jsonl"))
    if not paths:
        print(json.dumps({"run": run, "error": "no transcript"}))
        return 1
    records = []
    for line in open(paths[0], errors="replace"):
        try:
            records.append(json.loads(line))
        except ValueError:
            continue
    from app.observability.run_kpis import per_accepted_criterion
    from app.observability.switch_firing import fired

    numbers = with_the_pauses(kpis(records), paused_seconds_of(run))
    numbers = with_model_errors_by_kind(numbers, records)
    numbers = with_salvage_outcomes(numbers, records)
    print(json.dumps({"run": run, **per_accepted_criterion(numbers, accepted_criteria(run)), **owner_rating(run),
                      "switches_fired": " ".join(fired(records)) or "none"}))
    return 0


def paused_seconds_of(run: str) -> float:
    """How long the run was paused in all, from the run store; 0 when it cannot be read. Never raises."""
    try:
        from app.server.run_store import RunStore

        return float(RunStore().paused_seconds([run]).get(run, 0.0))
    except Exception:  # noqa: BLE001 - a KPI row without the pauses is the row as it was
        return 0.0


def with_the_pauses(numbers: dict, paused_seconds: float) -> dict:
    """`numbers` with the recorded pauses taken off `active_minutes` and kept as `paused_minutes` (HR2.R.1).

    Measured: `runs.paused_seconds` was kept and never read; 150 paused minutes on one day and 2,152 the week before
    sat inside `active_minutes`, since only silences over ten minutes were ever taken off.
    """
    paused = round(max(float(paused_seconds or 0.0), 0.0) / 60, 1)
    active = numbers.get("active_minutes")
    out = {**numbers, "paused_minutes": paused}
    if isinstance(active, (int, float)):
        out["active_minutes"] = round(max(float(active) - paused, 0.0), 1)
    return out


def with_salvage_outcomes(numbers: dict, records: list) -> dict:
    """`numbers` with what followed each salvaged reply (HR2.C.4a): cut again, another call in the stage, or the
    stage's end - the measure of whether a salvage was taken as the answer. Measured: 137 salvages in a day, 24% of
    the technical lead's replies, and nothing said whether the stage used them."""
    salvaged = cut_again = another_call = at_end = 0
    for index, r in enumerate(records):
        if r.get("kind") != "model_response" or not r.get("salvaged"):
            continue
        salvaged += 1
        stage = r.get("stage")
        following = next((later for later in records[index + 1:]
                          if later.get("stage") == stage and later.get("kind") in ("model_request", "model_response")), None)
        if following is None:
            at_end += 1
        elif following.get("kind") == "model_response" and following.get("salvaged"):
            cut_again += 1
        else:
            later_reply = next((later for later in records[index + 1:]
                                if later.get("stage") == stage and later.get("kind") == "model_response"), None)
            if later_reply is not None and later_reply.get("salvaged"):
                cut_again += 1
            else:
                another_call += 1
    return {**numbers, "salvaged_replies": salvaged, "salvaged_then_cut_again": cut_again,
            "salvaged_then_another_call": another_call, "salvaged_at_stage_end": at_end}


#: Why a model call failed, by the words the error carries (HR2.R.4). Only a rejected request is the harness's.
_ERROR_KINDS = (
    ("owner_action", ("No model loaded", "unloaded by user", "quota", "model not found", "does not exist", "invalid API key",
                      "Incorrect API key")),
    ("server_unavailable", ("Connection", "Lost connection", "connection", "protocol predict stream", "llama-server",
                            "Server disconnected", "502", "503", "504")),
    ("timeout", ("timed out", "Timeout", "timeout")),
)


def error_kind(text: str) -> str:
    """One of owner_action / server_unavailable / timeout / request_rejected for a model error's text."""
    said = str(text or "")
    for kind, words in _ERROR_KINDS:
        if any(word in said for word in words):
            return kind
    return "request_rejected"


def with_model_errors_by_kind(numbers: dict, records: list) -> dict:
    """`numbers` with the model errors counted by kind; `model_errors` keeps only the requests the server rejected.

    Measured over every stored transcript: of 779 model errors, 361 were pause markers (already left out), 93 the
    owner's unloads, 21 quota, 80 lost connections, 13 timeouts, 104 engine stream errors - all counted as the
    harness's errors and flagged as regressions.
    """
    kinds: dict[str, int] = {}
    for r in records:
        if r.get("kind") != "model_error":
            continue
        text = str(r.get("error") or "")
        if "RunCancelled" in text or "was stopped" in text:
            continue
        kind = error_kind(text)
        kinds[kind] = kinds.get(kind, 0) + 1
    out = {**numbers, "model_errors": kinds.get("request_rejected", 0)}
    for kind in ("owner_action", "server_unavailable", "timeout"):
        out[f"model_errors_{kind}"] = kinds.get(kind, 0)
    return out


def accepted_criteria(run: str) -> int | None:
    """How many criteria the run's last acceptance result passes, or None when it has none (plan MF.3)."""
    paths = glob.glob(f"/app/data/workspaces/*/workspace-{run}/.harness/acceptance-result.json")
    try:
        result = json.load(open(paths[0])) if paths else None
    except (OSError, ValueError):
        return None
    if not isinstance(result, dict) or not result.get("ran"):
        return None
    return sum(1 for c in (result.get("criteria") or {}).values() if (c or {}).get("status") == "passed")



def owner_rating(run: str, root: str = "/app/data") -> dict:
    """The owner's rating of the delivered run, 1-5 and a line, for its KPI row (plan EV.1); empty when unrated."""
    try:
        rating = json.load(open(f"{root}/ratings/{run}.json"))
    except (OSError, ValueError):
        return {"owner_rating": "", "owner_note": ""}
    return {"owner_rating": rating.get("score", ""), "owner_note": " ".join(str(rating.get("note") or "").split())[:200]}

if __name__ == "__main__" and len(sys.argv) > 1:
    raise SystemExit(main(sys.argv[1]))
