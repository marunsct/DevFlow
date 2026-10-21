"""A "where things stand" block at the start of every builder and fixer request (plan PH.1, behind `WHERE_THINGS_STAND`).

A builder or fixer started each visit from the request and the files, and
found out what the sprint had already done by reading: the work orders that
finished, what they decided, what the last measurement said. The harness
holds all of it. This writes it once, at most `MOST_CHARACTERS`: the sprint's
finished work orders (files changed, first decision), the blockers they left,
the last CI gate's verdict, and the acceptance suite's last measurement.
Never model-written.

Behind its own switch, `STATE_AT_DISPATCH` (plan PH.4): the CI gate's verdict
is a measurement of one commit, and a builder dispatched after a sibling
changed files read it as the product's state now. With the switch on, the
block names the files changed since that commit and says the verdict may no
longer hold - no sandbox run, only what git already knows.
"""

from __future__ import annotations

import logging
from typing import Any

from app.switches import is_on

logger = logging.getLogger(__name__)

#: `WHERE_THINGS_STAND` set to on or off overrides this.
ON_BY_DEFAULT = False
#: Characters of the block, at most.
MOST_CHARACTERS = 2_000
#: How the block begins.
HEADING = "--- Where things stand (written by the harness from what it measured) ---"


def enabled() -> bool:
    return is_on("WHERE_THINGS_STAND", ON_BY_DEFAULT)


class _StateAtDispatch:
    """PH.4's switch: `STATE_AT_DISPATCH`, off until measured."""

    ON_BY_DEFAULT = False

    @staticmethod
    def enabled() -> bool:
        return is_on("STATE_AT_DISPATCH", _StateAtDispatch.ON_BY_DEFAULT)


state_at_dispatch = _StateAtDispatch()
#: Paths the harness itself writes; a change to them is not a change to the product.
_THE_HARNESS_S_OWN = (".harness/", "docs/", ".project-")


def _changed_since_the_gate(state: Any) -> str:
    """A line naming the files changed since the CI gate measured, or "". Never raises."""
    if not state_at_dispatch.enabled() or not state.get("ci_batch_commit"):
        return ""
    try:
        from app.tools.version_control import changed_since

        changed = [p for p in changed_since(state["repository"].root_path, str(state["ci_batch_commit"]))
                   if not p.startswith(_THE_HARNESS_S_OWN)]
    except Exception:  # noqa: BLE001 - no line rather than a wrong one
        return ""
    if not changed:
        return ""
    shown = ", ".join(f"`{p}`" for p in changed[:8]) + (f" and {len(changed) - 8} more" if len(changed) > 8 else "")
    return (f"- Changed since that measurement: {shown}. It may no longer hold; run the product's "
            "tests before building on it.")


def _finished(outputs: Any, leave_out: str) -> list[str]:
    lines: list[str] = []
    for stage, output in (outputs or {}).items():
        if stage == leave_out or not str(stage).startswith(("specialist_", "defect_fix_")):
            continue
        files = [str(f) for f in (getattr(output, "changed_files", None) or [])][:5]
        decisions = [str(d) for d in (getattr(output, "decisions", None) or []) if str(d).strip()]
        if not files and not decisions:
            continue
        line = f"- {stage}: " + (", ".join(f"`{f}`" for f in files) or "no files")
        if decisions:
            line += " - " + " ".join(decisions[0].split())[:160]
        lines.append(line)
    return lines


def _blockers(outputs: Any, leave_out: str) -> list[str]:
    found = [
        f"- {stage}: " + " ".join(str(b).split())[:200]
        for stage, output in (outputs or {}).items() if stage != leave_out
        for b in (getattr(output, "blockers", None) or []) if str(b).strip()
    ]
    return found[:3]


def _the_suite(root: str) -> str:
    try:
        from app.acceptance import suite

        result = suite.last_result(root) or {}
        criteria = result.get("criteria") or {}
        if not criteria:
            return ""
        failing = sorted(cid for cid, c in criteria.items() if (c or {}).get("status") not in ("passed", "deferred"))
        passing = sum(1 for c in criteria.values() if (c or {}).get("status") == "passed")
        return (f"- The acceptance suite last measured {passing} of {len(criteria)} criteria passing"
                + (f"; failing: {', '.join(failing[:12])}" if failing else "") + ".")
    except Exception:  # noqa: BLE001 - no measurement is no line
        return ""


def block(state: Any, leave_out: str = "") -> str:
    """The block for a request, or "" when off or there is nothing to say. Never raises."""
    if not enabled():
        return ""
    try:
        outputs = state.get("specialist_outputs") or {}
        lines: list[str] = []
        finished = _finished(outputs, leave_out)
        if finished:
            lines += ["Finished this sprint:", *finished]
        blockers = _blockers(outputs, leave_out)
        if blockers:
            lines += ["Left open by them:", *blockers]
        ci = " ".join(str(state.get("ci_report") or "").split())
        if ci:
            lines.append(f"- The last CI gate: {ci[:300]}")
            since = _changed_since_the_gate(state)
            if since:
                lines.append(since)
        measured = _the_suite(state["repository"].root_path)
        if measured:
            lines.append(measured)
        if not lines:
            return ""
        text = HEADING + "\n" + "\n".join(lines)
        return text[:MOST_CHARACTERS].rstrip() + "\n"
    except Exception:  # noqa: BLE001 - the request stands as it was
        logger.debug("Could not write where things stand", exc_info=True)
        return ""


def with_it(request: dict[str, Any], state: Any, leave_out: str = "") -> dict[str, Any]:
    """`request` with the block put before its last message's text; as it was when off or empty."""
    text = block(state, leave_out)
    if text and request.get("messages") and isinstance(request["messages"][-1].get("content"), str):
        request["messages"][-1]["content"] = text + "\n" + request["messages"][-1]["content"]
    return request


__all__ = ["HEADING", "MOST_CHARACTERS", "ON_BY_DEFAULT", "block", "enabled", "state_at_dispatch", "with_it"]
