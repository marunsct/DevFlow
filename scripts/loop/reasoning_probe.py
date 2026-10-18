"""Does the model server honour a request for less thinking? Ten calls, a measurement (Initiative AR).

A reply that is all reasoning and no answer is the owner's biggest time cost
(a run spent about 90% of its output tokens thinking). Whether a per-request
setting changes that depends on the server, and the server reports no
reasoning tokens - so this measures it from the replies: the reply's length, the
reasoning's length, and whether it ended with an answer or ran out of room.

It sends the same planning-shaped request several ways, twice each, and prints
a table. It changes no setting and keeps nothing. It uses the owner's model:
run it only when no run is waiting for the server (the owner's allowance is
about an hour between runs), by hand:

    docker compose exec -T worker python - run < scripts/loop/reasoning_probe.py

Without the word `run` it only prints the plan, and sends nothing.
"""
from __future__ import annotations

import json
import statistics
import sys
import time
import urllib.request

REQUEST = (
    "You are the technical lead. A product has a notes service with routes to create, list, search and "
    "delete notes, stored in a file. Plan the work: list the files to write, in order, each with its purpose "
    "and the functions it exports, and the checks that prove it works."
)
VARIANTS = {
    "baseline": {},
    "effort_low": {"reasoning_effort": "low"},
    "effort_high": {"reasoning_effort": "high"},
    "thinking_off": {"chat_template_kwargs": {"enable_thinking": False}},
    "budget_256": {"chat_template_kwargs": {"enable_thinking": True}, "reasoning_budget": 256},
}
CALLS_EACH = 2
MAX_TOKENS = 4096


def summarise(rows: list[dict]) -> list[dict]:
    """One line per variant: how long its replies were, how much of that was reasoning, and how many were lost."""
    out = []
    for name in dict.fromkeys(row["variant"] for row in rows):
        mine = [row for row in rows if row["variant"] == name]
        lengths = [row["output_tokens"] for row in mine]
        reasoning = [row["reasoning_chars"] for row in mine]
        out.append({
            "variant": name,
            "calls": len(mine),
            "median_output_tokens": statistics.median(lengths),
            "median_reasoning_chars": statistics.median(reasoning),
            "answer_chars_median": statistics.median(row["answer_chars"] for row in mine),
            "lost_replies": sum(1 for row in mine if row["finish_reason"] == "length" and not row["answer_chars"]),
        })
    return out


def honoured(table: list[dict]) -> str:
    """What the table says: whether any variant shortened the replies, and by how much."""
    base = next((line for line in table if line["variant"] == "baseline"), None)
    if base is None or not base["median_output_tokens"]:
        return "no baseline to compare with"
    notes = []
    for line in table:
        if line["variant"] == "baseline":
            continue
        change = line["median_output_tokens"] / base["median_output_tokens"] - 1
        notes.append(f"{line['variant']}: {change:+.0%} output, lost replies {line['lost_replies']} (baseline {base['lost_replies']})")
    cut = [line for line in table if line["variant"] != "baseline" and line["median_output_tokens"] < 0.7 * base["median_output_tokens"]]
    verdict = "honoured by " + ", ".join(line["variant"] for line in cut) if cut else "the server does not shorten replies for any of these"
    return verdict + "\n" + "\n".join(notes)


def _post(base_url: str, key: str, body: dict) -> dict:
    request = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {key}"} if key else {})},
    )
    with urllib.request.urlopen(request, timeout=900) as reply:
        return json.load(reply)


def main() -> int:
    if "run" not in sys.argv[1:]:
        print(f"Plan: {len(VARIANTS)} variants x {CALLS_EACH} calls = {len(VARIANTS) * CALLS_EACH} requests of up to {MAX_TOKENS} tokens.")
        print("Nothing was sent. Add the word `run` when no run is waiting for the model server.")
        return 0
    from app.models import _runtime_settings

    settings = _runtime_settings()
    rows = []
    for name, extra in VARIANTS.items():
        for _ in range(CALLS_EACH):
            started = time.monotonic()
            reply = _post(settings.openai_base_url, settings.openai_api_key or "", {
                "model": settings.model_name, "max_tokens": MAX_TOKENS,
                "messages": [{"role": "user", "content": REQUEST}], **extra,
            })
            message = (reply.get("choices") or [{}])[0].get("message") or {}
            rows.append({
                "variant": name,
                "output_tokens": (reply.get("usage") or {}).get("completion_tokens") or 0,
                "reasoning_chars": len(message.get("reasoning_content") or message.get("reasoning") or ""),
                "answer_chars": len((message.get("content") or "").strip()),
                "finish_reason": (reply.get("choices") or [{}])[0].get("finish_reason"),
                "seconds": round(time.monotonic() - started, 1),
            })
    table = summarise(rows)
    for line in table:
        print(json.dumps(line))
    print(honoured(table))
    return 0


if __name__ == "__main__" and len(sys.argv) > 1:
    raise SystemExit(main())
