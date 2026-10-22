"""Several `replace_lines` calls to one file, sent in one reply.

A model that has just read a file and wants to change it in several places
sends every edit at once, each numbered against the read. The tool node runs
them one after another, in whatever order the threads take the mutation lock,
and every edit after the first is applied to a file the earlier ones have
already lengthened or shortened. Nothing refuses it: the guard that catches
drifted numbering compares the line with `expect_start`, which is optional and
was not sent.

Measured on one run. `specialist_ui_ux_1` sent seven single-line edits to
`style.css` in one reply - lines 190, 127, 82, 105, 93, 57 and 41, the first of
them adding a whole section. All seven reported "edited". The file then had a
`contain: layout style paint;` on a `[hidden]` rule and a stray `}`, and the
stage spent six more calls, two of them refused, putting it right.

The numbers are not wrong; they are all relative to the same read. So they
are translated: each edit applied from a reply is remembered in the numbering
the model used, and a later edit from the same reply is moved by what the
earlier ones added or removed above it. Two edits whose ranges overlap cannot
both be meant against that one read, and the second is refused.
"""

from __future__ import annotations

import json
import logging
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

_TOOL = "replace_lines"

#: Replies remembered at once. A reply's edits all run within one tool step,
#: so only the latest few can still be in flight; this is a bound, not a cache.
_REMEMBERED = 64


class _Batch:
    """The edits already applied from one reply to one file."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        # (first, last, lines added) in the numbering of the model's read.
        self.applied: list[tuple[int, int, int]] = []


_BATCHES: OrderedDict[tuple[str, str], _Batch] = OrderedDict()
_BATCHES_LOCK = threading.Lock()


def _batch_for(key: tuple[str, str]) -> _Batch:
    with _BATCHES_LOCK:
        batch = _BATCHES.get(key)
        if batch is None:
            batch = _BATCHES[key] = _Batch()
            while len(_BATCHES) > _REMEMBERED:
                _BATCHES.popitem(last=False)
        return batch


def _messages(state: Any) -> list[Any]:
    if isinstance(state, dict):
        return list(state.get("messages") or [])
    return list(getattr(state, "messages", None) or [])


def _calls_of(message: Any) -> list[dict]:
    calls = getattr(message, "tool_calls", None)
    if calls is None and isinstance(message, dict):
        calls = message.get("tool_calls")
    return [c for c in (calls or []) if isinstance(c, dict)]


def _same_file(path: Any) -> str:
    from app.agents.workspace_paths import the_same_place

    return the_same_place(str(path or "").strip())


def _the_reply_holding(state: Any, call_id: str) -> list[dict]:
    """The `replace_lines` calls of the reply that made this call."""
    for message in reversed(_messages(state)):
        calls = _calls_of(message)
        if any(c.get("id") == call_id for c in calls):
            return [c for c in calls if c.get("name") == _TOOL]
    return []


def _line_count(path: Path) -> int | None:
    try:
        return len(path.read_text(encoding="utf-8").splitlines(keepends=True))
    except (OSError, UnicodeDecodeError):
        return None


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _refused(call: dict, text: str) -> Any:
    from langchain_core.messages import ToolMessage

    return ToolMessage(
        content=json.dumps({"error": text}), tool_call_id=call.get("id", ""), name=_TOOL, status="error"
    )


def _is_error(result: Any) -> bool:
    content = getattr(result, "content", result)
    if getattr(result, "status", None) == "error":
        return True
    try:
        return "error" in json.loads(content)
    except (TypeError, ValueError):
        return str(content).lstrip().startswith('{"error"')


def build_line_batch_middleware(repo_root: str) -> Any:
    """Middleware that numbers a reply's line edits against the read they came from."""
    from langchain.agents.middleware import AgentMiddleware

    root = Path(repo_root)

    class LineBatchMiddleware(AgentMiddleware):
        """Translate each `replace_lines` from a batch through the ones before it."""

        name = "LineBatchMiddleware"

        def wrap_tool_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
            call = getattr(request, "tool_call", None)
            if not isinstance(call, dict) or call.get("name") != _TOOL:
                return handler(request)
            arguments = call.get("args") if isinstance(call.get("args"), dict) else {}
            where = _same_file(arguments.get("relative_path"))
            first, last = _as_int(arguments.get("start_line")), _as_int(arguments.get("end_line"))
            if not where or first is None or last is None:
                return handler(request)

            edits = _the_reply_holding(getattr(request, "state", None), call.get("id", ""))
            siblings = [e for e in edits if _same_file((e.get("args") or {}).get("relative_path")) == where]
            if len(siblings) < 2:
                return handler(request)
            # Keyed by the calls themselves, which are unique, rather than by
            # the reply's message id, which a checkpoint or a model server may
            # leave empty.
            reply = ",".join(sorted(str(e.get("id", "")) for e in siblings))

            try:
                from app.tools.repository import _repo_relative_path

                target = root / _repo_relative_path(root, str(arguments.get("relative_path")))
            except Exception:  # noqa: BLE001 - unresolvable: let the tool say so
                return handler(request)

            batch = _batch_for((reply, where))
            with batch.lock:
                for done_first, done_last, _ in batch.applied:
                    if not (last < done_first or first > done_last):
                        return _refused(
                            call,
                            f"Lines {first}-{last} of '{where}' overlap lines "
                            f"{done_first}-{done_last}, which another edit in the same "
                            "reply has already replaced, so these numbers no longer "
                            "name what you read. Read that part of the file again and "
                            "send this edit on its own.",
                        )
                shift = sum(added for _, done_last, added in batch.applied if done_last < first)
                if shift:
                    request = request.override(
                        tool_call={
                            **call,
                            "args": {**arguments, "start_line": first + shift, "end_line": last + shift},
                        }
                    )
                    logger.info(
                        "replace_lines on %s: lines %d-%d of the read are %d-%d after this "
                        "reply's earlier edits", where, first, last, first + shift, last + shift,
                    )
                before = _line_count(target)
                result = handler(request)
                after = _line_count(target)
                if not _is_error(result) and before is not None and after is not None:
                    batch.applied.append((first, last, after - before))
                return result

    return LineBatchMiddleware()


__all__ = ["build_line_batch_middleware"]
