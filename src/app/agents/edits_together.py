"""A reply's edits to one file that parse only together are made as one edit, so none is refused half-done.

Measured over 80 runs: 18 had replies whose several `edit_artifact` calls to one file each left it unparseable on its
own - a renamed function and its callers, a decorator and the line under it - and the parse check, which runs on each
call alone, refused all of them (54 edits in 23 bursts; 8 in one reply of one suite writer). Applied in order they
parse. After each model reply, the edits to one file are applied in order to its text: when one of them alone would
not parse and all of them together do, the reply's calls to that file become one `edit_artifact` from the file's
whole text to the combined text. That call is checked as any other - who owns the file, whether it parses - so no
stage can leave a broken file, and edits that do not parse together are left as sent, to be refused as before.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

EDIT = "edit_artifact"


def _apply(text: str, find: str, replace: str) -> str | None:
    """`text` with its one `find` replaced; None when the passage is absent or not unique."""
    return text.replace(find, replace, 1) if find and text.count(find) == 1 else None


def combined(relative_path: str, text: str, edits: list[tuple[str, str]]) -> str | None:
    """The file after all `edits` in order, when one alone would not parse and together they do; else None."""
    from app.analysis.syntax_balance import structural_problem

    if structural_problem(relative_path, text):
        return None  # already broken: not this reply's doing, and not for this to judge
    if not any(structural_problem(relative_path, one) for find, replace in edits
               if (one := _apply(text, find, replace)) is not None):
        return None  # each parses alone: nothing to combine
    result: str | None = text
    for find, replace in edits:
        result = _apply(result, find, replace) if result is not None else None
    if result is None or result == text or structural_problem(relative_path, result):
        return None
    return result


def together(message: Any, repo_root: str | Path) -> Any | None:
    """A copy of the reply with each file's edits that parse only together made one; None when nothing changes."""
    calls = list(getattr(message, "tool_calls", None) or [])
    by_path: dict[str, list[int]] = {}
    for at, call in enumerate(calls):
        if call.get("name") == EDIT:
            path = str((call.get("args") or {}).get("relative_path") or "").strip()
            if path:
                by_path.setdefault(path, []).append(at)
    replaced: dict[int, dict] = {}
    dropped: set[int] = set()
    root = Path(repo_root)
    for path, positions in by_path.items():
        if len(positions) < 2:
            continue
        try:
            text = (root / path.lstrip("/")).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        edits = [(str(calls[i]["args"].get("find") or ""), str(calls[i]["args"].get("replace") or "")) for i in positions]
        result = combined(path, text, edits)
        if result is None:
            continue
        first = positions[0]
        replaced[first] = {**calls[first], "args": {"relative_path": path, "find": text, "replace": result}}
        dropped.update(positions[1:])
        logger.info("%d edits to %s parse only together; made one edit", len(positions), path)
    if not replaced:
        return None
    kept = [replaced.get(at, call) for at, call in enumerate(calls) if at not in dropped]
    return message.model_copy(update={"tool_calls": kept})


def build_edits_together_middleware(repo_root: str | Path) -> Any:
    from langchain.agents.middleware import AgentMiddleware

    class EditsTogetherMiddleware(AgentMiddleware):
        def after_model(self, state: Any, runtime: Any = None) -> dict[str, Any] | None:
            # Never fails the stage: on any error the reply's calls go as they were sent.
            try:
                messages = list((state or {}).get("messages") or [])
                if not messages or getattr(messages[-1], "type", None) != "ai":
                    return None
                merged = together(messages[-1], repo_root)
                return {"messages": [merged]} if merged is not None else None
            except Exception:  # noqa: BLE001
                logger.debug("Could not combine a reply's edits", exc_info=True)
                return None

    return EditsTogetherMiddleware()


__all__ = ["build_edits_together_middleware", "combined", "together"]
