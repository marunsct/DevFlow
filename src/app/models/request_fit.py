"""Every request a model is sent fits the context the server gives it (LF.1500-LF.1502).

Measured on one fast run: a testing stage on a server that gives each request 93,184 tokens grew from 78,848 to
81,370 reported input tokens with no summary, and its next request - 96,754 tokens - was refused six times with
"request (96754 tokens) exceeds the available context size (93184 tokens)" and the run failed. Nothing between the
summariser and the server checked the whole request: the summariser counts the conversation, never the memory and
framing other middleware adds after it, and no client of this harness recognised that refusal as a context overflow,
so it was neither compacted nor retried smaller.

Three guards, all generic to any OpenAI-compatible server:

- `room_tokens`: the slot (the smallest limit the server has refused at, else `server_profile`'s per-request context)
  less the reply's reserve. The summariser compacts at once when the next request would pass it (`compaction`).
- `before_sending` / `after_a_refusal`: at the client, the whole request is estimated - every message, the tools -
  in characters per token calibrated on the server-reported input of the previous reply. Past the room, the results
  the model has already answered are cut to a head and a tail, oldest first, then the largest results, until it
  fits. A refusal for size is learnt from (its limit and its exact token count), cut harder and sent again, and when
  nothing more can be cut it is raised as a `ContextOverflowError`, which the summariser answers by summarising.
- `bounded_result`: a single tool result that by itself would push the stage's next request past the room is cut at
  the tool to a head and a tail with a pointer (`app.agents.tool_result_bound`).
"""

from __future__ import annotations

import json
import logging
import re
import threading
from typing import Any

logger = logging.getLogger(__name__)

#: Characters per token before any reply has been measured: a little under the 3 the context budget counts with,
#: since JSON-escaped command output tokenises denser than prose (measured: 2.87 on the refused request above).
DEFAULT_CHARS_PER_TOKEN = 2.8
#: The share of the room a request is fitted to, for the estimate's own error.
MARGIN = 0.95
#: At most this share of the slot is held back for the reply, so a large reply cap never leaves the request no room.
MOST_RESERVE_SHARE = 1 / 3
#: An earlier result the model has already answered is kept as this much of its start and its end.
SEEN_HEAD = 400
SEEN_TAIL = 800
#: No result is cut below this many characters.
FLOOR_CHARACTERS = 2_000
#: How many times a request refused for its size is sent again, each cut harder by `HARDER`.
MOST_RETRIES = 2
HARDER = 0.75
#: Calibrations outside this band are taken for a misreading and ignored.
_RATIO_BAND = (1.5, 6.0)

#: What the transcript records when a request was fitted.
RECORD_KIND = "request_fitted"

_CUT_NOTE = ("\n\n...[{omitted} characters of this result are left out here so the request fits the model's "
             "context]...\n\n")
_SEEN_NOTE = ("\n\n...[{omitted} characters of this earlier result are left out of this request so it fits the "
              "model's context; read or run it again if you need them]...\n\n")

_LOCK = threading.Lock()
#: Characters per token, by server and by stage, from the last reply each was measured on.
_RATIOS: dict[Any, float] = {}
#: The smallest context each server has refused a request at, in tokens.
_LIMITS: dict[Any, int] = {}
#: Each stage's last server-reported input tokens.
_LAST_INPUT: dict[str, int] = {}
#: The room each stage's last request had, in tokens (the slot less that request's reply reserve).
_LAST_ROOM: dict[str, int] = {}

#: llama.cpp and LM Studio: "request (96754 tokens) exceeds the available context size (93184 tokens)".
_LLAMA = re.compile(r"request \((\d+) tokens?\) exceeds the available context size \((\d+) tokens?\)", re.I)
#: OpenAI and vLLM: "maximum context length is 8192 tokens. However, your messages resulted in 9000 tokens".
_OPENAI = re.compile(r"maximum context length is (\d+) tokens?.*?(?:resulted in|requested) (\d+) tokens?", re.I | re.S)
#: Wordings that name no numbers.
_SAID = ("exceed_context_size_error", "exceeds the available context size", "context size has been exceeded",
         "context_length_exceeded", "maximum context length", "prompt is too long", "input is too long",
         "exceeds the context window", "too many tokens")


def refused_for_size(error: BaseException | str) -> tuple[int | None, int | None] | None:
    """(tokens sent, the server's limit) when `error` is a request refused for its size, either None where the
    server did not say; None when it is any other error."""
    try:
        from langchain_core.exceptions import ContextOverflowError

        typed = isinstance(error, ContextOverflowError)
    except ImportError:  # pragma: no cover - older langchain-core
        typed = False
    text = str(error)
    found = _LLAMA.search(text)
    if found:
        return int(found.group(1)), int(found.group(2))
    found = _OPENAI.search(text)
    if found:
        return int(found.group(2)), int(found.group(1))
    lowered = text.lower()
    if typed or any(said in lowered for said in _SAID):
        from app.models.window_probe import limit_from_error

        return None, limit_from_error(text)
    return None


def as_overflow(error: BaseException) -> BaseException:
    """`error` as a `ContextOverflowError` when it is a refusal for size, so the summariser's overflow fallback and
    the stage's overflow handling recognise it; else `error` itself."""
    try:
        from langchain_core.exceptions import ContextOverflowError
    except ImportError:  # pragma: no cover
        return error
    if isinstance(error, ContextOverflowError) or refused_for_size(error) is None:
        return error
    try:
        import openai
        from langchain_openai.chat_models.base import OpenAIContextOverflowError

        if isinstance(error, openai.BadRequestError):
            return OpenAIContextOverflowError(message=error.message, response=error.response, body=error.body)
    except Exception:  # noqa: BLE001 - the error as it was
        return error
    return error


def _text_of(content: Any) -> int:
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        total = 0
        for block in content:
            if isinstance(block, str):
                total += len(block)
            elif isinstance(block, dict):
                total += len(str(block.get("text") or ""))
        return total
    return len(str(content or ""))


def message_chars(message: Any) -> int:
    """The characters one message puts in a request: its text, its calls' arguments, its carried reasoning."""
    total = _text_of(getattr(message, "content", ""))
    for call in getattr(message, "tool_calls", None) or ():
        try:
            total += len(json.dumps(call.get("args") or {}, default=str)) + len(str(call.get("name") or ""))
        except Exception:  # noqa: BLE001
            total += len(str(call))
    reasoning = (getattr(message, "additional_kwargs", None) or {}).get("reasoning_content")
    if isinstance(reasoning, str):
        total += len(reasoning)
    return total


def tools_chars(tools: Any) -> int:
    """The characters the tools' schemas put in a request."""
    if not tools:
        return 0
    try:
        return len(json.dumps(list(tools), default=str))
    except Exception:  # noqa: BLE001
        return sum(len(str(tool)) for tool in tools)


def request_chars(messages: list[Any], tools: Any = None) -> int:
    """The characters a whole request holds: every message and every tool schema."""
    return sum(message_chars(m) for m in messages) + tools_chars(tools)


def _stage_key() -> str | None:
    try:
        from app.agents.stage_memory import current_stage_key

        return current_stage_key()
    except Exception:  # noqa: BLE001
        return None


def chars_per_token(server: Any = None) -> float:
    """Characters per token as last measured on `server`, else on the running stage, else the default."""
    with _LOCK:
        for key in (server, ("stage", _stage_key())):
            if key is not None and key in _RATIOS:
                return _RATIOS[key]
    return DEFAULT_CHARS_PER_TOKEN


def calibrate(server: Any, chars: int, tokens: int | None) -> None:
    """Keep `chars` / `tokens` as `server`'s and the running stage's characters per token."""
    if not chars or not tokens or tokens <= 0:
        return
    ratio = chars / tokens
    if not _RATIO_BAND[0] <= ratio <= _RATIO_BAND[1]:
        return
    stage = _stage_key()
    with _LOCK:
        if server is not None:
            _RATIOS[server] = ratio
        if stage:
            _RATIOS[("stage", stage)] = ratio
            _LAST_INPUT[stage] = int(tokens)


def learn_limit(server: Any, limit: int | None) -> None:
    """Keep the smallest context `server` has refused a request at."""
    if not limit or limit <= 0:
        return
    with _LOCK:
        key = server if server is not None else "any"
        _LIMITS[key] = min(_LIMITS.get(key, limit), int(limit))


def last_input_tokens() -> int | None:
    """The running stage's last server-reported input tokens, or None."""
    stage = _stage_key()
    with _LOCK:
        return _LAST_INPUT.get(stage) if stage else None


def _address(address: Any) -> str:
    return str(address or "").strip().rstrip("/").lower()


def slot_tokens(server: Any = None) -> int | None:
    """The tokens one request may hold: the smallest a server refused at (this one's, or any when None), and the
    per-request context `server_profile` read; None when neither is known."""
    with _LOCK:
        if server is not None:
            learned = _LIMITS.get(server)
        else:
            learned = min(_LIMITS.values()) if _LIMITS else None
    try:
        from app.models.server_profile import current, read_for

        profiled = getattr(current(), "slot_context", None)
        # Only for the server it was read from: a client of another server (a hosted judgement model) has its own.
        where = read_for()
        if isinstance(server, tuple) and server and where and _address(where[0]) != _address(server[0]):
            profiled = None
    except Exception:  # noqa: BLE001
        profiled = None
    known = [int(v) for v in (learned, profiled) if isinstance(v, int) and v > 0]
    return min(known) if known else None


def room_tokens(reply_tokens: int | None = None, server: Any = None, window: int | None = None) -> int | None:
    """The input tokens a request may hold: the slot (no larger than `window` when given) less the reply's reserve
    (`reply_tokens`, else the context budget's reply ceiling, never more than a third of the slot)."""
    slot = slot_tokens(server)
    if window and window > 0:
        slot = min(slot, int(window)) if slot else int(window)
    if not slot:
        return None
    reserve = reply_tokens if isinstance(reply_tokens, int) and reply_tokens > 0 else None
    if reserve is None:
        try:
            from app.agents.context_budget import ContextBudget

            reserve = ContextBudget.resolve().max_output_tokens or None
        except Exception:  # noqa: BLE001
            reserve = None
    reserve = min(reserve or int(slot * MOST_RESERVE_SHARE), int(slot * MOST_RESERVE_SHARE))
    return slot - reserve


def next_request_tokens(messages: list[Any]) -> int | None:
    """What the next request of this conversation will hold, in tokens: the last reply's server-reported input and
    output, and the messages since it at the calibrated rate; None when no reply reported its usage."""
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if getattr(message, "type", None) != "ai":
            continue
        usage = getattr(message, "usage_metadata", None) or {}
        reported = int(usage.get("input_tokens") or 0)
        if reported <= 0:
            return None
        since = sum(message_chars(m) for m in messages[index + 1:])
        return reported + int(usage.get("output_tokens") or 0) + int(since / chars_per_token())
    return None


def head_and_tail(text: str, most: int, note: str = _CUT_NOTE) -> str:
    """`text` as its start and its end in at most about `most` characters, with how much was left out between."""
    if len(text) <= most:
        return text
    keep = max(0, most - len(note) - 12)
    head = int(keep * 0.4)
    tail = keep - head
    omitted = len(text) - head - tail
    return text[:head] + note.format(omitted=omitted) + (text[-tail:] if tail else "")


def _is_result(message: Any) -> bool:
    return getattr(message, "type", None) == "tool" and isinstance(getattr(message, "content", None), str)


def fitted(messages: list[Any], most_chars: int) -> tuple[list[Any], int]:
    """`messages` cut to at most `most_chars` characters, and how many results were cut.

    First the results the model has already answered, oldest first, to `SEEN_HEAD` + `SEEN_TAIL`; then the largest
    results, each just enough or to `FLOOR_CHARACTERS`. Only tool results are cut: the request, the memory and the
    model's own words are what the stage works from. The list is new; the messages in it are copies where cut.
    """
    sizes = [message_chars(m) for m in messages]
    total = sum(sizes)
    if total <= most_chars:
        return messages, 0
    out = list(messages)
    cut: set[int] = set()
    last_reply = max((i for i, m in enumerate(out) if getattr(m, "type", None) == "ai"), default=-1)
    seen_most = SEEN_HEAD + SEEN_TAIL + len(_SEEN_NOTE) + 20
    for index, message in enumerate(out):
        if total <= most_chars:
            break
        if index < last_reply and _is_result(message) and len(message.content) > seen_most:
            content = message.content
            shorter = content[:SEEN_HEAD] + _SEEN_NOTE.format(omitted=len(content) - SEEN_HEAD - SEEN_TAIL) \
                + content[-SEEN_TAIL:]
            out[index] = message.model_copy(update={"content": shorter})
            new = message_chars(out[index])
            total -= sizes[index] - new
            sizes[index] = new
            cut.add(index)
    while total > most_chars:
        candidates = [i for i, m in enumerate(out) if _is_result(m) and len(m.content) > FLOOR_CHARACTERS + 200]
        if not candidates:
            break
        index = max(candidates, key=lambda i: len(out[i].content))
        content = out[index].content
        target = max(FLOOR_CHARACTERS, len(content) - (total - most_chars))
        out[index] = out[index].model_copy(update={"content": head_and_tail(content, target)})
        new = message_chars(out[index])
        if new >= sizes[index]:
            break
        total -= sizes[index] - new
        sizes[index] = new
        cut.add(index)
    return (out, len(cut)) if cut else (messages, 0)


def _note(estimated: int, room: int, cut: int, refused: bool) -> None:
    """A transcript record of a request fitted to the room. Never raises."""
    try:
        from app.models.model_pin import current_run_id
        from app.observability.transcript import _stage_from_config, record

        record(current_run_id(), _stage_from_config(""), RECORD_KIND, estimated_tokens=estimated, room_tokens=room,
               results_cut=cut, after_a_refusal=refused,
               message=(f"A request of about {estimated:,} tokens was fitted to the {room:,} the model's context "
                        f"leaves it by cutting {cut} tool result(s) to their start and end"))
    except Exception:  # noqa: BLE001
        logger.debug("Could not record a fitted request", exc_info=True)


def before_sending(server: Any, messages: list[Any], tools: Any = None,
                   reply_tokens: int | None = None) -> tuple[list[Any], int]:
    """The request's messages fitted to the room on `server`, and the request's characters as sent."""
    fixed = tools_chars(tools)
    chars = request_chars(messages) + fixed
    room = room_tokens(reply_tokens, server)
    if not room:
        return messages, chars
    stage = _stage_key()
    if stage:
        with _LOCK:
            _LAST_ROOM[stage] = room
    ratio = chars_per_token(server)
    if chars <= room * ratio * MARGIN:
        return messages, chars
    out, cut = fitted(messages, int(room * ratio * MARGIN) - fixed)
    if not cut:
        return messages, chars
    _note(int(chars / ratio), room, cut, refused=False)
    return out, request_chars(out) + fixed


def after_reply(server: Any, chars: int, result: Any) -> None:
    """Calibrate on the server-reported input tokens of `result`. Never raises."""
    try:
        message = result.generations[0].message
        usage = getattr(message, "usage_metadata", None) or {}
        tokens = usage.get("input_tokens")
        if not tokens:
            token_usage = (getattr(result, "llm_output", None) or {}).get("token_usage") or {}
            tokens = token_usage.get("prompt_tokens")
        calibrate(server, chars, int(tokens) if tokens else None)
    except Exception:  # noqa: BLE001
        pass


def after_a_refusal(server: Any, error: BaseException, messages: list[Any], tools: Any = None,
                    reply_tokens: int | None = None, attempt: int = 0) -> tuple[list[Any], int] | None:
    """The request cut harder after the server refused it for its size, and its characters; None when `error` is not
    that refusal, the retries are spent, or nothing is left to cut."""
    said = refused_for_size(error)
    if said is None or attempt >= MOST_RETRIES:
        return None
    sent, limit = said
    fixed = tools_chars(tools)
    chars = request_chars(messages) + fixed
    learn_limit(server, limit)
    if sent:
        # The server counted this very request: the exact rate, whatever the last reply said.
        ratio = chars / sent
        if _RATIO_BAND[0] <= ratio <= _RATIO_BAND[1]:
            with _LOCK:
                if server is not None:
                    _RATIOS[server] = ratio
    room = room_tokens(reply_tokens, server)
    if not room:
        room = int(sent * 0.8) if sent else None
    if not room:
        return None
    ratio = chars_per_token(server)
    most = int(room * ratio * MARGIN * HARDER ** attempt) - fixed
    out, cut = fitted(messages, max(0, most))
    if not cut:
        return None
    _note(sent or int(chars / ratio), room, cut, refused=True)
    return out, request_chars(out) + fixed


def bounded_result(text: str, pointer: str) -> str:
    """`text` cut to a head and a tail with `pointer` when, by itself, it would push the running stage's next request
    past the room; `text` itself otherwise.

    The stage's next request holds its last request and this result: past the room, the result keeps what is left of
    the room, and never less than a quarter of it - the summariser makes room for the rest.
    """
    if not isinstance(text, str) or len(text) <= FLOOR_CHARACTERS:
        return text
    stage = _stage_key()
    with _LOCK:
        room = _LAST_ROOM.get(stage) if stage else None
    room = room or room_tokens()
    if not room:
        return text
    ratio = chars_per_token()
    before = last_input_tokens() or 0
    tokens = len(text) / ratio
    if before + tokens <= room:
        return text
    most_tokens = max(room - before, room // 4)
    if tokens <= most_tokens:
        return text
    note = ("\n\n...[{omitted} characters of this result are left out here, since whole it would not fit the "
            "model's context; " + pointer.replace("{", "{{").replace("}", "}}") + "]...\n\n")
    return head_and_tail(text, int(most_tokens * ratio), note)


def forget() -> None:
    """Drop every calibration and learnt limit (a new process, or a test)."""
    with _LOCK:
        _RATIOS.clear()
        _LIMITS.clear()
        _LAST_INPUT.clear()
        _LAST_ROOM.clear()


__all__ = ["DEFAULT_CHARS_PER_TOKEN", "MOST_RETRIES", "RECORD_KIND", "after_a_refusal", "after_reply", "as_overflow",
           "before_sending", "bounded_result", "calibrate", "chars_per_token", "fitted", "forget", "head_and_tail",
           "last_input_tokens", "learn_limit", "message_chars", "next_request_tokens", "refused_for_size",
           "request_chars", "room_tokens", "slot_tokens", "tools_chars"]
