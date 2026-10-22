"""Per-run token accounting for the model calls a run makes.

Three properties this module is built around, each of which was absent before
and each of which is a way of reporting a number that is not true.

**It is scoped to a run.** The previous handler accumulated into instance
attributes with no run id. An operator's only question about cost is "what did
*this run* cost", and an accumulator with no run id cannot answer it. Totals
live in `_RUN_COSTS`, keyed by run id, and `run_cost(run_id)` reads one back.

**It does not price what it cannot price.** The previous handler applied
GPT-4o-mini's rates to every call: `(p * 0.15 + c * 0.60) / 1e6`. This
deployment's default provider is `local` - an OpenAI-compatible server on the
operator's own machine, whose marginal cost is electricity. Reporting a dollar
figure for that is not an approximation, it is a fabricated measurement. A
local provider is priced at nothing, and a model absent from the table is
counted as *unpriced* rather than guessed at.

**It says how much of the run it priced.** `usd` alone is a trap: a run whose
model is missing from the table would report `$0.00`, which reads as "this was
free" rather than "this was not measured". Every summary therefore carries
`priced_requests` and `unpriced_requests`, and `fully_priced` is false when any
call went unpriced.

Prices are list prices in US dollars per million tokens, correct as of
`PRICES_AS_OF`. They go stale - that is why `MODEL_PRICES_JSON` exists, so an
operator can correct a rate without waiting for a release, the same reasoning
as `_fallback_model` in `app.models`: a provider's pricing change should be a
configuration change, not a code change.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

logger = logging.getLogger(__name__)


PRICES_AS_OF = "2026-05"
"""The month the rates below were current.

Stated because a price table with no date cannot be audited: a reader has no
way to tell a rate that is right from one that aged out two providers ago.
"""


@dataclass(frozen=True)
class Price:
    """A model's list price, in US dollars per million tokens."""

    input_usd_per_mtok: float
    output_usd_per_mtok: float

    def usd_for(self, prompt_tokens: int, completion_tokens: int) -> float:
        return (
            prompt_tokens * self.input_usd_per_mtok
            + completion_tokens * self.output_usd_per_mtok
        ) / 1_000_000


#: List prices per million tokens, keyed by the model id the provider reports.
#:
#: Keys are matched by longest prefix (see `_lookup`), because providers append
#: dated suffixes to the same model - `claude-haiku-4-5-20251001` should price
#: as `claude-haiku-4-5` rather than fall through to unpriced on every new date
#: stamp. A model that matches nothing here is counted as unpriced; it is not
#: charged at a neighbour's rate.
PRICES: dict[str, Price] = {
    # Anthropic
    "claude-opus-4": Price(15.00, 75.00),
    "claude-sonnet-4": Price(3.00, 15.00),
    "claude-haiku-4-5": Price(1.00, 5.00),
    "claude-3-5-haiku": Price(0.80, 4.00),
    # OpenAI
    "gpt-4o-mini": Price(0.15, 0.60),
    "gpt-4o": Price(2.50, 10.00),
    "gpt-4.1-mini": Price(0.40, 1.60),
    "gpt-4.1": Price(2.00, 8.00),
    # Google
    "gemini-2.5-pro": Price(1.25, 10.00),
    "gemini-2.5-flash": Price(0.30, 2.50),
    "gemini-2.0-flash": Price(0.10, 0.40),
}


LOCAL_PROVIDERS = frozenset({"local", "lm-studio", "ollama", "llama-cpp", "vllm"})
"""Providers whose marginal token cost is electricity, not an invoice.

Priced at zero *deliberately* rather than left unpriced: unpriced means "this
was not measured", and for a local model the measurement is known and it is
nothing. A run on a local model should report a confident $0.00, not a warning.
"""


def _configured_prices() -> dict[str, Price]:
    """`PRICES` with any `MODEL_PRICES_JSON` overrides applied.

    Shape: `{"<model-id>": {"input": <usd per mtok>, "output": <usd per mtok>}}`.
    A malformed value is logged and ignored rather than raised: a typo in a
    pricing override must not stop a run from starting.
    """
    raw = os.environ.get("MODEL_PRICES_JSON", "").strip()
    if not raw:
        return PRICES
    try:
        overrides = json.loads(raw)
        merged = dict(PRICES)
        for model, rates in overrides.items():
            merged[str(model).strip().lower()] = Price(
                float(rates["input"]), float(rates["output"])
            )
        return merged
    except Exception:  # noqa: BLE001 - a bad override must not break the run
        logger.warning(
            "MODEL_PRICES_JSON could not be read; using the built-in price table",
            exc_info=True,
        )
        return PRICES


def _lookup(model: str) -> Price | None:
    """The price for `model`, matched by longest key prefix.

    Longest-first so `claude-haiku-4-5` wins over a hypothetical `claude-haiku`
    rather than depending on dict order.
    """
    if not model:
        return None
    needle = model.strip().lower()
    # Providers prefix ids with a vendor segment (`openai/gpt-oss-20b`); compare
    # against both the whole id and the part after the last slash.
    candidates = [needle, needle.rsplit("/", 1)[-1]]
    table = _configured_prices()
    for key in sorted(table, key=len, reverse=True):
        if any(candidate.startswith(key) for candidate in candidates):
            return table[key]
    return None


def price_for(provider: str, model: str) -> Price | None:
    """The price to apply, or `None` when this call cannot honestly be priced.

    A local provider returns a zero `Price` - a measurement, not a guess. An
    unknown model on a paid provider returns `None`, which the accumulator
    records as an unpriced request.
    """
    if (provider or "").strip().lower() in LOCAL_PROVIDERS:
        return Price(0.0, 0.0)
    return _lookup(model)


@dataclass
class RunCost:
    """What one run has spent so far, and how much of it was actually priced."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    successful_requests: int = 0
    priced_requests: int = 0
    unpriced_requests: int = 0
    usd: float = 0.0
    unpriced_models: set[str] = field(default_factory=set)

    @property
    def fully_priced(self) -> bool:
        """Whether `usd` accounts for every call, or only some of them."""
        return self.unpriced_requests == 0

    def summary(self) -> dict[str, Any]:
        return {
            "total_tokens": self.total_tokens,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "successful_requests": self.successful_requests,
            "priced_requests": self.priced_requests,
            "unpriced_requests": self.unpriced_requests,
            "unpriced_models": sorted(self.unpriced_models),
            "fully_priced": self.fully_priced,
            "estimated_cost_usd": round(self.usd, 6),
            "prices_as_of": PRICES_AS_OF,
        }


#: run id -> that run's running total. Guarded by `_LOCK` because a worker runs
#: stages concurrently and callbacks fire from whichever thread made the call.
_RUN_COSTS: dict[str, RunCost] = {}
_LOCK = threading.Lock()


#: Runs whose earlier total this process has already taken from the transcript.
_SEEDED: set[str] = set()


def seed_from_the_transcript(run_id: str | None, provider: str = "", model: str = "") -> None:
    """Take what the run spent before this process from its transcript, once per process.

    `_RUN_COSTS` lives in one process's memory, so a deploy or an orphan
    recovery restarted a run's total at zero and a token or cost ceiling bound
    only the worker segment (Initiative AK). The transcript is the shared
    copy; every call made before this moment is in it, and none made by this
    process is, so the cut is exact. Called when a stage's handler is built,
    before any call of this process for the run.
    """
    if not run_id:
        return
    key = str(run_id)
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    with _LOCK:
        if key in _SEEDED:
            return
        _SEEDED.add(key)
        try:
            earlier = cost_from_transcript(key, provider, model, before=now)
        except Exception:  # noqa: BLE001 - a total that cannot be rebuilt starts at zero, as before
            logger.debug("Could not seed %s from its transcript", key, exc_info=True)
            return
        if earlier is None:
            return
        total = _RUN_COSTS.setdefault(key, RunCost())
        total.prompt_tokens += earlier.prompt_tokens
        total.completion_tokens += earlier.completion_tokens
        total.total_tokens += earlier.total_tokens
        total.successful_requests += earlier.successful_requests
        total.priced_requests += earlier.priced_requests
        total.unpriced_requests += earlier.unpriced_requests
        total.usd += earlier.usd
        total.unpriced_models |= earlier.unpriced_models


def run_cost(run_id: str | None) -> RunCost:
    """This run's total so far; an empty one for a run that has spent nothing.

    Returns a copy, so a caller holding the result cannot see it change under
    them mid-decision - which matters for the ceiling check in `runner`, where
    the number that triggers a pause should be the number reported in the
    pause message.
    """
    if not run_id:
        return RunCost()
    with _LOCK:
        current = _RUN_COSTS.get(str(run_id))
        if current is None:
            return RunCost()
        return RunCost(
            prompt_tokens=current.prompt_tokens,
            completion_tokens=current.completion_tokens,
            total_tokens=current.total_tokens,
            successful_requests=current.successful_requests,
            priced_requests=current.priced_requests,
            unpriced_requests=current.unpriced_requests,
            usd=current.usd,
            unpriced_models=set(current.unpriced_models),
        )


def forget_run(run_id: str | None) -> None:
    """Drop a finished run's total.

    Called when a run reaches a terminal state. Without it the registry grows
    for the life of the worker process, which is the leak `ModelRouter` was
    changed to avoid when it stopped being a process-wide singleton.
    """
    if not run_id:
        return
    with _LOCK:
        _RUN_COSTS.pop(str(run_id), None)
        _SEEDED.discard(str(run_id))


def _record(run_id: str, price: Price | None, model: str, p: int, c: int, t: int) -> None:
    with _LOCK:
        total = _RUN_COSTS.setdefault(run_id, RunCost())
        total.prompt_tokens += p
        total.completion_tokens += c
        total.total_tokens += t
        total.successful_requests += 1
        if price is None:
            total.unpriced_requests += 1
            if model:
                total.unpriced_models.add(model)
        else:
            total.priced_requests += 1
            total.usd += price.usd_for(p, c)


def _record_call_without_usage(run_id: str, price: Price | None, model: str) -> None:
    """Count a call that reported no token usage at all.

    The call still happened, so `successful_requests` counts it: that field
    counts model calls, not model calls that happened to report their size, and
    undercounting it would understate how much work a run did.

    Its *cost*, though, is unknown rather than zero, so on a paid provider it is
    an unpriced request - which keeps it out of the ceiling's arithmetic and
    keeps `fully_priced` false, so nobody reads the total as complete. On a
    local provider the cost is zero whatever the token count was, so there is
    nothing unknown to flag.
    """
    with _LOCK:
        total = _RUN_COSTS.setdefault(run_id, RunCost())
        total.successful_requests += 1
        if price is None:
            total.unpriced_requests += 1
            if model:
                total.unpriced_models.add(model)
        else:
            total.priced_requests += 1


class CostTrackingCallbackHandler(BaseCallbackHandler):
    """Accumulates one run's token usage and cost as its model calls complete.

    Built per run and per stage alongside the transcript handler, in
    `app.server.agent_stream.build_activity_callbacks`, so a run cannot end up
    with a transcript and no accounting.

    `provider` and `model` are the configured defaults. When a response reports
    its own model id - which a fallback route makes different from the
    configured one - that id is priced instead, because the point of the table
    is to price what actually ran.
    """

    def __init__(self, run_id: str, provider: str = "", model: str = "") -> None:
        self.run_id = str(run_id)
        self.provider = provider
        self.model = model
        # Before any call of this process for the run: see `seed_from_the_transcript`.
        seed_from_the_transcript(self.run_id, provider, model)

    @staticmethod
    def _counts(response: LLMResult) -> tuple[int, int, int] | None:
        """Prompt, completion and total tokens, from wherever they arrived.

        A non-streamed response carries them in ``llm_output["token_usage"]``.
        A streamed one leaves ``llm_output`` as ``None`` and puts them on the
        aggregated message instead, so reading only the first place reports
        zero tokens for an entire run - which is what this handler did for
        every call once the models began streaming.
        """
        usage = (response.llm_output or {}).get("token_usage")
        if usage:
            p = usage.get("prompt_tokens", 0)
            c = usage.get("completion_tokens", 0)
            return p, c, usage.get("total_tokens", p + c)

        p = c = t = 0
        found = False
        for generations in response.generations:
            for generation in generations:
                metadata = getattr(getattr(generation, "message", None), "usage_metadata", None)
                if not metadata:
                    continue
                found = True
                p += metadata.get("input_tokens", 0)
                c += metadata.get("output_tokens", 0)
                t += metadata.get("total_tokens", 0)
        return (p, c, t or p + c) if found else None

    def _model_that_answered(self, response: LLMResult) -> str:
        """The model id the response reports, falling back to the configured one."""
        reported = (response.llm_output or {}).get("model_name") or ""
        return str(reported).strip() or self.model

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> Any:  # noqa: ARG002
        # An accounting failure must never cost the run its model call: this is
        # the same rule the transcript handler follows, for the same reason.
        try:
            counts = self._counts(response)
            model = self._model_that_answered(response)
            price = price_for(self.provider, model)
            if counts is None:
                _record_call_without_usage(self.run_id, price, model)
                return
            p_tokens, c_tokens, total = counts
            _record(self.run_id, price, model, p_tokens, c_tokens, total)
        except Exception:  # noqa: BLE001
            logger.debug("Could not record the cost of a model call", exc_info=True)

    def get_summary(self) -> dict[str, Any]:
        """This run's totals. Kept for callers that held the old handler's API."""
        return run_cost(self.run_id).summary()


def _happened_before(entry: dict, moment: str) -> bool:
    """Whether a transcript entry is earlier than `moment`; one with no readable time counts as earlier."""
    from datetime import datetime

    try:
        return datetime.fromisoformat(str(entry.get("at"))) < datetime.fromisoformat(moment)
    except (TypeError, ValueError):
        return True


def cost_from_transcript(
    run_id: str, provider: str = "", model: str = "", *, before: str | None = None
) -> RunCost | None:
    """Rebuild a run's total from its transcript, for a process that did not run it.

    `_RUN_COSTS` is per-process and in memory, so only the Celery worker that
    made the calls can read a run's total from it. In this deployment the API is
    a different container entirely, which meant `/api/runs/{id}` reported no cost
    for every run - the accounting worked and nobody could see it.

    The transcript is the shared copy. It is written to `DATA_DIR/transcripts/`,
    which both containers mount, and every `model_response` line already carries
    the `usage` block this needs. That is plan-part3 §3.3's argument applied
    here: the transcript already holds the numbers, so reduce it rather than
    stand up a second store that can disagree with the first.

    Returns `None` when there is no transcript to read - absent, not zero, for
    the same reason `_cost_summary` distinguishes them.

    **Less precise than the live handler, deliberately.** A `model_response`
    line does not record which model answered, so every call is priced at the
    configured `model`. A run that fell back to a different provider mid-way is
    priced as though it had not. The in-process total is authoritative where it
    exists; this is what an operator gets instead of nothing.
    """
    from app.observability.transcript import read_transcript

    try:
        entries = read_transcript(run_id, {"model_response"})
    except Exception:  # noqa: BLE001 - a missing transcript is not an error here
        logger.debug("Could not read the transcript for %s", run_id, exc_info=True)
        return None
    if before:
        entries = [entry for entry in entries if _happened_before(entry, before)]
    if not entries:
        return None

    price = price_for(provider, model)
    total = RunCost()
    for entry in entries:
        usage = entry.get("usage") or {}
        if not isinstance(usage, dict):
            continue
        p = int(usage.get("input_tokens", 0) or 0)
        c = int(usage.get("output_tokens", 0) or 0)
        total.prompt_tokens += p
        total.completion_tokens += c
        total.total_tokens += int(usage.get("total_tokens", 0) or 0) or (p + c)
        total.successful_requests += 1
        if price is None:
            total.unpriced_requests += 1
            if model:
                total.unpriced_models.add(model)
        else:
            total.priced_requests += 1
            total.usd += price.usd_for(p, c)
    return total if total.successful_requests else None


__all__ = [
    "PRICES",
    "cost_from_transcript",
    "PRICES_AS_OF",
    "CostTrackingCallbackHandler",
    "Price",
    "RunCost",
    "forget_run",
    "price_for",
    "run_cost",
    "seed_from_the_transcript",
]
