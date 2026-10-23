"""A reply cut off by the reply cap is salvaged from its own reasoning, where the model's server allows it (behind `REPLY_SALVAGE`).

A reasoning model that reaches the cap while still thinking writes nothing:
measured over nine runs, 19 of 1,927 replies, 15 of them in fix stages, and
10% of every output token the runs spent. The recovery so far was the next call
with the tools withheld, then thinking switched off for the rest of the stage -
the reasoning thrown away, and the stage's later calls reasoning less. A cap on
reasoning would have cost more: 74 replies of the same runs finished between
16,000 and 32,768 tokens, 21 of them past 24,000.

So the reasoning is kept and finished instead, as a reasoning budget ends
thinking rather than discarding it (vLLM's reasoning budget; the Qwen3 report's
thinking budget): the request is sent again with the model's reply begun - its
own reasoning, closed, and a sentence saying it answers now - and the model
writes the answer that reasoning was for. A reply cut off part way through its
text is continued the same way, from where it stopped (Aider's "infinite
output"). No reply that finishes under the cap is touched.

Whether a server continues a begun reply, and how a reasoning model's begun
reply must be shaped for its template, is the model's and the server's, not
the harness's. So it is measured, not assumed: `measure` asks a few small
questions with a begun reply in each shape, and keeps what worked beside the
model's other measurements (`registry.fitness_dir`), under its served name.
It runs the first time a model is seen - at a run segment's start, or at the
first reply that needs it - and never again for that model unless asked
(`loop.sh salvage-probe`). Salvage is used only where it was measured to work.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from app.switches import is_on

logger = logging.getLogger(__name__)

#: `REPLY_SALVAGE` set to on or off overrides this.
ON_BY_DEFAULT = False

#: The ways a begun reply is sent, tried in this order. `reasoning_field` puts
#: the reasoning where the server's own template renders it (llama.cpp reads an
#: assistant message's `reasoning_content`); `think_tags` writes the template's
#: markup into the content.
SHAPES = ("reasoning_field", "think_tags")
#: Said at the end of the kept reasoning, so the model answers rather than
#: reasoning again.
ENOUGH = "I have reasoned enough about this. I will give my answer now, from what I have worked out above."
#: The most of a cut-off reply's reasoning sent back, from its end, where the
#: model has said what it concluded; the request must still fit its window.
MOST_REASONING_CHARACTERS = 48_000
#: Continuations of one reply cut off part way through its text, at most.
MOST_CONTINUATIONS = 2
#: The probe's reply ceiling: an answer to its questions is a few tokens.
PROBE_REPLY_TOKENS = 256
#: A probe reply that reasoned more than this ignored the begun reply and thought again.
PROBE_MOST_REASONING_CHARACTERS = 400
#: Where a reply salvaged says so, on its response metadata and in the transcript.
SALVAGED = "harness_salvaged"
#: The key a model's measurement is kept under in its fitness file.
RECORD_KEY = "reply_salvage"


def enabled() -> bool:
    return is_on("REPLY_SALVAGE", ON_BY_DEFAULT)


@dataclass(frozen=True)
class Support:
    """What one model's server was measured to do with a begun reply."""

    #: The shape that worked, or "" when none did.
    shape: str = ""
    #: Whether an answer after kept reasoning can be a tool call.
    tools: bool = False
    #: Whether a reply begun with its own text is continued.
    continuation: bool = False
    #: Whether the server's reply repeats the begun text before continuing it.
    echoes: bool = False
    model: str = ""
    measured_at: str = ""

    @property
    def salvages(self) -> bool:
        return bool(self.shape)


_SUPPORT: dict[str, Support] = {}
_LOCK = threading.Lock()
#: The whole reasoning of the last reply parsed on this thread (`CompatibleChatOpenAI._create_chat_result`).
_LAST = threading.local()


def remember_reasoning(text: str) -> None:
    _LAST.reasoning = text


def _the_last_reasoning() -> str:
    text = getattr(_LAST, "reasoning", "") or ""
    _LAST.reasoning = ""
    return text


def served_name(model: Any) -> str:
    """The name a model's measurement is kept under: the file the server holds, else the configured name."""
    try:
        from app.models.server_profile import current

        profile = current()
        if profile is not None and profile.model:
            return profile.model
    except Exception:  # noqa: BLE001
        pass
    return str(getattr(model, "model_name", "") or "unknown")


def _path(name: str):
    from app.models.registry import _slug, fitness_dir

    return fitness_dir() / f"{_slug(name)}.json"


def recorded(name: str) -> Support | None:
    """The kept measurement for `name`, or None when it was never measured."""
    with _LOCK:
        if name in _SUPPORT:
            return _SUPPORT[name]
    try:
        found = json.loads(_path(name).read_text(encoding="utf-8")).get(RECORD_KEY)
    except (OSError, ValueError, AttributeError):
        return None
    if not isinstance(found, dict):
        return None
    support = Support(**{k: v for k, v in found.items() if k in Support.__dataclass_fields__})
    with _LOCK:
        _SUPPORT[name] = support
    return support


def keep(name: str, support: Support) -> None:
    """Keep `support` in `name`'s fitness file beside what else was measured of it."""
    from app.models.registry import merge_into_fitness

    merge_into_fitness(name, {RECORD_KEY: asdict(support)})
    with _LOCK:
        _SUPPORT[name] = support


def forget() -> None:
    """Drop what this process has read. For tests."""
    with _LOCK:
        _SUPPORT.clear()


# --- the probe -----------------------------------------------------------------

_QUESTION = "What is 17 multiplied by 23? Reply with the number only."
_REASONING = "The user wants 17 * 23. 17 * 20 = 340 and 17 * 3 = 51, so 17 * 23 = 391."
_ANSWER_TOOL = {"type": "function", "function": {
    "name": "give_answer", "description": "Give the answer.",
    "parameters": {"type": "object", "properties": {"value": {"type": "integer"}}, "required": ["value"]}}}
_COUNT = "Count from one to six in words, separated by commas, nothing else."
_COUNT_BEGUN = "one, two, three,"


def begun_reply(shape: str, reasoning: str, text: str = "") -> dict[str, Any]:
    """The assistant message a request ends with, so the server continues it: `reasoning` closed, then `text`."""
    closed = f"{reasoning.rstrip()}\n\n{ENOUGH}" if reasoning.strip() else ""
    if shape == "reasoning_field":
        message: dict[str, Any] = {"role": "assistant", "content": text}
        if closed:
            message["reasoning_content"] = closed
        return message
    return {"role": "assistant", "content": (f"<think>\n{closed}\n</think>\n\n" if closed else "") + text}


def _reply(response: Any) -> tuple[str, str, list[dict], str]:
    """(content, reasoning, tool calls, finish reason) of a raw chat completion."""
    data = response if isinstance(response, dict) else response.model_dump(warnings=False)
    choice = (data.get("choices") or [{}])[0] or {}
    message = choice.get("message") or {}
    return (str(message.get("content") or ""), str(message.get("reasoning_content") or message.get("reasoning") or ""),
            list(message.get("tool_calls") or []), str(choice.get("finish_reason") or ""))


def _without_the_echo(text: str, begun: str) -> tuple[str, bool]:
    stripped = text.lstrip()
    if begun and stripped.startswith(begun.strip()):
        return stripped[len(begun.strip()):], True
    return text, False


def measure(model: Any, name: str = "") -> Support:
    """Ask the model's server a few small questions with a begun reply in each shape; keep and return what worked.

    Uses the model: run where no stage waits for the server (a segment's start,
    or the one reply that needs it). Never raises; a server that answers none of
    it is kept as supporting nothing, so it is not asked again.
    """
    name = name or served_name(model)
    shape, tools, continuation, echoes = "", False, False, False
    create = model.root_client.chat.completions.create
    base = {"model": model.model_name, "max_tokens": PROBE_REPLY_TOKENS, "stream": False}
    for candidate in SHAPES:
        try:
            content, reasoning, _calls, _finish = _reply(create(**base, messages=[
                {"role": "user", "content": _QUESTION}, begun_reply(candidate, _REASONING)]))
        except Exception:  # noqa: BLE001 - a shape the server refuses is not this one
            continue
        if "391" in content and len(reasoning) <= PROBE_MOST_REASONING_CHARACTERS:
            shape = candidate
            break
    if shape:
        try:
            _content, _reasoning, calls, _finish = _reply(create(**base, tools=[_ANSWER_TOOL], messages=[
                {"role": "user", "content": _QUESTION.replace("Reply with the number only.", "Answer with give_answer.")},
                begun_reply(shape, _REASONING)]))
            arguments = json.loads(((calls or [{}])[0].get("function") or {}).get("arguments") or "{}")
            tools = str(arguments.get("value")) == "391"
        except Exception:  # noqa: BLE001
            tools = False
        try:
            content, _reasoning, _calls, _finish = _reply(create(**base, messages=[
                {"role": "user", "content": _COUNT}, begun_reply(shape, "The user wants one to six in words.", _COUNT_BEGUN)]))
            rest, echoes = _without_the_echo(content, _COUNT_BEGUN)
            continuation = "four" in rest.lower() and "one" not in rest.lower().split("four")[0]
        except Exception:  # noqa: BLE001
            continuation = False
    support = Support(shape=shape, tools=tools, continuation=continuation, echoes=echoes, model=name,
                      measured_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    try:
        keep(name, support)
    except Exception:  # noqa: BLE001 - measured for this process at least
        with _LOCK:
            _SUPPORT[name] = support
    logger.info("Reply salvage for %s: %s", name, describe(support))
    return support


def measure_if_new(model: Any) -> Support | None:
    """`name`'s kept measurement, measured now when there is none. Never raises; None when off or unmeasurable."""
    if not enabled():
        return None
    try:
        name = served_name(model)
        return recorded(name) or measure(model, name)
    except Exception:  # noqa: BLE001
        logger.debug("Could not measure reply salvage", exc_info=True)
        return None


def describe(support: Support | None) -> str:
    if support is None:
        return "unmeasured"
    if not support.salvages:
        return "not supported by this server (measured)"
    return (f"supported ({support.shape}); answers after kept reasoning {'may' if support.tools else 'may not'} "
            f"be tool calls; cut-off text {'is' if support.continuation else 'is not'} continued")


# --- the salvage ------------------------------------------------------------

def _lost(message: Any) -> bool:
    return not str(getattr(message, "content", "") or "").strip() and not (getattr(message, "tool_calls", None) or ()) \
        and not (getattr(message, "invalid_tool_calls", None) or ())


def _cut_text(message: Any) -> bool:
    return bool(str(getattr(message, "content", "") or "").strip()) and not (getattr(message, "tool_calls", None) or ()) \
        and not (getattr(message, "invalid_tool_calls", None) or ())


def salvaged(model: Any, messages: list[Any], result: Any, stop: Any = None, **kwargs: Any) -> Any:
    """`result`, or - when its reply hit the cap - the reply its own reasoning answers, or its text continued. Never raises."""
    reasoning = _the_last_reasoning()
    try:
        generation = result.generations[0]
        message = generation.message
        if (getattr(generation, "generation_info", None) or {}).get("finish_reason") != "length" or not enabled():
            return result
        lost, cut = _lost(message), _cut_text(message)
        if not (lost or cut):
            return result
        support = measure_if_new(model)
        if support is None or not support.salvages or (cut and not support.continuation):
            return result
        if lost and (not reasoning.strip() or (kwargs.get("tools") and not support.tools)):
            return result
        kept = reasoning[-MOST_REASONING_CHARACTERS:]
        text = str(message.content or "") if cut else ""
        finish = "length"
        for _ in range(MOST_CONTINUATIONS if cut else 1):
            payload = model._get_request_payload(messages, stop=stop, **kwargs)
            payload["stream"] = False
            payload["messages"].append(begun_reply(support.shape, kept, text))
            response = model.client.create(**payload)
            content, more_reasoning, calls, finish = _reply(response)
            if lost and not content.strip() and not calls:
                return result  # it reasoned again and answered nothing: the usual recovery takes it
            fresh = model._create_chat_result(response)
            if lost:
                return _with_the_salvage(result, fresh, "reasoning")
            rest, _echoed = _without_the_echo(content, text) if support.echoes else (content, False)
            text += rest
            if finish != "length":
                break
        return _with_the_text(result, text, "continuation", finish)
    except Exception:  # noqa: BLE001 - the reply as it was
        logger.debug("Could not salvage a cut-off reply", exc_info=True)
        return result


def _with_the_salvage(original: Any, fresh: Any, kind: str) -> Any:
    old, new = original.generations[0].message, fresh.generations[0].message
    new.additional_kwargs = {**(old.additional_kwargs or {}), **(new.additional_kwargs or {})}
    new.response_metadata = {**(new.response_metadata or {}), SALVAGED: kind,
                             "reasoning_chars": (old.response_metadata or {}).get("reasoning_chars", 0)}
    new.usage_metadata = _summed(old.usage_metadata, new.usage_metadata)
    fresh.generations[0].generation_info = {**(fresh.generations[0].generation_info or {}), SALVAGED: kind}
    logger.info("A reply cut off while reasoning was salvaged from its own reasoning")
    return fresh


def _with_the_text(original: Any, text: str, kind: str, finish: str) -> Any:
    message = original.generations[0].message
    message.content = text
    message.response_metadata = {**(message.response_metadata or {}), SALVAGED: kind, "finish_reason": finish}
    original.generations[0].generation_info = {**(original.generations[0].generation_info or {}),
                                               "finish_reason": finish, SALVAGED: kind}
    logger.info("A reply cut off part way through its text was continued")
    return original


def _summed(one: Any, two: Any) -> Any:
    if not one or not two:
        return two or one
    try:
        return {**two, **{k: int(one.get(k) or 0) + int(two.get(k) or 0)
                          for k in ("input_tokens", "output_tokens", "total_tokens")}}
    except Exception:  # noqa: BLE001
        return two


__all__ = ["ENOUGH", "MOST_CONTINUATIONS", "MOST_REASONING_CHARACTERS", "ON_BY_DEFAULT", "RECORD_KEY", "SALVAGED",
           "SHAPES", "Support", "begun_reply", "describe", "enabled", "forget", "keep", "measure", "measure_if_new",
           "recorded", "remember_reasoning", "salvaged", "served_name"]
