"""How much room a model gets to think, and how each provider is told.

Reasoning models can be asked to spend tokens deliberating before they answer.
Providers expose that differently, and the difference is not cosmetic:

- OpenAI-compatible servers, including the local `llama-server`, take
  `reasoning_effort` ("low" | "medium" | "high").
- llama.cpp additionally gates thinking on the chat template, through
  `chat_template_kwargs={"enable_thinking": ...}`. Measured against this
  deployment's Qwen3.6 server: with it true the reply carries
  `reasoning_content`, with it false it does not, and `reasoning_effort` is
  accepted either way.
- Anthropic takes `thinking={"type": "enabled", "budget_tokens": N}` and
  requires `max_tokens` to exceed N.
- Google takes a thinking budget in tokens.

So "on/off" and "how hard" are separate settings, because on this deployment
they are separate request fields.

Thinking tokens are *output* tokens. They come out of the same budget every
other reply is measured against, which is why the budget here is derived from
`ContextBudget.max_output_tokens` rather than being a free-standing number: a
thinking budget larger than the reply ceiling is a request the provider
rejects, and one that consumes the whole ceiling leaves nothing to answer with.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any, Literal

logger = logging.getLogger(__name__)

ThinkingEffort = Literal["low", "medium", "high"]

ThinkingMode = Literal["default", "on", "off"]
"""Three states, because two were not enough and the difference broke a run.

`off` is not the absence of `on`. A server carries its own default - this
deployment's llama-server is launched with
`--chat-template-kwargs {"enable_thinking": true}` - so sending nothing is
"whatever the server was configured to do", which is a third answer.

Measured on one run, the first run after this feature shipped with a
two-state `enabled: bool` defaulting to False: the client began sending
`enable_thinking: False` explicitly, turning off reasoning the model had been
using all along. The product manager wrote its artifact, then returned its
summary as prose instead of the structured response, and the next stage died
on `KeyError: 'product_intake'`.

So `default` sends nothing and is the default: shipping a new setting must not
change how an existing deployment behaves.
"""

DEFAULT_MODE: ThinkingMode = "default"

#: Fraction of the reply ceiling each effort level may spend on thinking.
#: The remainder is what the model has left to actually answer with.
EFFORT_FRACTIONS: dict[str, float] = {"low": 0.25, "medium": 0.5, "high": 0.75}

DEFAULT_EFFORT: ThinkingEffort = "medium"

#: Anthropic rejects a thinking budget below this.
MIN_THINKING_TOKENS = 1_024

#: What must remain for the answer itself once thinking has taken its share.
MIN_ANSWER_TOKENS = 2_048


def normalise_mode(value: object) -> ThinkingMode:
    """The mode, tolerating the booleans and strings a stored setting may hold."""
    if isinstance(value, bool):
        return "on" if value else "default"
    candidate = str(value or "").strip().lower()
    if candidate in {"on", "true", "1", "yes", "enabled"}:
        return "on"
    if candidate in {"off", "false", "0", "no", "disabled"}:
        return "off"
    return "default"


def normalise_effort(value: str | None) -> ThinkingEffort:
    """The effort level, or the default when the value is unrecognised."""
    candidate = (value or "").strip().lower()
    return candidate if candidate in EFFORT_FRACTIONS else DEFAULT_EFFORT  # type: ignore[return-value]


def thinking_budget_tokens(effort: str | None, max_output_tokens: int) -> int:
    """How many output tokens this effort level may spend on thinking.

    Clamped so the model always keeps `MIN_ANSWER_TOKENS` to reply with, and
    returns 0 when the reply ceiling is too small to divide at all - which the
    caller reads as "do not enable thinking", a better outcome than a request
    the provider refuses.
    """
    ceiling = max(int(max_output_tokens or 0), 0)
    if ceiling < MIN_THINKING_TOKENS + MIN_ANSWER_TOKENS:
        return 0
    wanted = int(ceiling * EFFORT_FRACTIONS[normalise_effort(effort)])
    return max(MIN_THINKING_TOKENS, min(wanted, ceiling - MIN_ANSWER_TOKENS))


@dataclass(frozen=True)
class ThinkingPolicy:
    """The thinking configuration for one model, ready to hand to a client."""

    mode: ThinkingMode
    effort: ThinkingEffort
    budget_tokens: int

    @property
    def enabled(self) -> bool:
        return self.mode == "on"

    @classmethod
    def resolve(
        cls, *, mode: object = DEFAULT_MODE, effort: str | None = None, max_output_tokens: int = 0
    ) -> "ThinkingPolicy":
        chosen = normalise_mode(mode)
        level = normalise_effort(effort)
        budget = thinking_budget_tokens(level, max_output_tokens) if chosen == "on" else 0
        # A budget of zero means the reply ceiling could not accommodate
        # thinking at all. Fall back to the server's own default rather than
        # sending a request the provider rejects - or silently disabling
        # reasoning the deployment was relying on.
        if chosen == "on" and budget <= 0:
            chosen = "default"
        return cls(mode=chosen, effort=level, budget_tokens=budget)

    def openai_arguments(self, *, local: bool) -> dict:
        """Client keyword arguments for an OpenAI-compatible endpoint.

        `local` adds the llama.cpp chat-template switch, which is what actually
        turns thinking on for that server; `reasoning_effort` alone leaves the
        template's own default in force.
        """
        if self.mode == "default":
            # Nothing at all. Whatever the server was launched with stands.
            return {}
        if self.mode == "off":
            return (
                {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}
                if local
                else {}
            )
        arguments: dict = {"reasoning_effort": self.effort}
        if local:
            arguments["extra_body"] = {"chat_template_kwargs": {"enable_thinking": True}}
        return arguments

    def anthropic_arguments(self) -> dict:
        """Client keyword arguments for Anthropic."""
        if not self.enabled:
            return {}
        return {"thinking": {"type": "enabled", "budget_tokens": self.budget_tokens}}

    def describe(self) -> str:
        if self.mode == "default":
            return "Thinking follows whatever the model server was configured to do."
        if self.mode == "off":
            return "Thinking is off; the model answers directly."
        return (
            f"Thinking is on at {self.effort} effort, up to {self.budget_tokens:,} "
            "tokens of the reply budget."
        )


def without_reasoning(model: Any) -> Any:
    """A copy of `model` whose every reply is an answer, with no reasoning first; or `model`.

    For the stages fast delivery (`app.delivery`) runs without reasoning: the
    ones that build and fix from a specification that has decided what they
    write. One run's build model spent half of 2.8 million output tokens
    reasoning, and lost whole replies to it at the start of most stages.
    The switch is `answering_without_reasoning`'s, measured per endpoint; a
    client that cannot be switched per call is returned as it is.
    """
    switch = answering_without_reasoning(model).get("extra_body")
    if not switch:
        return model
    try:
        return model.model_copy(update={"extra_body": switch})
    except Exception:  # noqa: BLE001 - a model that cannot be copied reasons as configured
        return model


def answering_without_reasoning(model: object) -> dict:
    """Per-call model settings that make one reply an answer, not more reasoning.

    For the call after a reply that reasoned until it was cut off. Taking the
    tools away and asking for the answer is not enough on its own: measured on
    one run's `test_round_1`, the call after that notice reasoned through the
    whole 25,000-token budget again, with the thinking mode left at `default`
    and the server launched with thinking on. So the run failed on the second
    spiral, with nothing else tried.

    Only an OpenAI-compatible server reached through a base URL can be switched
    per call. Servers differ in which switch they read, so both are sent in
    `extra_body`, merged over whatever the client already sends there: the
    llama.cpp chat-template flag, and the chat-completions field
    `reasoning_effort`. Measured against an LM Studio server running a GLM
    model: it ignored the template flag entirely - one run's stack selector
    reasoned through the whole 25,000-token budget on the switched-off call
    too - and answered a probe in two tokens with `reasoning_effort: "none"`.
    Which effort value does that depends on the model, so it is measured, once
    per endpoint and model (`least_reasoning_effort`). A server that rejects the
    field is asked again without it (`without_the_effort_field`), so no
    deployment is worse off for it.

    Anthropic ignores a per-call `thinking` override, but it does not need one:
    its thinking budget is always set below the reply ceiling, so a reply there
    always has room left to answer. Every other client gets nothing, rather
    than a field it may reject.
    """
    base = getattr(model, "openai_api_base", None)
    if not base:
        return {}
    from app.models.endpoints import is_self_hosted

    # The template switch is a self-hosted server's; a hosted API may reject it.
    extra = _without_the_template_switch(model) if is_self_hosted(base) else dict(getattr(model, "extra_body", None) or {})
    effort = least_reasoning_effort(model)
    if effort:
        extra[_EFFORT_FIELD] = effort
    return {"extra_body": extra}




def _without_the_template_switch(model: object) -> dict:
    """The client's own `extra_body`, with the chat-template thinking flag off."""
    extra = dict(getattr(model, "extra_body", None) or {})
    template = dict(extra.get("chat_template_kwargs") or {})
    template["enable_thinking"] = False
    extra["chat_template_kwargs"] = template
    return extra


#: The chat-completions field that sets how hard a model reasons, and the value
#: that asks for no reasoning at all.
_EFFORT_FIELD = "reasoning_effort"
NO_REASONING_EFFORT = "none"

#: The values tried for the call that must answer, fewest reasoning tokens
#: intended first.
#:
#: Which one a server honours depends on the model behind it, not on the
#: server. Measured on one LM Studio server: a GLM model answered a probe in
#: two tokens with "none"; `openai/gpt-oss-20b`, whose own format knows only
#: low, medium and high, treated "none" as no instruction at all and reasoned
#: 384-1,990 tokens on a small puzzle, against 64-70 with "low". So the
#: switched-off call after a lead's 25,000-token spiral reasoned another 12,372
#: tokens and took 106 seconds.
_EFFORTS_TO_TRY = (NO_REASONING_EFFORT, "low")

#: A small question that a reasoning model does reason about, so the replies
#: differ by how much each effort value restrained it. Its answer is one number
#: whatever the effort, so a difference in output tokens is reasoning.
_PROBE_QUESTION = (
    "A farmer has 17 sheep; all but 9 run away; then he buys twice as many as "
    "remain and sells a third of the total. How many sheep? Reply with the "
    "number only."
)

#: The probe's reply ceiling. An effort value that is ignored reasons past it,
#: so it only has to be well above what an honoured one spends.
_PROBE_REPLY_TOKENS = 512

#: At or below this, "none" is taken as honoured and nothing else is tried.
_HONOURED_TOKENS = 64

_least_effort: dict[tuple[str, str], str | None] = {}
_least_effort_lock = threading.Lock()


class _Unmeasured(Exception):
    """The probe could not tell how much a reply reasoned."""


def least_reasoning_effort(model: object) -> str | None:
    """The `reasoning_effort` value that makes this model reason least, or None.

    Measured once per endpoint and model in a process, by asking the probe
    question with each value in `_EFFORTS_TO_TRY`. A value the server refuses
    (400/422) is skipped; None means it refused them all, so the field is not
    sent. A server that answers without reporting token usage gets "none", as
    before. When the server did not answer at all the result is also "none",
    but not remembered, so the next call measures again.
    """
    key = (
        str(getattr(model, "openai_api_base", "") or ""),
        str(getattr(model, "model_name", "") or ""),
    )
    with _least_effort_lock:
        if key in _least_effort:
            return _least_effort[key]
        try:
            chosen = _the_least_of(model)
        except _Unmeasured:
            return NO_REASONING_EFFORT
        _least_effort[key] = chosen
    logger.info(
        "Reasoning switch for %s at %s: reasoning_effort=%s", key[1], key[0], chosen
    )
    return chosen


def _the_least_of(model: object) -> str | None:
    fewest: tuple[int, str] | None = None
    for effort in _EFFORTS_TO_TRY:
        try:
            spent = _reasoning_spent(model, effort)
        except Exception as error:  # noqa: BLE001 - a probe must never fail a call
            if the_server_refused_the_request(error):
                continue
            raise _Unmeasured(str(error)) from error
        if spent is None:
            # It answers but does not say what the answer cost: nothing to
            # compare, and no reason to ask again.
            return NO_REASONING_EFFORT
        if effort == NO_REASONING_EFFORT and spent <= _HONOURED_TOKENS:
            return effort
        if fewest is None or spent < fewest[0]:
            fewest = (spent, effort)
    return fewest[1] if fewest else None


def _reasoning_spent(model: object, effort: str) -> int | None:
    """Output tokens the probe question costs with `effort`, or None when the
    reply does not report them."""
    extra = _without_the_template_switch(model)
    extra[_EFFORT_FIELD] = effort
    reply = model.invoke(  # type: ignore[attr-defined]
        [("human", _PROBE_QUESTION)], extra_body=extra, max_tokens=_PROBE_REPLY_TOKENS
    )
    usage = getattr(reply, "usage_metadata", None) or {}
    spent = usage.get("output_tokens")
    return spent if isinstance(spent, int) else None


def the_server_refused_the_request(error: BaseException) -> bool:
    """Whether `error` is the server rejecting the request as malformed (400/422)."""
    status = getattr(error, "status_code", None)
    if status is None:
        status = getattr(getattr(error, "response", None), "status_code", None)
    return status in (400, 422)


def without_the_effort_field(settings: dict) -> dict | None:
    """`settings` without the `reasoning_effort` that `answering_without_reasoning`
    added, or None when it carries none - for a server that refused the request.
    """
    extra = dict((settings or {}).get("extra_body") or {})
    if _EFFORT_FIELD not in extra:
        return None
    extra.pop(_EFFORT_FIELD)
    return {**settings, "extra_body": extra}


__all__ = [
    "NO_REASONING_EFFORT",
    "answering_without_reasoning",
    "least_reasoning_effort",
    "without_the_effort_field",
    "DEFAULT_EFFORT",
    "DEFAULT_MODE",
    "ThinkingMode",
    "normalise_mode",
    "EFFORT_FRACTIONS",
    "ThinkingEffort",
    "ThinkingPolicy",
    "normalise_effort",
    "the_server_refused_the_request",
    "thinking_budget_tokens",
]
