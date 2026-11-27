"""How much a model reasons on real stage requests at each effort and budget, and whether its answer stays right: the
effort, reasoning budget and reply cap per stage kind (DX.7, design P4).

Measured before it, on this morning's model: design replies ran 30,000-44,000 tokens until a budget worked, about
three hours a run; the diagnosis's reasoning probe was one fixed puzzle asked once a way (145 output tokens as served,
under the 200-token floor), so no effort was kept although the chat template defaults to 0.9; the budget sizes that
then helped (cap less answer room, 8,000 a step) came from live runs, not from the diagnosis. On earlier models,
replies over 16,000 tokens held 18-46% of all output tokens.

So the replay set's requests (`replay_set`: real stage requests of three kinds, `stage_kinds`) are asked as served,
at the effort levels the server's template lists (by the route the tool diagnosis found, else the template's own
argument where the server lists levels), and at a reasoning budget where the server enforces one, a few tries each,
side by side (`diagnosis_pool`). Each reply is scored by `replay_set.score` - never by a hidden test - and its
reasoning, output tokens and seconds are kept. The rules (`choose`), per stage kind:

- an effort is a control that works when its median reasoning is under `WORKS_BELOW` of as served's;
- the effort set is the least such whose passes are within `WITHIN` of the best arm's over the same paired tries;
- the budget is the 90th percentile of the reasoning of the passing replies at that effort (as served where no effort
  was set), rounded up to a thousand, never above the stage cap less its answer room; only where a budget is enforced;
- the reply cap is that budget plus 1.25 times the largest passing answer, rounded up to a thousand;
- a budget arm whose passes are within `WITHIN` of the best shows a stage call's budget usable (DX.4's evidence at
  stage size).

Two tiers (design 4.6). `QUICK` runs with every new model's diagnosis and on the settings page: one request a kind
(the most reasoning-heavy), as served, the least listed effort and one budget, two tries, replies capped at 4,000 -
it answers "does this model reason past 4,000 tokens as served, and does a lower effort or a budget stop that with the
answer still valid?", and so sets an effort and whether a budget is usable, never a budget or cap (a reply held to
4,000 tokens cannot show what a stage needs above it). `FULL` starts only from the settings page (owner 2026-11-27): every request, as served, every
listed effort and two budgets, three tries, the stage's cap; held to `FULL.most_output_tokens` and `most_seconds`,
past which what is not yet asked is "not measured". Values are applied by `with_the_profile`, behind
`PROFILE_FROM_DIAGNOSIS` (`diagnosis_profile`); an owner's run setting for the effort is never replaced.
"""
from __future__ import annotations

import logging
import math
import statistics
import threading
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

WORKS_BELOW = 0.7
WITHIN = 1
CHARS_PER_TOKEN = 4
RAW_KEY = "dose"
#: A tier whose replies may run this long measures a budget and a cap; a shorter one, only an effort.
STAGE_SIZED_FROM = 16_000
_ORDER = ("none", "minimal", "low", "medium", "high", "xhigh", "max")


@dataclass(frozen=True)
class Tier:
    name: str
    items_per_kind: int
    tries: int
    cap: int
    all_efforts: bool
    budgets: int
    most_output_tokens: int
    most_seconds: int


QUICK = Tier("quick", 1, 2, 4_000, False, 1, 80_000, 20 * 60)
FULL = Tier("full", 3, 3, 32_000, True, 2, 800_000, 120 * 60)


def _round_up(tokens: float) -> int:
    return int(math.ceil(max(tokens, 1) / 1_000.0) * 1_000)


def p90(values: list[int]) -> int:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(math.ceil(0.9 * len(ordered))) - 1)]


def choose(replies: list[dict], stage_cap: int, budget_enforced: bool) -> dict[str, dict]:
    """The fields one stage kind's replies call for (see the module's rules). Each reply: `arm` ("as served",
    "effort <level>", "budget <n>"), `passed`, `reasoning`, `output`, `measured`, and the `item` and `try` it answered
    (its place among its arm's replies where not given). Arms are compared only on the tries both answered."""
    from app.models.reasoning_budget import answer_room

    arms: dict[str, dict[tuple, dict]] = {}
    for reply in replies:
        if reply.get("measured"):
            mine = arms.setdefault(str(reply["arm"]), {})
            mine[(reply.get("item"), reply.get("try", len(mine)))] = reply
    served = arms.get("as served") or {}
    if len(served) < 2:
        return {}

    def compared(arm: str) -> tuple[set, int, int, int]:
        """(the tries `arm` and as served both answered, passes of each there, the best arm's passes there)."""
        keys = set(served) & set(arms[arm])
        passes = {name: sum(1 for k in keys if replies_of[k]["passed"]) for name, replies_of in arms.items()
                  if keys <= set(replies_of)}
        return keys, passes.get("as served", 0), passes.get(arm, 0), max(passes.values(), default=0)

    def median_reasoning(arm: str, keys: set) -> float:
        return statistics.median(arms[arm][k]["reasoning"] for k in keys)

    def said(arm: str, keys: set) -> str:
        return (f"{arm}: {sum(1 for k in keys if arms[arm][k]['passed'])} of {len(keys)} passed, median reasoning "
                f"{int(median_reasoning(arm, keys)):,} tokens")

    fields: dict[str, dict] = {}
    efforts = sorted((arm for arm in arms if arm.startswith("effort ")),
                     key=lambda arm: _ORDER.index(arm.split(" ", 1)[1]) if arm.split(" ", 1)[1] in _ORDER else 99)
    chosen = "as served"
    for arm in efforts:
        keys, _served_passes, arm_passes, best = compared(arm)
        if len(keys) < 2:
            continue
        works = median_reasoning("as served", keys) > 0 and \
            median_reasoning(arm, keys) < WORKS_BELOW * median_reasoning("as served", keys)
        if works and arm_passes >= max(1, best - WITHIN):
            chosen = arm
            fields["effort"] = {"value": arm.split(" ", 1)[1], "confidence": "likely",
                                "evidence": f"{said('as served', keys)}; {said(arm, keys)}"}
            break
    passing = [r for r in arms[chosen].values() if r["passed"]]
    if budget_enforced and passing:
        ceiling = stage_cap - answer_room(stage_cap)
        budget = min(_round_up(p90([r["reasoning"] for r in passing])), ceiling)
        answer = max(max(r["output"] - r["reasoning"], 0) for r in passing)
        fields["budget"] = {"value": budget, "confidence": "likely",
                            "evidence": f"90th percentile of the reasoning of {len(passing)} passing replies at "
                                        f"{chosen}, rounded up"}
        fields["cap"] = {"value": _round_up(budget + 1.25 * answer), "confidence": "likely",
                         "evidence": f"the budget plus 1.25 times the largest passing answer ({answer:,} tokens)"}
    shown = []
    for arm in (arm for arm in arms if arm.startswith("budget ")):
        keys, _served_passes, arm_passes, best = compared(arm)
        if len(keys) >= 2:
            shown.append((arm_passes >= max(1, best - WITHIN), said(arm, keys)))
    if shown:
        fields["_budget_usable"] = {"value": any(ok for ok, _ in shown), "evidence": "; ".join(s for _, s in shown)}
    return fields


def _effort_extra(level: str, route: str) -> dict:
    if route == "template":
        return {"extra_body": {"chat_template_kwargs": {"reasoning_effort": level}}}
    return {"reasoning_effort": level}


def _reading(item: Any, response: Any, seconds: float) -> dict:
    from app.models.replay_set import score

    data = response if isinstance(response, dict) else response.model_dump(warnings=False)
    choice = (data.get("choices") or [{}])[0] or {}
    message, finish = choice.get("message") or {}, str(choice.get("finish_reason") or "")
    usage = data.get("usage") or {}
    details = usage.get("completion_tokens_details") if isinstance(usage.get("completion_tokens_details"), dict) else {}
    output = int(usage.get("completion_tokens") or 0)
    reported = details.get("reasoning_tokens")
    reasoning_text = str(message.get("reasoning_content") or message.get("reasoning") or "")
    reasoning = int(reported) if isinstance(reported, int) and reported > 0 else len(reasoning_text) // CHARS_PER_TOKEN
    passed, why = score(item, message, finish)
    return {"measured": True, "passed": passed, "why": why, "reasoning": min(reasoning, output) if output else reasoning,
            "output": output, "seconds": round(seconds, 1), "finish": finish}


def measure(model: Any, name: str, tier: Tier = QUICK) -> dict[str, dict]:
    """P4 asked of `model`; the fields found (by `diagnosis_profile` id), kept in its profile. Never raises."""
    from app.models import diagnosis_pool, diagnosis_profile, diagnostics, replay_set, server_profile, stage_kinds
    from app.models.reasoning_budget import budget_for, fields as budget_fields
    from app.models.server_fault import server_fault

    model = diagnosis_pool.handle(model)
    try:
        items = replay_set.load()
        if not items:
            return {}
        tools = diagnostics.recorded(name)
        settings = tools.settings if tools is not None else None
        enforced = bool(getattr(settings, "reasoning_budget", False))
        profile = server_profile.current()
        levels = [level for level in (getattr(profile, "reasoning_effort_levels", ()) or ()) if level in _ORDER]
        route = getattr(settings, "effort_route", "field") if getattr(settings, "reasoning_measurable", True) \
            else ("template" if levels else "field")
        levels = levels or ["low", "medium", "high"]
        levels = sorted(set(levels), key=_ORDER.index)
        below_high = [level for level in levels if _ORDER.index(level) < _ORDER.index("high")]
        efforts = below_high if tier.all_efforts else below_high[:1]
        by_kind: dict[str, list[Any]] = {}
        for kind in stage_kinds.KINDS:
            mine = [item for item in items if item.kind == kind]
            mine.sort(key=lambda item: -int((item.notes or {}).get("recorded_reasoning_chars") or 0))
            by_kind[kind] = mine[:tier.items_per_kind]
        spent = {"output": 0}
        started = time.monotonic()
        lock = threading.Lock()
        # The effort arms may spend two thirds of the tier's bound; the budget arms, which are sized from them, the
        # rest. Within a phase the requests go round the kinds, items and arms try by try, so a bound reached early
        # still leaves every kind and arm compared on the same tries.
        bound = {"limit": int(tier.most_output_tokens * 2 / 3) if enforced else tier.most_output_tokens}

        def ask(item: Any, label: str, extra: dict, _n: int) -> dict:
            with lock:
                over = spent["output"] >= bound["limit"] or time.monotonic() - started >= tier.most_seconds
            if over:
                return {"measured": False, "why": f"the {tier.name} tier's bound on tokens or time was reached"}
            began = time.monotonic()
            try:
                response = model.root_client.chat.completions.create(
                    model=model.model_name, messages=item.messages, tools=item.tools, max_tokens=tier.cap,
                    stream=False, **extra)
            except Exception as error:  # noqa: BLE001
                why = server_fault(error)
                if why:
                    return {"measured": False, "why": why}
                return {"measured": True, "passed": False, "why": f"refused: {str(error)[:80]}", "reasoning": 0,
                        "output": 0, "seconds": 0.0, "finish": "error"}
            reading = _reading(item, response, time.monotonic() - began)
            with lock:
                spent["output"] += reading["output"]
            return reading

        def asked(arms_of: Any) -> list[dict]:
            jobs = [(item, label, extra, n) for n in range(tier.tries) for rank in range(tier.items_per_kind)
                    for kind in stage_kinds.KINDS for item in by_kind[kind][rank:rank + 1]
                    for label, extra in arms_of(kind)]
            results = diagnosis_pool.side_by_side([lambda j=job: ask(*j) for job in jobs], model=model)
            return [{**(r if isinstance(r, dict) else {"measured": False, "why": str(r)}), "arm": label,
                     "kind": item.kind, "item": item.id, "try": n} for (item, label, _extra, n), r in zip(jobs, results)]

        effort_arms = [("as served", {})] + [(f"effort {level}", _effort_extra(level, route)) for level in efforts]
        replies = asked(lambda _kind: effort_arms)
        if enforced:
            budgets: dict[str, list[int]] = {}
            for kind in stage_kinds.KINDS:
                served = [r["reasoning"] for r in replies if r["kind"] == kind and r["arm"] == "as served"
                          and r.get("measured")]
                if tier.budgets == 1 or not served:
                    budgets[kind] = [b for b in [budget_for(tier.cap)] if b]
                else:
                    budgets[kind] = sorted({max(1_024, int(statistics.median(served))), max(1_024, p90(served))})
            bound["limit"] = tier.most_output_tokens
            replies += asked(lambda kind: [(f"budget {b}", {"extra_body": budget_fields(b)})
                                           for b in budgets.get(kind, [])])
        # A budget and a cap only from replies of a stage's size: replies held to the quick tier's 4,000 tokens cannot
        # show what a stage call needs above that, so the quick tier sets an effort and the budget's usability alone.
        stage_sized = tier.cap >= STAGE_SIZED_FROM
        found: dict[str, dict] = {}
        usable: dict[str, Any] = {}
        for kind in stage_kinds.KINDS:
            kind_replies = [r for r in replies if r["kind"] == kind]
            for key, entry in choose(kind_replies, tier.cap, enforced and stage_sized).items():
                if key == "_budget_usable":
                    usable[kind] = entry["value"]
                    continue
                found[f"{key}.{kind}"] = {**entry, "evidence": f"{tier.name} tier: {entry['evidence']}"}
        if any(key.startswith("effort.") for key in found):
            found["effort_route"] = {"value": route, "confidence": "likely",
                                     "evidence": "the route the tool diagnosis measured" if
                                     getattr(settings, "reasoning_measurable", True) else
                                     "the chat template's own argument, which the server lists levels for"}
        # What an earlier tier showed of a kind this one could not compare (its bound reached first) stands.
        earlier = diagnosis_profile.recorded(name).get(RAW_KEY) or {}
        if earlier.get("replay_set") == replay_set.set_hash(items):
            usable = {**(earlier.get("budget_usable") or {}), **usable}
        raw = {"tier": tier.name, "replay_set": replay_set.set_hash(items), "route": route, "budget_enforced": enforced,
               "budget_usable": usable,
               "replies": [{k: r.get(k) for k in ("kind", "item", "arm", "try", "measured", "passed", "why",
                                                  "reasoning", "output", "seconds", "finish")} for r in replies],
               "seconds": int(time.monotonic() - started), "output_tokens": spent["output"]}
        diagnosis_profile.keep(name, found, {RAW_KEY: raw})
        logger.info("Dose-response (%s) of %s: %s", tier.name, name, {k: v.get("value") for k, v in found.items()})
        return found
    except Exception:  # noqa: BLE001
        logger.warning("Could not measure the model's reasoning dose-response", exc_info=True)
        return {}


def measure_if_new(model: Any) -> None:
    """The quick tier at a run's start where the profile has no dose-response from this replay set on this server's
    model file, template and build. Never raises."""
    try:
        from app.models import diagnosis_fingerprint, diagnosis_profile, replay_set
        from app.models.reply_salvage import served_name

        name = served_name(model)
        profile = diagnosis_profile.recorded(name)
        raw = profile.get(RAW_KEY) or {}
        stale = diagnosis_fingerprint.stale(profile.get("fingerprint"), diagnosis_fingerprint.current())
        if raw.get("replay_set") == replay_set.set_hash() and not stale:
            return
        measure(model, name, QUICK)
    except Exception:  # noqa: BLE001
        logger.debug("Could not measure the model's reasoning dose-response", exc_info=True)


def budget_usable(name: str) -> bool | None:
    """Whether the dose-response's budget arms showed a stage call's budget usable: True where every kind measured
    passed within `WITHIN` of the best, False where one did not, None where none was asked."""
    from app.models import diagnosis_profile

    usable = ((diagnosis_profile.recorded(name).get(RAW_KEY) or {}).get("budget_usable") or {})
    values = [v for v in usable.values() if isinstance(v, bool)]
    return None if not values else all(values)


def with_the_profile(payload: dict, server: tuple[str, str], messages: list[Any] | None = None) -> dict:
    """`payload` with the effort, reasoning budget and reply cap the profile applies to its stage kind: the effort
    only where the request sends none (the owner's run setting stays), the cap only lowering, the budget only where
    one is sent and only lowering. Never raises."""
    try:
        from app.models import diagnosis_profile, stage_kinds
        from app.models.reasoning_budget import BUDGET_FIELD, answer_room

        kind = stage_kinds.of_payload(payload, messages)
        effort = diagnosis_profile.applied(f"effort.{kind}", server)
        budget = diagnosis_profile.applied(f"budget.{kind}", server)
        cap = diagnosis_profile.applied(f"cap.{kind}", server)
        if effort is None and budget is None and cap is None:
            return payload
        extra = dict(payload.get("extra_body") or {}) if isinstance(payload.get("extra_body"), dict) else {}
        template = dict(extra.get("chat_template_kwargs") or {})
        thinking_set = ("reasoning_effort" in payload or "reasoning_effort" in extra or "reasoning_effort" in template
                        or template.get("enable_thinking") is False)
        noted = []
        if effort and not thinking_set:
            if diagnosis_profile.applied("effort_route", server) == "template":
                extra["chat_template_kwargs"] = {**template, "reasoning_effort": effort}
            else:
                payload["reasoning_effort"] = effort
            noted.append(("effort", f"{kind}: reasoning effort {effort}"))
        if isinstance(cap, int) and cap > 0:
            key = "max_completion_tokens" if "max_completion_tokens" in payload else "max_tokens"
            if not isinstance(payload.get(key), int) or payload[key] > cap:
                payload[key] = cap
                noted.append(("cap", f"{kind}: replies capped at {cap:,} tokens"))
        sent = extra.get(BUDGET_FIELD)
        if isinstance(sent, int) and not isinstance(sent, bool) and sent > 0:
            wanted = [b for b in (budget, ) if isinstance(b, int) and b > 0]
            held = payload.get("max_tokens") or payload.get("max_completion_tokens")
            if isinstance(held, int) and held > 0:
                wanted.append(max(1, held - answer_room(held)))
            if wanted and min(wanted) < sent:
                extra[BUDGET_FIELD] = min(wanted)
                noted.append(("budget", f"{kind}: reasoning held to {min(wanted):,} tokens"))
        if extra:
            payload["extra_body"] = extra
        for field, words in noted:
            if diagnosis_profile.from_the_diagnosis(f"{field}.{kind}", server) is not None:
                diagnosis_profile.note(words)
    except Exception:  # noqa: BLE001 - the request as it was
        logger.debug("Could not apply the model's profile to the request", exc_info=True)
    return payload


__all__ = ["CHARS_PER_TOKEN", "FULL", "QUICK", "RAW_KEY", "Tier", "WITHIN", "WORKS_BELOW", "budget_usable", "choose",
           "measure", "measure_if_new", "p90", "with_the_profile"]
