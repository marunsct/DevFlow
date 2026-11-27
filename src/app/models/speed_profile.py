"""How fast the model's server answers, whether it reuses a conversation's cache, and what two requests at once really
get: the timeout floor, the parallel cap and the balancer session scope (DX.6, design P1 and P2).

Nothing measured these before. The timeout floor was a constant, 30 tokens a second (`models.DEFAULT_MIN_TOKENS_PER
_SECOND`); from the transcripts the newest model runs at a median of 62 tokens a second where the one before it ran at
102-122. Two one-slot servers behind a balancer queued both runs' conversations on one server while the other sat
idle, and the parallel cap was the slots, whatever they gave.

- **Speed (P1)**: `SHORT_TRIES` short requests one at a time, alone; tokens a second each, from the server's own
  `timings` where it gives them (llama.cpp's `predicted_per_second`), else output tokens over the wall clock. The
  floor is the slowest of them (`floor_from`). Then a long request (about 8,000 tokens of project text) sent twice
  under one session: the cache works when the second's prompt took under `CACHE_WORKS_BELOW` of the first's
  (`cache_works`).
- **Concurrency (P2)**, self-hosted servers with two slots or more: k = 1 up to the slots requests at once, each its
  own session; the cap is the largest k whose total throughput is at least `GAIN` times k-1's (`cap_from`). Then,
  at k = the slots, `ROUNDS` rounds with each lane's session kept across them - each lane's conversation begun on its
  own, as two runs' are - against `ROUNDS` rounds with a fresh session per request: per-request sessions when they give
  `GAIN` times the throughput (`scope_from`), else conversation sessions (the cache is kept).
- **Alone**: both are spoiled by company, so neither is asked while another diagnosis request is in flight, and
  neither while live runs have calls on the server (`call_gate.in_flight_on`): then they are "not measured" and the
  profile keeps what it had.

What it sets (`diagnosis_profile`): `timeout_floor` always (only ever lowered from the default, which lengthens
patience; `MODEL_TOKENS_PER_SECOND` still wins); `parallel_cap` and `session_scope` behind `PROFILE_FROM_DIAGNOSIS`.
"""
from __future__ import annotations

import logging
import statistics
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)

SHORT_TRIES = 5
SHORT_REPLY_TOKENS = 400
#: A long request's opening, about 8,000 tokens of project text, the same both times it is sent.
_LONG_PREFIX = "".join(
    f"=== app/module_{n}.py ===\ndef handler_{n}(request):\n    return {{'value': {n}}}, 200\n\n" for n in range(290))
CACHE_WORKS_BELOW = 0.3
#: A step up in concurrency, or a session scope, is taken only for this much more total throughput (design P2).
GAIN = 1.3
ROUNDS = 2
P2_REPLY_TOKENS = 200
_SHORT = "Count from one to sixty in words, one number a line, nothing else."
#: The result is kept under this key of the profile, its numbers only.
RAW_KEY = "speed"


def floor_from(rates: list[float]) -> float | None:
    """The slowest generation rate of at least three measured replies; None with fewer."""
    measured = [r for r in rates if r and r > 0]
    return round(min(measured), 1) if len(measured) >= 3 else None


def cache_works(first_prompt_seconds: float | None, second_prompt_seconds: float | None) -> bool | None:
    """Whether the second send of one request read its prompt from the cache; None when either is unknown."""
    if not first_prompt_seconds or second_prompt_seconds is None or first_prompt_seconds <= 0:
        return None
    return second_prompt_seconds < CACHE_WORKS_BELOW * first_prompt_seconds


def cap_from(throughput: dict[int, float]) -> int | None:
    """The largest k reached by steps that each raised the total throughput `GAIN` times; None without k = 1."""
    if not throughput.get(1):
        return None
    cap = 1
    for k in sorted(k for k in throughput if k > 1):
        if throughput.get(k, 0) >= GAIN * throughput[cap] and k == cap + 1:
            cap = k
        else:
            break
    return cap


def scope_from(conversation: float | None, request: float | None) -> str | None:
    """"request" where fresh sessions gave `GAIN` times conversation sessions' throughput, else "conversation";
    None when either is unknown."""
    if not conversation or not request:
        return None
    return "request" if request >= GAIN * conversation else "conversation"


def _reading(response: Any, seconds: float) -> dict[str, Any]:
    data = response if isinstance(response, dict) else response.model_dump(warnings=False)
    usage = data.get("usage") or {}
    timings = data.get("timings") if isinstance(data.get("timings"), dict) else {}
    output = int(usage.get("completion_tokens") or 0)
    rate = timings.get("predicted_per_second")
    if not isinstance(rate, (int, float)) or rate <= 0:
        rate = output / seconds if seconds > 0 and output else None
    prompt_ms = timings.get("prompt_ms")
    return {"output_tokens": output, "seconds": round(seconds, 3),
            "tokens_per_second": round(float(rate), 1) if rate else None,
            "prompt_seconds": round(float(prompt_ms) / 1000, 3) if isinstance(prompt_ms, (int, float)) else None,
            "cached_tokens": timings.get("cache_n") if isinstance(timings.get("cache_n"), int) else None}


def _ask(model: Any, content: str, max_tokens: int, session: str | None = None) -> dict[str, Any]:
    from app.models.session_header import session_header_name

    extra: dict[str, Any] = {}
    header = session_header_name()
    if session and header:
        extra["extra_headers"] = {header: session}
    started = time.monotonic()
    response = model.root_client.chat.completions.create(
        model=model.model_name, messages=[{"role": "user", "content": content}], max_tokens=max_tokens,
        stream=False, **extra)
    return _reading(response, time.monotonic() - started)


def _busy(model: Any) -> int:
    try:
        from app.models.call_gate import in_flight_on

        return in_flight_on(str(getattr(model, "openai_api_base", "") or ""))
    except Exception:  # noqa: BLE001
        return 0


def speed(model: Any) -> dict[str, Any]:
    """P1: the short replies' rates, the floor, and the long request's two prompt times. Never raises."""
    if _busy(model):
        return {"not_measured": "a run was using the model server"}
    rates: list[float] = []
    replies = []
    try:
        for _ in range(SHORT_TRIES):
            reply = _ask(model, _SHORT, SHORT_REPLY_TOKENS)
            replies.append(reply)
            if reply["tokens_per_second"]:
                rates.append(reply["tokens_per_second"])
        session = f"diagnosis:{uuid.uuid4().hex[:12]}"
        question = _LONG_PREFIX + "\nWhat does handler_7 return? Reply in a few words."
        first = _ask(model, question, 16, session)
        second = _ask(model, question, 16, session)
    except Exception as error:  # noqa: BLE001 - what was measured stands
        from app.models.server_fault import server_fault

        return {"rates": rates, "floor": floor_from(rates), "replies": replies,
                "not_measured": f"the server failed a request ({server_fault(error) or type(error).__name__})"}

    def prompt_time(reply: dict) -> float | None:
        return reply["prompt_seconds"] if reply["prompt_seconds"] is not None else reply["seconds"]

    return {"rates": rates, "floor": floor_from(rates), "median": round(statistics.median(rates), 1) if rates else None,
            "replies": replies, "long": [first, second],
            "cache_works": cache_works(prompt_time(first), prompt_time(second))}


def _round(model: Any, sessions: list[str]) -> float:
    """Total output tokens a second of one round: one request a session, all at once."""
    from app.models.diagnosis_pool import side_by_side

    started = time.monotonic()
    replies = side_by_side([lambda s=s: _ask(model, _SHORT, P2_REPLY_TOKENS, s) for s in sessions],
                           at_once=len(sessions))
    seconds = time.monotonic() - started
    if any(isinstance(reply, BaseException) for reply in replies):
        raise next(reply for reply in replies if isinstance(reply, BaseException))
    return sum(reply["output_tokens"] for reply in replies) / seconds if seconds > 0 else 0.0


def concurrency(model: Any, slots: int | None, rounds: int = ROUNDS) -> dict[str, Any]:
    """P2: total throughput at k = 1 up to `slots`, and at k = `slots` under conversation and request sessions."""
    if not slots or slots < 2:
        return {"not_measured": "the server serves one request at a time" if slots == 1 else
                "the server does not say how many requests it serves at once"}
    if _busy(model):
        return {"not_measured": "a run was using the model server"}

    def fresh(n: int) -> list[str]:
        return [f"diagnosis:{uuid.uuid4().hex[:12]}" for _ in range(n)]

    try:
        throughput = {k: round(_round(model, fresh(k)), 1) for k in range(1, slots + 1)}
        lanes = fresh(slots)
        for lane in lanes:
            # Each lane's conversation begins on its own, as two runs' do: the balancer places it then.
            _ask(model, _SHORT, 8, lane)
        conversation = statistics.mean(_round(model, lanes) for _ in range(rounds))
        request = statistics.mean(_round(model, fresh(slots)) for _ in range(rounds))
    except Exception as error:  # noqa: BLE001
        from app.models.server_fault import server_fault

        return {"not_measured": f"the server failed a request ({server_fault(error) or type(error).__name__})"}
    return {"throughput": throughput, "cap": cap_from(throughput), "conversation": round(conversation, 1),
            "request": round(request, 1), "scope": scope_from(conversation, request), "slots": slots}


def measure(model: Any, name: str, rounds: int = ROUNDS) -> dict[str, dict]:
    """P1 and P2 asked of `model` (wrapped by `diagnosis_pool.handle`), kept in its profile; the fields found. Never
    raises."""
    from app.models import diagnosis_pool, diagnosis_profile, server_profile

    model = diagnosis_pool.handle(model)
    try:
        profile = server_profile.current()
        hosted = diagnosis_pool._is_hosted(model)
        p1 = speed(model)
        p2 = {"not_measured": "a hosted model: its rate limits, not its slots, bound it"} if hosted else \
            concurrency(model, getattr(profile, "slots", None), rounds)
        fields: dict[str, dict] = {}
        if p1.get("floor"):
            fields["timeout_floor"] = {"value": p1["floor"], "confidence": "likely",
                                       "evidence": f"slowest of {len(p1['rates'])} replies: {p1['floor']} tokens a "
                                                   f"second (median {p1.get('median')})"}
        if p2.get("cap"):
            fields["parallel_cap"] = {"value": p2["cap"], "confidence": "likely",
                                      "evidence": "total tokens a second at 1.." + str(p2["slots"]) + " at once: "
                                                  + ", ".join(f"{k}: {v}" for k, v in p2["throughput"].items())}
        if p2.get("scope"):
            fields["session_scope"] = {"value": p2["scope"], "confidence": "likely",
                                       "evidence": f"at {p2['slots']} at once: {p2['conversation']} tokens a second "
                                                   f"with a session a conversation, {p2['request']} with one a request"}
        diagnosis_profile.keep(name, fields, {RAW_KEY: {"speed": p1, "concurrency": p2}})
        logger.info("Speed profile of %s: %s", name, {k: v.get("value") for k, v in fields.items()})
        return fields
    except Exception:  # noqa: BLE001
        logger.debug("Could not measure the model's speed", exc_info=True)
        return {}


def measure_if_new(model: Any) -> None:
    """P1 and P2 at a run's start where the profile has no speed measured on this server (its model file, template,
    build, endpoints, slots and per-slot context, `diagnosis_fingerprint.SERVER_KEYS`). Never raises."""
    try:
        from app.models import diagnosis_fingerprint, diagnosis_profile
        from app.models.reply_salvage import served_name

        name = served_name(model)
        profile = diagnosis_profile.recorded(name)
        raw = profile.get(RAW_KEY) or {}
        stale = diagnosis_fingerprint.stale(profile.get("fingerprint"), diagnosis_fingerprint.current(),
                                            diagnosis_fingerprint.SERVER_KEYS)
        if (raw.get("speed") or {}).get("floor") and not stale:
            return
        measure(model, name)
    except Exception:  # noqa: BLE001
        logger.debug("Could not measure the model's speed", exc_info=True)


__all__ = ["CACHE_WORKS_BELOW", "GAIN", "RAW_KEY", "ROUNDS", "SHORT_TRIES", "cache_works", "cap_from",
           "concurrency", "floor_from", "measure", "measure_if_new", "scope_from", "speed"]
