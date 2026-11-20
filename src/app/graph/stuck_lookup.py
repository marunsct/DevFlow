"""A stuck fixer is shown what others found for its error: the harness looks it up, not the model (plan WL.4).

Behind `WEB_LOOKUP_WHEN_STUCK` (off in code; the compose file and each run's own setting say whether it is on - the
user's control). Measured the night it was built: the local model, offered search tools in about 3,500 requests,
never called them, and every open-source harness researched leaves that decision to the model. So the harness decides:
a defect shown to a fixer again after an attempt that did not close it, whose text states a concrete error, is looked
up once (`app.tools.lookups` - free official sources first, a week's cache, only the cleaned error sent), and what was
found goes into the fixer's request as quoted leads. Each lookup is a ledger record, so the audit can say whether it
fired and helped.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.switches import is_on

logger = logging.getLogger(__name__)

#: `WEB_LOOKUP_WHEN_STUCK` set to on or off overrides this.
ON_BY_DEFAULT = False
#: The ledger's event for a lookup made.
LOOKUP_EVENT = "lookup"

#: (workspace, cleaned query) already looked up in this process: one lookup per error per run.
_DONE: dict[tuple[str, str], str] = {}


def enabled() -> bool:
    return is_on("WEB_LOOKUP_WHEN_STUCK", ON_BY_DEFAULT)


def _stuck(defect: Any) -> bool:
    """Whether an earlier attempt at this defect ended without closing it."""
    return any(isinstance(a, dict) and str(a.get("outcome") or "") not in {"", "fixed"}
               for a in getattr(defect, "attempts", None) or [])


def _the_error_line(defect: Any) -> str:
    """The last error the defect's text states, or "" - a criterion's prose ("does not work yet") is not searchable."""
    from app.acceptance.what_went_wrong import the_errors_stated

    stated = the_errors_stated(f"{getattr(defect, 'actual_behavior', '') or ''}\n{getattr(defect, 'description', '')}")
    return stated[-1] if stated else ""


def _the_stack_s_words(stack: Any) -> str:
    return " ".join(str(getattr(stack, field, "") or "") for field in ("language", "framework") if getattr(stack, field, ""))


def _the_private_words(repo_root: str | Path) -> list[str]:
    """Names that are the product's, never sent: the project's folder and the workspace's name."""
    words = [Path(repo_root).name]
    try:
        from app.stacks import contract

        record = contract.read(repo_root) or {}
        words += [str(record.get("project") or ""), str(record.get("title") or "")]
    except Exception:  # noqa: BLE001 - the folder's name alone
        pass
    return [w for w in words if w]


def section(repo_root: str | Path, defect: Any, stack: Any, stage_name: str = "defect_fix") -> str:
    """What others found for this stuck defect's error, as its fixer's request carries it; "" when off, not stuck,
    with no concrete error, already looked up in this run, or when nothing was found. Never raises."""
    try:
        if not enabled() or not _stuck(defect):
            return ""
        from app.acceptance import mutation_guided

        if mutation_guided.is_a_finding(defect):
            return ""
        error = _the_error_line(defect)
        if not error:
            return ""
        from app.tools import lookups

        private = _the_private_words(repo_root)
        key = (str(repo_root), lookups.cleaned(error, private))
        if key in _DONE:
            return _DONE[key]
        answer = lookups.look_up(error, _the_stack_s_words(stack), private)
        shown = lookups.as_a_section(answer)
        shown = ("\n" + shown) if shown else ""
        _DONE[key] = shown
        try:
            from app.observability import defect_ledger

            defect_ledger.note(LOOKUP_EVENT, stage_name, defect=defect, detail=(
                f"searched {answer.get('query')!r}: {len(answer.get('found') or [])} found"
                + (" (cached)" if answer.get("cached") else f" from {', '.join(answer.get('asked') or [])}")))
        except Exception:  # noqa: BLE001 - a record must never fail the fix
            pass
        return shown
    except Exception:  # noqa: BLE001 - the fix goes on without it
        logger.debug("Could not look up a stuck defect's error", exc_info=True)
        return ""


__all__ = ["LOOKUP_EVENT", "ON_BY_DEFAULT", "enabled", "section"]
