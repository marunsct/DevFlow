"""Shared chat-model factory for Deep Agents role workers.

Every role agent (Product Manager, Tools and Models Architect, Principal
Architect, Scrum Master, Technical Lead, specialists) needs the same provider
connection details: base URL, API key, and model name. Centralizing that
lookup here means each new agent module does not re-implement environment
loading or default handling; only this module changes if the provider setup
changes.
"""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI

from app.config import Settings, load_settings
from .router import ModelRouter


DEFAULT_MAX_OUTPUT_TOKENS = 32_000
"""Ceiling on what a model may emit in one turn.

Unbounded, one confused turn can consume a whole run. Measured on
run-0b55ad49: asked for its structured response, `specialist_ui_ux_0` instead
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


def _request_timeout() -> float:
    """Seconds to wait for one model call before giving up on it.

    Set explicitly because the alternative is not "no timeout" but the OpenAI
    SDK's default, `Timeout(connect=5, read=600, write=600, pool=600)` - a
    value nobody here chose and which does not match this deployment.

    Measured on a local llama.cpp server. Twice now a request has wedged: the
    server reported `llamacpp:requests_processing 1` with
    `prompt_tokens_total` AND `tokens_predicted_total` both frozen across a
    25-second sample, while the GPU sat at 88%. A slow generation still moves
    those counters; a wedged one moves neither. run-6412366b lost 22 minutes to
    that in `tools_models`, and run-caae7e32 never produced a single event.

    The retry is the cheap part: on run-6412366b the identical request
    succeeded in 66 seconds once the first attempt was abandoned.

    300 seconds is roughly twice the longest legitimate call measured across
    the stored runs - `principal_architect` at 162s, everything else well
    under - so it bounds a wedge without touching real work. Override with
    MODEL_REQUEST_TIMEOUT_SECONDS.

    This number only bounds a wedge because `CompatibleChatOpenAI` streams.
    Unstreamed, httpx reads it as a total and it becomes a cap on how long an
    answer may be: at this deployment's ~41 tokens per second it would cut off
    every reply longer than about 12,000 tokens, including the 13,000-token
    specification this pipeline legitimately produces. Streamed, it is the
    longest silence tolerated between chunks, which is the question actually
    being asked. Run-f0630b10 hit the unstreamed version twice in its first
    hour, each costing 300 seconds and a retry that could only time out again.
    """
    import logging
    import os

    raw = os.environ.get("MODEL_REQUEST_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return DEFAULT_REQUEST_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        logging.getLogger(__name__).warning(
            "MODEL_REQUEST_TIMEOUT_SECONDS=%r is not a number; using %s",
            raw, DEFAULT_REQUEST_TIMEOUT_SECONDS,
        )
        return DEFAULT_REQUEST_TIMEOUT_SECONDS
    # A timeout below the longest legitimate call measured would turn real work
    # into retries, which is the more expensive mistake.
    return max(value, MIN_REQUEST_TIMEOUT_SECONDS)


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

    It also streams every request, which is what makes the request timeout mean
    what this module wants it to mean. See ``streaming`` below.
    """

    streaming: bool = True
    """Stream every request, including ``invoke``.

    Not for incremental display - nothing here consumes chunks. It is the only
    way to have one timeout answer two different questions.

    On a non-streaming call httpx applies the timeout as a *total*: the whole
    answer arrives in one read, so a long generation trips it by construction.
    `max_output_tokens` is 32,000 and this deployment generates at about 41
    tokens per second, so a full-length answer needs roughly thirteen minutes
    against a 300-second timeout - and even the largest *legitimate* output
    measured here, a 51 KB specification of about 13,000 tokens, needs 318
    seconds. Both fail, then retry three times and fail again, because a
    request that timed out for being long times out the same way when repeated.

    On a streaming call the same number is a *per-read* timeout: a response
    delivering any chunk inside the window never trips it. Measured against
    this server at a 60-second timeout, the identical 4,000-token request
    failed at exactly 60.0s unstreamed and returned in 120.9s streamed.

    That is why this is better than simply raising the timeout. The 300 seconds
    exists to catch a *wedged* server - twice observed reporting
    `llamacpp:requests_processing 1` with both token counters frozen - and a
    timeout long enough for a thirteen-minute answer would take thirteen
    minutes to notice a wedge. Streaming separates the two questions that one
    number was being asked: silence still fails fast, length no longer fails at
    all.

    Declared on the class rather than at each construction site so a fourth
    site cannot be added without it.
    """

    stream_usage: bool = True
    """Ask for token counts in the stream.

    Without it `usage_metadata` comes back `None` on every streamed response
    and `CostTrackingCallbackHandler` silently reports zero tokens for the
    whole run. Verified against this server: streaming without it reported
    0 prompt and 0 completion tokens for a call the unstreamed path counted
    at 19 and 10.
    """

    def _get_request_payload(self, input_, *, stop=None, **kwargs):  # type: ignore[override]
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        for message in payload.get("messages", []):
            if isinstance(message, dict) and message.get("role") != "tool":
                message.pop("name", None)
        return payload


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
