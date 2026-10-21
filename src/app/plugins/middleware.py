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
from app.plugins.seed import SETUP

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

    Bounded, because both calls are small and neither is the stage's work. The
    client used to carry no reply ceiling, no timeout and whatever reasoning the
    server defaults to. On one run a reasoning model given the stack document
    reasoned for over 60,000 tokens and was still going 20 minutes later -
    and since this runs in the middleware in front of an agent's model call,
    the specification stage sat behind it the whole time. So the reply is
    capped, the call times out, and reasoning is switched off the same way the
    one-call answer after a spiral switches it off
    (`app.agents.thinking.answering_without_reasoning`); `_ask` retries without
    the effort field for a server that refuses it. A reply cut off anyway comes
    back empty, which reads as "no frameworks named" - the names found in the
    document itself (`_named_in_the_selected_stack`) still apply.
    """
    from langchain_openai import ChatOpenAI

    from app.agents.thinking import answering_without_reasoning
    from app.models import _runtime_settings

    from app.models.endpoints import reached_from_here

    settings = _runtime_settings()
    # Reached as every stage's client reaches it: from a container, a server
    # on the owner's machine is `host.docker.internal`, sent the Host header
    # its owner names it by. Built from the setting as written, one run's
    # `http://localhost:9090/v1` reached the container itself and the stack's
    # instructions were absent for the whole run.
    reached, naming = reached_from_here(settings.openai_base_url)
    model = ChatOpenAI(
        model=settings.model_name,
        api_key=settings.openai_api_key,
        base_url=reached if settings.openai_base_url else settings.openai_base_url,
        default_headers=naming or None,
        temperature=0,
        max_tokens=_AUXILIARY_REPLY_TOKENS,
        timeout=_AUXILIARY_TIMEOUT_SECONDS,
        max_retries=1,
    )
    quiet = answering_without_reasoning(model)
    return model.model_copy(update=quiet) if quiet else model


#: The most either auxiliary reply may be: a comma-separated list, or four
#: bullet points. Far below any stage's own ceiling.
_AUXILIARY_REPLY_TOKENS = 2_048

#: How long either auxiliary call may take before it counts as a failure.
_AUXILIARY_TIMEOUT_SECONDS = 180


#: The cap of the one second asking, when the first reply was all reasoning.
_AUXILIARY_REPLY_TOKENS_WITH_REASONING = 4 * _AUXILIARY_REPLY_TOKENS


def _all_reasoning(reply: Any) -> bool:
    """Whether the reply hit its cap with nothing written: the model reasoned through all of it."""
    metadata = getattr(reply, "response_metadata", None) or {}
    return str(metadata.get("finish_reason") or "") == "length" and not _text_of(reply).strip()


def _ask(model: Any, messages: list[Any]) -> Any:
    """`model.invoke(messages)`, asked again without `reasoning_effort` if the
    server refused the request because of it, and once more with room to reason
    if the reply was all reasoning.

    The reply is capped small and asked for without reasoning, and a model that
    reasons on every reply whatever it is asked spent the whole cap thinking and
    wrote nothing: measured on the first runs of one such model, the list of
    frameworks came back empty, and the notes for a framework the store does not
    know would have too.
    """
    from app.agents.thinking import the_server_refused_the_request, without_the_effort_field
    from app.observability.direct_calls import config_for_this_run

    recorded = config_for_this_run("plugin_instructions")
    try:
        reply = model.invoke(messages, **recorded)
    except Exception as error:
        extra = getattr(model, "extra_body", None)
        plainer = without_the_effort_field({"extra_body": extra}) if extra else None
        if plainer is None or not the_server_refused_the_request(error):
            raise
        model = model.model_copy(update=plainer)
        reply = model.invoke(messages, **recorded)
    if _all_reasoning(reply) and int(getattr(model, "max_tokens", 0) or 0) < _AUXILIARY_REPLY_TOKENS_WITH_REASONING:
        logger.info("The auxiliary reply was all reasoning at its cap; asking once more with room to reason")
        reply = model.model_copy(update={"max_tokens": _AUXILIARY_REPLY_TOKENS_WITH_REASONING}).invoke(messages, **recorded)
    return reply


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


#: The heading `artifact_document` gives the chosen stack. The section under it
#: is what was selected; the rationale after it also names what was rejected.
_SELECTED_SECTION = re.compile(
    r"^##\s+Selected Technology Stack\s*$(?P<body>.*?)(?=^##\s|\Z)", re.M | re.S
)


def _named_in_the_selected_stack(content: str, known: set[str]) -> List[str]:
    """Every framework with stored instructions that the selected stack names.

    The model's extraction is told to leave out "tools or generic terms", and
    for one run's stack - "None (Vanilla HTML/CSS/JS)", "Playwright for page" -
    it returned `javascript` alone. The instructions for testing a page in a
    browser are stored under `html`, so the stage that wrote the Playwright
    suite never received them, including the two traps it then fell into.

    A stored name that the selected section spells out is not a judgement call,
    so it is matched here rather than left to the model: whole words, case
    folded, with dots dropped so "Next.js" reads as `nextjs`. Only that section
    is read, because the rationale also names the options it turned down.
    """
    chosen, _ = _what_the_selected_stack_says(content)
    if chosen is None:
        return []
    named = [name for name in sorted(known) if name and _names(chosen, name)]
    return sorted(dict.fromkeys(_the_known_name_for(name, known) for name in named))


#: A clause boundary inside the selected section. "instead of" and "rather than"
#: open a clause of their own, so "Vue instead of React" keeps Vue.
_A_CLAUSE_BREAK = re.compile(
    r"[\n;()\[\],]|\.\s|:\s|\s[-–—]\s|\bbut\b|(?=\binstead of\b|\brather than\b)",
    re.I,
)

#: Words that turn a clause into a rejection: "no TypeScript", "rules out
#: Vue/React", "React is not used", "instead of Angular".
_REJECTS = re.compile(
    r"\b(?:no|not|none|without|never|neither|nor|avoid\w*|exclud\w*|reject\w*"
    r"|rules? out|ruled out|instead of|rather than|passed over|unlike)\b",
    re.I,
)

#: A field label as `artifact_document` writes it: `**Additional tools:**`.
_A_FIELD_LABEL = re.compile(r"\*\*\s*([^*:]+?)\s*:\s*\*\*")


def _what_the_selected_stack_says(content: str) -> tuple[str | None, str]:
    """The selected section's text split into (chosen, set aside), lowercased.

    Set aside is every clause that rejects what it names, and the tools field.

    `chosen` is None when the document has no selected section.

    The section was read whole, and it says what it turns down as well as what
    it takes. One run's selected stack read "vanilla JavaScript (ES2020 ...; no
    TypeScript ...)" and "The brief's 'no external dependencies ...' rules out
    Vue/Svelte/React/Alpine outright", and its agents were given the React,
    Vue and TypeScript instructions. The same run's "Additional tools" listed
    `python3 -m http.server`, which brought the Python instructions - "You are
    working in a Python environment" - into a JavaScript project. A command a
    stack uses is a tool, and the extraction model is already told to leave
    tools out; so is this.
    """
    match = _SELECTED_SECTION.search(content)
    if not match:
        return None, ""
    chosen: list[str] = []
    set_aside: list[str] = []
    label = ""
    for line in match.group("body").splitlines():
        labelled = _A_FIELD_LABEL.search(line)
        if labelled:
            label = labelled.group(1).lower()
            line = line[labelled.end():]
        if "tool" in label:
            set_aside.append(line.lower())
            continue
        for clause in _A_CLAUSE_BREAK.split(line):
            (set_aside if _REJECTS.search(clause) else chosen).append(clause.lower())
    return "\n".join(chosen), "\n".join(set_aside)


def _names(text: str, name: str) -> bool:
    """Whether `text` names `name` as a whole word, dots dropped, version allowed."""
    spaced = f"{text}\n{text.replace('.', '')}"
    # A version number may follow: "HTML5/CSS3/JS" selected `html` and `css` on
    # one run and matched neither while the boundary was a bare word boundary,
    # because a digit is a word character.
    return re.search(rf"(?<![\w-]){re.escape(name)}(?:\d[\d.]*)?(?![\w-])", spaced) is not None


#: A version written onto a name: `html5`, `css3`, `python3`, `es2020`.
_A_VERSION_SUFFIX = re.compile(r"[\s-]*v?\d[\d.]*$")


def _the_known_name_for(name: str, known: set[str]) -> str:
    """`name` without a version written onto it, when that is a known framework.

    One run's extraction returned `html5` and `css3`. Neither was stored, so
    notes were generated for both - spec trivia about `<canvas>`, `<video>`,
    animations and Flexbox - and appended to every prompt beside the seeded
    `html` and `css` instructions, which are the ones the harness maintains.
    The word match already reads `HTML5` as `html`; this reads the model's
    answer the same way. Preferred even when the versioned name is stored too,
    so a note generated before this existed is not used again.
    """
    bare = _A_VERSION_SUFFIX.sub("", name).strip()
    if bare and bare != name and bare in known:
        return bare
    return name


def _turned_down_by_the_selected_stack(content: str, name: str) -> bool:
    """Whether the selected section names `name` only to reject it or as a tool.

    A name it never mentions is not turned down: the model may infer
    `javascript` from "Vanilla JS", which is what it is asked to do.
    """
    chosen, set_aside = _what_the_selected_stack_says(content)
    if chosen is None:
        return False
    lowered = name.lower()
    return _names(set_aside, lowered) and not _names(chosen, lowered)


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
        reply = _ask(model, [
            SystemMessage(content=(
                "You are a tech stack analyzer. Read the provided technology stack "
                "document and return ONLY a comma-separated list of the core "
                "programming languages and frameworks it mandates (for example: "
                "react, typescript, python, postgres). Do not include tools or "
                "generic terms. Output exactly the comma-separated list."
            )),
            HumanMessage(content=content),
        ])
        # The model reads the whole document, rationale included, and the
        # rationale names what was turned down. A name the selected stack itself
        # rejects is not one it mandates, whoever read it out.
        detected = [
            name
            for name in _framework_names(_text_of(reply))
            if not _turned_down_by_the_selected_stack(content, name)
        ]
        if not detected:
            logger.info("No frameworks could be read from the stack document")

        store = PluginStore.shared()
        # A setup row is the second half of another name's notes, never a
        # framework of its own.
        known = {name for name in store.get_all_framework_names() if not name.endswith(SETUP)}
        detected = list(dict.fromkeys(_the_known_name_for(name, known) for name in detected))
        detected += [
            name for name in _named_in_the_selected_stack(content, known) if name not in detected
        ]
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
                    # Facts about the tool, never advice about the product. The
                    # previous request asked for "best practices ... concurrency,
                    # security and architecture" and a to-do list's specialists
                    # were told to use Web Workers and CSP headers - scope the
                    # brief never asked for, stated as a rule of the stack.
                    generated = _text_of(_ask(model, [
                        SystemMessage(content=(
                            "You write short, factual working notes for a coding agent "
                            "that has to build and test a project with a given framework "
                            "or language. Output only the notes."
                        )),
                        # Testing mechanics only. Asked also for "how a project is
                        # laid out, how it is run", the notes described a typical
                        # project - `src/`, `dist/`, a bundler, Jest with jsdom and
                        # a storage polyfill package - against the harness's own
                        # "Keep it FLAT" layout and the seeded "`node --test`
                        # ships with Node: nothing to install". Layout and build
                        # belong to the harness and the brief.
                        HumanMessage(content=(
                            f"Write at most 4 bullet points of facts about '{framework}' "
                            f"that a coding agent needs in order to run its tests without "
                            f"a person watching and to declare test-only dependencies. "
                            f"Do not describe project layout, build or bundling steps, or "
                            f"which libraries to add, and do not recommend features, "
                            f"patterns, security measures or architecture - the product's "
                            f"brief and the harness decide those. If '{framework}' is not "
                            f"a framework, language or runtime, reply with nothing at all."
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


def _with_the_setup_notes(keywords: List[str], repo_root: str) -> List[str]:
    """`keywords`, each followed by its notes on setting test runners up -
    unless a stack pack scaffolded the project, which set them up and keeps
    them. See `app.plugins.seed.SETUP`."""
    try:
        from app.stacks.contract import read as the_contract

        if the_contract(repo_root) is not None:
            return list(keywords)
    except Exception:  # noqa: BLE001 - without a contract the notes are the help there is
        logger.debug("Could not read the stack contract", exc_info=True)
    return [name for keyword in keywords for name in (keyword, keyword + SETUP)]


def build_plugin_instructions_middleware(repo_root: str, role: str = "") -> Any:
    """Append the stack's framework instructions to every call's system prompt."""
    from langchain.agents.middleware import AgentMiddleware

    class PluginInstructionsMiddleware(AgentMiddleware):
        """Append framework-specific plugin instructions to the system prompt."""

        name = "PluginInstructionsMiddleware"

        def wrap_model_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
            keywords = _extract_stack_keywords(repo_root)
            instructions = get_plugin_instructions(_with_the_setup_notes(keywords, repo_root), role) if keywords else ""
            # The owner's direction for this run, sent while it runs, after
            # the stack's instructions (`app.server.steering`).
            try:
                from app.observability.transcript import _stage_from_config
                from app.server.steering import as_instructions as the_owner_s_direction
                from app.tracing import APP_RUN_ID_KEY

                try:
                    from langgraph.config import get_config

                    run_id = ((get_config() or {}).get("configurable") or {}).get(APP_RUN_ID_KEY)
                except Exception:  # noqa: BLE001 - outside a run there is no config; the note still applies
                    run_id = None
                instructions += the_owner_s_direction(repo_root, _stage_from_config(""), run_id)
            except Exception:  # noqa: BLE001 - a note that cannot be read adds nothing
                logger.debug("Could not read the run's steering notes", exc_info=True)
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
