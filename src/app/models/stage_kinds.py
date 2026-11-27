"""Which kind of stage call a request is - a working step, a reading stage's call, an opening - read from the request
alone (DX.7).

The reasoning a model spends differs most by what the call is for, not by which role makes it: measured over every
captured transcript, a working stage's steps after tool results reasoned a median of 220 tokens (p90 2,290), and a
stage offered only reads and its answer a median of 1,783 (p90 12,887) - the design, plan and review stages, whose
requests reasoned 30,000-44,000 tokens on one model (`step_budget`, LF.1593; the 2026-11-27 diagnosis design,
section 1). So a setting measured per kind - effort, reasoning budget, reply cap - is chosen by the same three kinds,
from the request's tools and conversation, never by a stage's or a product's name:

- **step**: offered a tool that changes a file or runs a command, its conversation already holds tool results, and
  not a call where only the answer is allowed - a working stage's step;
- **reading**: offered no such tool - a stage that reads and answers: the designs, plans and reviews (the request
  does not tell a design from a review: the harness offers both the same tools);
- **opening**: any other - a working stage's opening call, where it plans its work, or a call only its answer may
  end.
"""
from __future__ import annotations

from typing import Any, Iterable

KINDS = ("step", "reading", "opening")

#: The tools that change a file or run a command (`step_budget`'s list): a stage offered one works in its loop.
ACTING_TOOLS = frozenset({"write_artifact", "edit_artifact", "replace_lines", "replace_approved_lines",
                          "delete_artifact", "move_artifact", "run_terminal_command", "run_validation"})


def kind(tool_names: Iterable[str], holds_tool_results: bool, answer_only: bool = False) -> str:
    """The kind of a call offered `tool_names`, whose conversation holds tool results or not."""
    if not set(tool_names) & ACTING_TOOLS:
        return "reading"
    if holds_tool_results and not answer_only:
        return "step"
    return "opening"


def _role(message: Any) -> str:
    if isinstance(message, dict):
        return str(message.get("role") or message.get("type") or "")
    return str(getattr(message, "type", "") or "")


def of_payload(payload: dict, messages: list[Any] | None = None) -> str:
    """The kind of the request `payload` (an OpenAI-style body), its conversation `messages` where known."""
    names = [str((tool.get("function") or {}).get("name") or tool.get("name") or "")
             for tool in payload.get("tools") or () if isinstance(tool, dict)]
    held = messages or payload.get("messages") or []
    try:
        from app.models.named_answer import asked_for

        answer_only = bool(asked_for()) or isinstance(payload.get("tool_choice"), dict)
    except Exception:  # noqa: BLE001
        answer_only = isinstance(payload.get("tool_choice"), dict)
    return kind(names, any(_role(m) == "tool" for m in held), answer_only)


__all__ = ["ACTING_TOOLS", "KINDS", "kind", "of_payload"]
