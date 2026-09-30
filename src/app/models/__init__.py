"""Shared chat-model factory for Deep Agents role workers.

Every role agent (Product Manager, Tools and Models Architect, Principal
Architect, Scrum Master, Technical Lead, specialists) needs the same provider
connection details: base URL, API key, and model name. Centralizing that
lookup here means each new agent module does not re-implement environment
loading or default handling; only this module changes if the provider setup
changes.
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI

from app.config import Settings, load_settings
from .router import ModelRouter


DEFAULT_MAX_OUTPUT_TOKENS = 32_000
"""Ceiling on what a model may emit in one turn.

Unbounded, one confused turn can consume a whole run. Measured on
one run: asked for its structured response, `specialist_ui_ux_0` instead
wrote the heading `## Structured Response` in prose and kept going for 431,469
characters - roughly 108,000 tokens - over 38 minutes, then failed the stage
because no structured response was ever emitted. Nothing stopped it, because
nothing was asking it to stop.

Sized from the largest *legitimate* output this pipeline produces, not from the
window: the biggest artifact observed is a 51 KB specification written in a
single `write_artifact` call, about 13,000 tokens. 32,000 leaves well over
double that headroom while cutting the pathological case off early.

Raising `CTX_MAX_TOKENS` does not substitute for this. That governs when the
conversation is compacted; it places no bound on a single response, so a larger
window buys a longer ramble rather than a shorter one.
"""


#: Twice the longest legitimate model call measured across the stored runs
#: (`principal_architect` at 162 seconds).
DEFAULT_REQUEST_TIMEOUT_SECONDS = 300.0

#: Below this, real work starts being cancelled and retried.
MIN_REQUEST_TIMEOUT_SECONDS = 180.0


DEFAULT_MIN_TOKENS_PER_SECOND = 30.0
"""The slowest sustained generation rate this deployment should plan for.

A floor, not an average, because it decides how long to *wait*: too pessimistic
costs a little extra patience on a wedge, too optimistic cancels work that was
about to succeed and retries it into the same wall.

Measured on this endpoint over 800-1,200 token completions:

    Qwen3.5-9B                  40.9 tok/s
    Qwen2.5-Coder-7B-128K       51.7 tok/s
    North-Mini-Code-1.0         33.0 tok/s

It was 40.0, taken from the first of those, and the third model broke it - at
33 tok/s a full-length answer needs 394 seconds against the 325 the floor
derived, which is precisely the mismatch this whole mechanism exists to
prevent. A constant measured on one model is not a floor, it is that model's
rate wearing a floor's name.

30.0 sits below every rate observed so far. `MODEL_TOKENS_PER_SECOND` overrides
it for a model slower still, and lowering it only ever lengthens the timeout,
so a wrong value here degrades patience rather than correctness.
"""


def _tokens_per_second() -> float:
    """The generation-rate floor, from the environment or the default."""
    import logging
    import os

    raw = os.environ.get("MODEL_TOKENS_PER_SECOND", "").strip()
    if not raw:
        return DEFAULT_MIN_TOKENS_PER_SECOND
    try:
        value = float(raw)
    except ValueError:
        logging.getLogger(__name__).warning(
            "MODEL_TOKENS_PER_SECOND=%r is not a number; using %s",
            raw, DEFAULT_MIN_TOKENS_PER_SECOND,
        )
        return DEFAULT_MIN_TOKENS_PER_SECOND
    # A rate at or below zero would divide the budget into an infinite wait.
    return value if value > 0 else DEFAULT_MIN_TOKENS_PER_SECOND

#: The largest reply this pipeline has ever legitimately produced: a 51 KB
#: specification written in one `write_artifact` call, about 13,000 tokens.
#:
#: Deliberately NOT `_max_output_tokens()`, which is 32,000. That number is a
#: ceiling on pathology - it exists so one confused turn cannot emit 108,000
#: tokens over 38 minutes, as `specialist_ui_ux_0` did on one run - and
#: sizing the timeout from it means waiting for a ramble nobody wants.
#:
#: Measured on one run, 206 model calls: 185 finished inside 10 seconds,
#: 11 more inside 60, 8 more inside 170, and the longest legitimate call was
#: 141.7 seconds. Nothing at all landed between 170 and 800 seconds. The one
#: call past 800s was a wedge, and its retry succeeded in 2.5 seconds.
#:
#: So the distribution is bimodal and the gap between the two modes is where
#: this timeout belongs: long enough for the largest real answer, short enough
#: that a wedge is caught quickly.
LARGEST_LEGITIMATE_OUTPUT_TOKENS = 13_000


def _time_to_generate_a_full_answer() -> float:
    """Seconds the largest *legitimate* reply would take to produce.

    A timeout shorter than this is not a timeout, it is a length limit wearing
    the wrong name - and one that reports itself as a transport failure and
    retries, rather than as the truncation it is.

    Sized from real output rather than from the pathology ceiling, which is the
    correction to an earlier version of this function. Deriving it from
    `_max_output_tokens()` gave 800 seconds and made the only failure mode that
    actually occurs - a wedged request - take 2.7 times longer to detect, in
    order to permit long answers that the measured distribution says never
    happen.
    """
    return LARGEST_LEGITIMATE_OUTPUT_TOKENS / _tokens_per_second()


def _request_timeout() -> float:
    """Seconds to wait for one model call before giving up on it.

    Set explicitly because the alternative is not "no timeout" but the OpenAI
    SDK's default, `Timeout(connect=5, read=600, write=600, pool=600)` - a
    value nobody here chose and which does not match this deployment.

    Measured on a local llama.cpp server. Twice now a request has wedged: the
    server reported `llamacpp:requests_processing 1` with
    `prompt_tokens_total` AND `tokens_predicted_total` both frozen across a
    25-second sample, while the GPU sat at 88%. A slow generation still moves
    those counters; a wedged one moves neither. One run lost 22 minutes to
    that in `tools_models`, and one run never produced a single event.

    The retry is the cheap part: on one run the identical request
    succeeded in 66 seconds once the first attempt was abandoned.

    300 seconds is roughly twice the longest legitimate call measured across
    the stored runs - `principal_architect` at 162s, everything else well
    under - so it bounds a wedge without touching real work. Override with
    MODEL_REQUEST_TIMEOUT_SECONDS.

    300 seconds alone is not enough, because httpx applies this as a *total*:
    the whole answer arrives in one read, so the number is also a cap on how
    long a reply may be. This deployment generates at about 41 tokens per
    second, so 300 seconds cuts off every reply beyond roughly 12,000 tokens -
    including the 13,000-token specification the pipeline legitimately
    produces, and far short of the 32,000-token ceiling `max_tokens`
    advertises. One run hit exactly that twice in its first hour, each
    costing 300 seconds and a retry that could only time out the same way.

    So the floor is raised to whatever a full-length answer actually needs -
    see `_time_to_generate_a_full_answer`. The two numbers were chosen
    independently and never against each other; this makes one derive from the
    other so they cannot drift apart again.

    Streaming was the better answer and does not work here. On a streamed call
    httpx applies the timeout per-read, so silence still fails fast while
    length stops being bounded at all, and a direct test against this server
    confirmed it: the identical 4,000-token request failed at exactly 60.0s
    unstreamed and returned in 120.9s streamed, with structured output and
    tool calling both intact. But setting `streaming` on the model puts
    `stream: true` in the payload while langchain still routes through the
    non-streaming `_generate`, which is handed an `openai.Stream` it cannot
    read:

        ValueError: Unexpected response type from OpenAI-compatible endpoint.
        Expected a dict or openai.BaseModel, got Stream

    That killed one run on its first model call. It passes when the model
    is built and invoked directly, which is why it reached a deploy; the agent
    invokes a bound model and takes a different path. Revisit only with a
    reproduction through `langchain.agents`, not through a bare model.
    """
    import logging
    import os

    needed = _time_to_generate_a_full_answer()

    raw = os.environ.get("MODEL_REQUEST_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return max(DEFAULT_REQUEST_TIMEOUT_SECONDS, needed)
    try:
        value = float(raw)
    except ValueError:
        logging.getLogger(__name__).warning(
            "MODEL_REQUEST_TIMEOUT_SECONDS=%r is not a number; using %s",
            raw, DEFAULT_REQUEST_TIMEOUT_SECONDS,
        )
        return max(DEFAULT_REQUEST_TIMEOUT_SECONDS, needed)
    # A timeout below the longest legitimate call measured would turn real work
    # into retries, which is the more expensive mistake. An explicit setting is
    # still honoured above the floor, but never below what a full-length answer
    # needs: that is not a preference, it is a guarantee of failure.
    return max(value, MIN_REQUEST_TIMEOUT_SECONDS, needed)


def _max_output_tokens() -> int:
    """Read `MODEL_MAX_OUTPUT_TOKENS` without ever raising at import time."""
    import logging
    import os

    from app.agents.context_budget import ContextBudget

    # Derived from the configured window, so a bigger model gets a bigger reply
    # allowance and a smaller one is held back, without anybody retuning this.
    return ContextBudget.resolve().max_output_tokens


class CompatibleChatOpenAI(ChatOpenAI):
    """`ChatOpenAI` that omits ``name`` on everything except tool messages.

    LangChain serializes a message's ``name`` onto the wire for ``system``,
    ``user`` and ``assistant`` roles. The OpenAI API tolerates that - it is an
    optional participant label - but several OpenAI-*compatible* servers apply
    the stricter reading and reject the whole request:

        400 - messages.2: Value error, "name" is only valid on role="tool" messages.

    That is fatal rather than cosmetic: the request never reaches the model, so
    the stage fails outright. Nothing here needs the field either - deepagents
    sets it to the agent's own name as bookkeeping, and no prompt in this
    workflow addresses a named participant - so it is dropped on the way out
    rather than being made a setting nobody would know to turn on.

    ``_get_request_payload`` is the single place the request dict is assembled,
    so overriding it covers invoke, stream, batch, tool calls and structured
    output alike.
    """

    def _get_request_payload(self, input_, *, stop=None, **kwargs):  # type: ignore[override]
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        for message in payload.get("messages", []):
            if isinstance(message, dict) and message.get("role") != "tool":
                message.pop("name", None)
        try:
            with_the_reasoning_carried(
                self._convert_input(input_).to_messages(), payload.get("messages") or []
            )
        except Exception:  # noqa: BLE001 - a missing note must never cost the call
            pass
        return payload

    def _create_chat_result(self, response, generation_info=None):  # type: ignore[override]
        """The result, with the reasoning the server returned kept on each message.

        `ChatOpenAI` reads `content` and `tool_calls` and drops a server's
        `reasoning_content` on the floor. See `with_the_reasoning_carried` for why
        it is needed on the next request.
        """
        result = super()._create_chat_result(response, generation_info)
        try:
            data = response if isinstance(response, dict) else response.model_dump(warnings=False)
            for generation, choice in zip(result.generations, data.get("choices") or []):
                message = (choice or {}).get("message") or {}
                reasoning = message.get("reasoning_content") or message.get("reasoning")
                if isinstance(reasoning, str) and reasoning.strip():
                    generation.message.additional_kwargs[REASONING_FIELD] = (
                        reasoning.strip()[-REASONING_CARRIED_CHARS:]
                    )
        except Exception:  # noqa: BLE001 - keeping reasoning is an aid, never a failure
            pass
        return result


#: Where a reply's reasoning is kept on its message.
REASONING_FIELD = "reasoning_content"

#: How much of one reply's reasoning is kept and carried forward - its end,
#: where a model states what it has decided to do next.
REASONING_CARRIED_CHARS = 1_500

#: How many of the most recent tool-calling replies carry theirs.
REPLIES_CARRYING_REASONING = 4


def with_the_reasoning_carried(messages: list[Any], dicts: list[dict]) -> None:
    """Put each recent tool-calling reply's reasoning back where the model will read it.

    A reasoning model thinks before every tool call, and in an agent loop that
    thinking is the plan: which file next, what the last result meant. OpenAI's
    guide for its open-weight reasoning models says the previous chain of
    thought must be passed back while the model is calling tools. Nothing here
    did. `ChatOpenAI` discarded it, and an LM Studio server ignores it in every
    reasoning field - measured: a plan placed in `reasoning_content`,
    `reasoning` or `thinking` was invisible to the model, while the same plan in
    the assistant message's `content` was read back word for word. The chat
    template renders a tool-calling message's `content` as that model's
    analysis channel.

    On one run 82% of every token the model produced was reasoning, all of it
    thrown away before the next call; 26% of that day's tool calls were a read,
    listing or search the same stage had already made with the same arguments.

    So the end of each of the last few tool-calling replies' reasoning goes into
    that reply's `content` on the way out, where it is empty. Changed in the
    request only - the stored conversation is untouched, so nothing that reads a
    reply's content as an answer ever sees it. Bounded in length and in how many
    replies carry it. A server that returns no reasoning is unaffected.
    """
    from langchain_core.messages import AIMessage

    carrying = [
        index
        for index, message in enumerate(messages)
        if isinstance(message, AIMessage)
        and message.tool_calls
        and not str(message.content or "").strip()
        and message.additional_kwargs.get(REASONING_FIELD)
    ]
    for index in carrying[-REPLIES_CARRYING_REASONING:]:
        if index >= len(dicts):
            continue
        outgoing = dicts[index]
        if isinstance(outgoing, dict) and outgoing.get("role") == "assistant" and not outgoing.get("content"):
            outgoing["content"] = str(messages[index].additional_kwargs[REASONING_FIELD])


def _fallback_model(env_var: str, default: str) -> str:
    """Fallback model ids come from configuration, not from source.

    They were hardcoded, and the Anthropic one had aged out - a provider
    deprecation should be a config change, not a code change.
    """
    import os

    return os.environ.get(env_var, default).strip() or default


def _runtime_settings() -> Settings:
    """Settings including admin overrides, falling back to the environment.

    Imported lazily and guarded: this module is used by the CLI and by tests
    that have no database, and a model factory must not start requiring one.
    """
    try:
        from app.server.runtime_settings import effective_settings

        return effective_settings()
    except Exception:  # noqa: BLE001 - the environment is still a valid config
        return load_settings()


def build_default_chat_model(settings: Settings | None = None) -> BaseChatModel:
    """Construct the chat model role agents use, from validated settings.

    Passing a real `ChatOpenAI` instance to `create_deep_agent` (instead of a
    bare "openai:<model>" string) means the client is built from our own
    validated `Settings`, so behavior does not depend on whether some other
    part of the process happened to load `.env` first.
    """
    # `effective_settings` is `load_settings` plus anything an administrator has
    # changed through the settings API. Reading the bare environment here meant a
    # corrected model URL never reached the worker that actually calls the model.
    resolved_settings = settings or _runtime_settings()

    # Thinking is measured against the same reply ceiling as everything else,
    # so the policy is resolved once here and handed to whichever client is
    # built. See `app.agents.thinking` for why on/off and effort are separate.
    from app.agents.thinking import ThinkingPolicy

    thinking = ThinkingPolicy.resolve(
        mode=getattr(resolved_settings, "thinking_mode", "default"),
        effort=getattr(resolved_settings, "thinking_effort", None),
        max_output_tokens=_max_output_tokens(),
    )
    # `local` is the llama.cpp chat-template switch: an OpenAI-compatible
    # server reached through a base URL. A hosted OpenAI endpoint neither needs
    # it nor accepts it.
    speaks_llama_cpp = bool(resolved_settings.openai_base_url)

    primary = None
    fallback = None

    if resolved_settings.llm_provider == "anthropic":
        primary = ChatAnthropic(
            api_key=resolved_settings.anthropic_api_key,
            model=resolved_settings.model_name,
            max_retries=3,
            timeout=_request_timeout(),
            max_tokens=_max_output_tokens(),
            **thinking.anthropic_arguments(),
        )
        if resolved_settings.openai_api_key:
            fallback = CompatibleChatOpenAI(
                api_key=resolved_settings.openai_api_key,
                model=_fallback_model("OPENAI_FALLBACK_MODEL", "gpt-4o-mini"),
                max_retries=3,
            timeout=_request_timeout(),
                max_tokens=_max_output_tokens(),
            )
    elif resolved_settings.llm_provider == "gemini":
        primary = ChatGoogleGenerativeAI(
            api_key=resolved_settings.google_api_key,
            model=resolved_settings.model_name,
            max_retries=3,
            timeout=_request_timeout(),
            max_output_tokens=_max_output_tokens(),
        )
        if resolved_settings.openai_api_key:
            fallback = CompatibleChatOpenAI(
                api_key=resolved_settings.openai_api_key,
                model=_fallback_model("OPENAI_FALLBACK_MODEL", "gpt-4o-mini"),
                max_retries=3,
            timeout=_request_timeout(),
                max_tokens=_max_output_tokens(),
            )
    else:
        # Defaults to OpenAI or Local
        primary = CompatibleChatOpenAI(
            base_url=resolved_settings.openai_base_url,
            api_key=resolved_settings.openai_api_key,
            model=resolved_settings.model_name,
            max_retries=3,
            timeout=_request_timeout(),
            max_tokens=_max_output_tokens(),
            **thinking.openai_arguments(local=speaks_llama_cpp),
        )
        # If it's a local model that fails, fallback to Anthropic if available
        if resolved_settings.openai_base_url and resolved_settings.anthropic_api_key:
             fallback = ChatAnthropic(
                api_key=resolved_settings.anthropic_api_key,
                model=_fallback_model("ANTHROPIC_FALLBACK_MODEL", "claude-haiku-4-5-20251001"),
                max_retries=3,
            timeout=_request_timeout(),
                max_tokens=_max_output_tokens(),
             )

    models = [{"name": "primary", "model": primary}]
    if fallback:
        models.append({"name": "fallback", "model": fallback})

    # A per-configuration router rather than one process-wide singleton that
    # every agent construction reset: two runs with different provider settings
    # in the same worker used to overwrite each other's models.
    router = ModelRouter.for_configuration(resolved_settings, models)
    return router.get_healthy_model()


__all__ = ["build_default_chat_model"]
