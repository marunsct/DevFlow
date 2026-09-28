"""Framework-specific instructions, injected into whichever stack a run chose.

The harness's own prompts have to hold for every language and framework, so the
advice that only makes sense for one - how this ecosystem manages dependencies,
what its concurrency model forbids, which of its defaults are unsafe - cannot
live in them. This middleware reads the stack the run selected and appends the
instructions for it, from a store keyed by framework name.

A framework the store has never seen gets its instructions written by the model
and saved, so the next run that selects it starts with them. That is what keeps
the feature agnostic: nothing here has a list of supported technologies, and
nothing has to be taught one before a run can use it.

Two things about the first implementation were wrong and are fixed here.

It appended to `messages[0]`, expecting a `{"role": "system"}` dict. A
middleware's `ModelRequest.messages` explicitly *excludes* the system prompt -
the reference says so, and the prompt is `request.system_message` - so the
condition was never true and not one instruction ever reached a model. The
feature was inert.

And it extracted the stack on every model call, which meant one extra model call
to read `technology_stack.md`, plus one per unrecognised framework, *per call the
agent made*. A stage that makes 160 calls paid for 160 extractions of a document
that changes at most once a run. The extraction is now cached against the file's
own content, so it happens once per distinct stack per process, and the run pays
for the frameworks it has, once.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
from pathlib import Path
from typing import Any, Callable, List

from app.plugins.registry import get_plugin_instructions

logger = logging.getLogger(__name__)

#: What a framework name may look like. The extraction asks a model for a
#: comma-separated list and a model sometimes answers with a sentence, an
#: apology or a heading - and every one of those became a row in the store,
#: keyed by the sentence, with instructions generated *for* the sentence.
#: A name here is short, lowercase and has no sentence punctuation.
_A_FRAMEWORK_NAME = re.compile(r"^[a-z0-9][a-z0-9 .+#_-]{0,29}$")

#: A stack names a handful of things. More than this from one document means the
#: answer was not a list of frameworks, and each surplus entry would cost
#: another generation call.
_MOST_FRAMEWORKS = 12

#: Keywords already worked out, keyed by the digest of the stack document they
#: came from. The document is what the answer depends on, so the digest is the
#: right key: a run that rewrites its stack gets a fresh extraction, and a run
#: that does not pays once however many calls its agents make.
_CACHE: dict[str, List[str]] = {}

#: Failed attempts per stack document. Only successes were cached, so a model
#: endpoint that is down was dialled again on every model call of every stage -
#: 142 attempts in one worker, every one of them the same refused connection.
_FAILURES: dict[str, int] = {}

#: How many times one stack document is tried before this gives up on it. Two,
#: so a single blip is survived and a host that is down costs two calls rather
#: than one per model call for the rest of the run.
_ATTEMPTS_BEFORE_GIVING_UP = 2

_CACHE_LOCK = threading.Lock()


def _where_the_extraction_model_points() -> str:
    """The endpoint this would call, for a log line that names the real fault.

    Never raises: it is only ever used to describe a failure.
    """
    try:
        from app.models import _runtime_settings

        return str(_runtime_settings().openai_base_url or "the default endpoint")
    except Exception:  # noqa: BLE001 - a description must not fail a stage
        return "an endpoint that could not be resolved"


def _text_of(response: Any) -> str:
    """One model reply as text, whatever shape the provider returned.

    `content` is a string from most providers and a list of content blocks from
    some. `"".join` on the list of dicts raises, and the bare `except` around
    the old call site turned that into "no frameworks detected" - a silent,
    total loss of the feature on any provider that blocks its content.
    """
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "\n".join(parts)
    return str(content or "")


def _extraction_model() -> Any:
    """The chat model the run is actually using, for the two auxiliary calls.

    Built from `_runtime_settings`, not `load_settings`. `load_settings` is a pure
    function of the environment and does not see what an administrator has
    changed, and `effective_settings` says so in its own docstring: "This is what
    every model-building path should call."

    This path did not, and the two disagreed in production. The operator's
    runtime settings pointed at `http://host.docker.internal:8888/v1`, which was
    serving; the environment still held `http://host.docker.internal:1234/v1`,
    which answered `ECONNREFUSED`. So every agent call worked and every call from
    here failed. Across the worker's whole lifetime:

        142  Could not resolve framework instructions for this stack
          0  Framework instructions resolved for this stack

    Dynamic framework instructions had therefore never once been injected in this
    deployment - not degraded, inert - and nothing said so except a warning that
    named a stack rather than a host.

    Reuses `app.models._runtime_settings`, which already falls back to the
    environment when there is no database, so the CLI and the tests are unchanged.
    """
    from langchain_openai import ChatOpenAI

    from app.models import _runtime_settings

    settings = _runtime_settings()
    return ChatOpenAI(
        model=settings.model_name,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        temperature=0,
    )


def _framework_names(reply: str) -> List[str]:
    """The framework names in a comma-separated reply, junk discarded."""
    names: List[str] = []
    for candidate in reply.replace("\n", ",").split(","):
        # Stripped in one pass over both sets: `.strip().strip("-")` leaves
        # the space in "- react" behind, and " react" matches nothing.
        name = candidate.strip(" \t`*-.\u2022\u00b7").lower()
        if not name or not _A_FRAMEWORK_NAME.match(name) or name in names:
            continue
        names.append(name)
        if len(names) >= _MOST_FRAMEWORKS:
            break
    return names


def _extract_stack_keywords(repo_root: str) -> List[str]:
    """The frameworks this run's stack mandates, with instructions for each.

    Cached on the stack document's content. Returns `[]` when there is no stack
    document yet - the early stages of a run have not chosen one - and on any
    failure, because a missing hint must never be the thing that fails a stage.
    """
    stack_file = Path(repo_root) / "docs" / "technology_stack.md"
    if not stack_file.is_file():
        return []

    try:
        content = stack_file.read_text(encoding="utf-8")
    except OSError:
        return []

    key = hashlib.sha256(content.encode("utf-8", "replace")).hexdigest()
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        failures = _FAILURES.get(key, 0)
    if cached is not None:
        return list(cached)
    if failures >= _ATTEMPTS_BEFORE_GIVING_UP:
        # No model call. This is the rung that was missing: the cache held only
        # successes, so an endpoint that is down was dialled again for every
        # model call of every stage for the rest of the run.
        return []

    keywords: List[str] = []
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from app.server.plugin_store import PluginStore

        model = _extraction_model()
        reply = model.invoke([
            SystemMessage(content=(
                "You are a tech stack analyzer. Read the provided technology stack "
                "document and return ONLY a comma-separated list of the core "
                "programming languages and frameworks it mandates (for example: "
                "react, typescript, python, postgres). Do not include tools or "
                "generic terms. Output exactly the comma-separated list."
            )),
            HumanMessage(content=content),
        ])
        detected = _framework_names(_text_of(reply))
        if not detected:
            logger.info("No frameworks could be read from the stack document")

        store = PluginStore.shared()
        known = set(store.get_all_framework_names())
        for framework in detected:
            if framework not in known:
                # Nothing maintains a list of supported frameworks, so the ones
                # that are not in the store get their instructions written now
                # and kept. This is the call that made the uncached version
                # expensive, and it is the whole point of the feature.
                #
                # The request carries a user message. It used to be a system
                # message alone, and an OpenAI-compatible local server answers
                # that with 400 "At least one non-system message is required" -
                # so every stack naming a framework the seed does not cover, a
                # vanilla JavaScript page included, failed here.
                #
                # And one framework's failure costs only that framework. The
                # exception used to reach the outer handler, which discarded
                # every framework found, counted an attempt, and after two gave
                # up for the run: an unseeded `javascript` cost the run its
                # instructions for every other framework in its stack as well.
                try:
                    generated = _text_of(model.invoke([
                        SystemMessage(content=(
                            "You write concise, strict engineering instructions for "
                            "coding agents. Output only the instructions."
                        )),
                        HumanMessage(content=(
                            f"Generate 4 bullet points of strict software engineering best "
                            f"practices for the '{framework}' framework or language. Focus on "
                            f"concurrency, security and architecture."
                        )),
                    ])).strip()
                except Exception:  # noqa: BLE001 - one framework, not the stack
                    logger.warning(
                        "Could not generate instructions for '%s'; continuing without them",
                        framework,
                        exc_info=True,
                    )
                    continue
                if generated:
                    store.update_instructions(framework, generated)
                else:
                    # Nothing generated is not an empty instruction set: storing
                    # "" would mark the framework known and stop it ever being
                    # generated again.
                    continue
            keywords.append(framework)
    except Exception:  # noqa: BLE001 - an absent hint beats a failed stage
        # Counted, and given up on. Only successes were cached, so a failure was
        # retried on every model call of the run - which is how one unreachable
        # host produced 142 attempts and 142 tracebacks in a single worker.
        # Two tries per stack document survives a blip and ends the storm.
        with _CACHE_LOCK:
            _FAILURES[key] = _FAILURES.get(key, 0) + 1
            attempts = _FAILURES[key]
        if attempts >= _ATTEMPTS_BEFORE_GIVING_UP:
            # Names the endpoint. The old line named the stack, so an
            # unreachable host read as a problem with the document.
            logger.warning(
                "Could not resolve framework instructions after %d attempts at "
                "%s; they will be absent for this stack for the rest of the run.",
                attempts, _where_the_extraction_model_points(),
                exc_info=True,
            )
        else:
            logger.warning(
                "Could not resolve framework instructions for this stack "
                "(attempt %d of %d)", attempts, _ATTEMPTS_BEFORE_GIVING_UP,
                exc_info=True,
            )
        return []

    with _CACHE_LOCK:
        _CACHE[key] = list(keywords)
    # One line per distinct stack document, which is what makes the caching
    # checkable in a deployed run rather than only in a test. If this appears
    # once per stage - or once per model call, as it did before the cache - the
    # extraction is being repeated and each repetition is a model call.
    logger.info(
        "Framework instructions resolved for this stack: %s",
        ", ".join(keywords) or "none",
    )
    return keywords


def build_plugin_instructions_middleware(repo_root: str) -> Any:
    """Append the stack's framework instructions to every call's system prompt."""
    from langchain.agents.middleware import AgentMiddleware

    class PluginInstructionsMiddleware(AgentMiddleware):
        """Append framework-specific plugin instructions to the system prompt."""

        name = "PluginInstructionsMiddleware"

        def wrap_model_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
            keywords = _extract_stack_keywords(repo_root)
            if not keywords:
                return handler(request)

            instructions = get_plugin_instructions(keywords)
            if not instructions:
                return handler(request)

            try:
                request = _with_instructions(request, instructions)
            except Exception:  # noqa: BLE001 - never fail a call over a hint
                logger.debug("Could not append plugin instructions", exc_info=True)
            return handler(request)

    return PluginInstructionsMiddleware()


def _with_instructions(request: Any, instructions: str) -> Any:
    """`request` with `instructions` on the end of its system prompt.

    The system prompt is `request.system_message`, not `request.messages[0]`;
    `messages` is documented as excluding it. Both are handled because
    `system_prompt` is still accepted and still converted, and a request that
    carries neither gets the instructions as a message rather than losing them.
    """
    from langchain_core.messages import SystemMessage

    existing = getattr(request, "system_message", None)
    if existing is not None and isinstance(getattr(existing, "content", None), str):
        return request.override(
            system_message=SystemMessage(content=f"{existing.content}\n\n{instructions}")
        )

    prompt = getattr(request, "system_prompt", None)
    if isinstance(prompt, str) and prompt:
        return request.override(system_message=SystemMessage(content=f"{prompt}\n\n{instructions}"))

    messages = getattr(request, "messages", None)
    if isinstance(messages, list):
        return request.override(messages=[*messages, {"role": "user", "content": instructions}])
    return request


__all__ = ["build_plugin_instructions_middleware"]
