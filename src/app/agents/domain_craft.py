"""Short craft checklists by the domains of a work order's files, and the same bars for the advisers (plan SK.2,
with PQ.6 and PQ.9; `DOMAIN_CRAFT_CHECKLISTS`, off until measured).

A product review of eight stored products (`reports/audits/2026-11-25-product-quality-ui-db-api.md`) found them
correct and plain: pages with no empty, busy or failure state, raw colours beside the pack's design tokens, failed
contrast; data with no constraints, indexes or timestamps where the brief asked for a proper schema; services
answering 500 for a forbidden or duplicate request, ignoring a filter, with several error shapes. Its causes C5 and
C8: the UI/UX adviser was never told the pack ships design tokens, so it wrote raw colours into the specification;
and the database and backend advice requests asked for less than the UI/UX one did.

So, with the switch on:

- a builder's request (and each file drafted whole) carries a checklist of a few lines for each domain its files are
  in (`app.analysis.file_domains`): the interface, the data layer, the service;
- the UI/UX adviser and the architect are told which design tokens the run's pack ships and that the interface
  design names them, never raw values (PQ.6);
- the database and backend advisers are asked for the data and service bars (PQ.9), each inside "adds no rule that
  refuses what the brief allows".

The text here is generic; the token names come from the pack's own stylesheet (`app.stacks.packs`), so a stack's
specifics stay in its pack.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Iterable

from app.analysis.file_domains import ADVICE_ROLE, domains_of_files
from app.switches import is_on

logger = logging.getLogger(__name__)

ON_BY_DEFAULT = False
SWITCH = "DOMAIN_CRAFT_CHECKLISTS"


class _Craft:
    """`DOMAIN_CRAFT_CHECKLISTS` as the switch registry reads one: off in code until measured."""

    ON_BY_DEFAULT = ON_BY_DEFAULT
    #: What the admin page says this switch does.
    explanation = ("Builders get a short craft checklist for the kinds of file they write (interface: empty, busy "
                   "and failure states, design tokens, labels, contrast, phone layout; data: constraints, indexes, "
                   "created and changed times, migrations when asked; service: one error shape, the right status "
                   "codes, authorisation, no input ignored). The UI/UX adviser and the architect are told the pack's "
                   "design tokens, and the database and backend advisers are asked for the same bars.")

    @staticmethod
    def enabled() -> bool:
        return is_on(SWITCH, _Craft.ON_BY_DEFAULT)


craft_switch = _Craft()


def enabled() -> bool:
    return craft_switch.enabled()


#: The heading a builder's checklist comes under; also the switch's firing signal.
CHECKLIST_HEADING = "--- Craft checklist for your files ---"

#: One checklist per domain, a few lines each. `{tokens}` is where the pack's design tokens are named, when known.
CHECKLISTS: dict[str, str] = {
    "interface": (
        "The interface: what a person sees when there is nothing yet, while a request is in flight, and when one "
        "fails - each shown outside the list of records, never as an entry in it; colours, spacing and type sizes "
        "from the shared design tokens{tokens}, never a raw value where a token exists; a visible label for every "
        "field and control; text with enough contrast in the light and the dark scheme; and a layout that fits a "
        "phone's width with no sideways scrolling."
    ),
    "data": (
        "The data layer: the constraints the data implies, as far as the brief allows and never one that refuses "
        "what it allows - a required field, a value unique within one owner's records, a reference to another "
        "record with what happens to it when that record is deleted; an index on each field records are looked up, "
        "filtered or sorted by; when each record was created and last changed, stored with it and never returned "
        "where the contract's responses do not list it; and migrations when the brief asks for them."
    ),
    "service": (
        "The service: one error shape for every failure; the status code each failure calls for - a request that "
        "cannot be used, a record that is not there, a record that is not the caller's, a conflict with one that "
        "exists - never a 500 for any of them; where records belong to a person, who may read or change one is "
        "checked on every route that touches it; and no input accepted and then ignored - a filter, field or option "
        "the contract names is applied, or refused with a 4xx."
    ),
}

#: What the database and backend advisers are asked for besides their usual cover (PQ.9).
_ADVISER_BARS = {
    "database": "data",
    "backend": "service",
}
_BARS_LEAD = ("Cover these bars too, each only as far as the brief allows - none may add a rule that refuses or "
              "limits what the brief allows, and a stored field the brief does not list is never returned: ")

#: A CSS custom property declared in a stylesheet: `--color-text: #1b1f24;`.
_CUSTOM_PROPERTY = re.compile(r"(?m)^\s*(--[A-Za-z0-9_-]+)\s*:")
_STYLESHEET = re.compile(r"\.(css|scss|sass|less|styl)$", re.I)


def design_tokens(pack: Any) -> tuple[str, list[str]]:
    """The stylesheet a pack's scaffold writes design tokens in, and the token names, in order; ("", []) when it
    ships none. Read from the pack's own files, so every pack that carries tokens is covered."""
    for path, content in (getattr(pack, "files", None) or {}).items():
        if not _STYLESHEET.search(str(path)):
            continue
        names = list(dict.fromkeys(_CUSTOM_PROPERTY.findall(str(content or ""))))
        if names:
            return str(path), names
    return "", []


def _shown(pack: Any, path: str, project: str = "", package: str = "") -> str:
    """The stylesheet's path as the project names it: the pack's placeholders filled where the names are known."""
    try:
        if project:
            path = pack.filled(path, project, "", package or None)
    except Exception:  # noqa: BLE001 - the path as the pack writes it
        pass
    path = path.replace("{{package}}", "<package>").replace("{{project}}", "<project>")
    return f"{project}/{path}" if project and not path.startswith(f"{project}/") else path


def _pack(name_or_pack: Any) -> Any:
    if name_or_pack is None or not isinstance(name_or_pack, str):
        return name_or_pack
    from app.stacks import pack_named

    return pack_named(name_or_pack)


def tokens_note(pack: Any) -> str:
    """What the UI/UX adviser and the architect are told of the pack's design tokens (PQ.6); "" when the switch is
    off or the pack ships none. Never raises."""
    try:
        if not enabled():
            return ""
        pack = _pack(pack)
        path, names = design_tokens(pack)
    except Exception:  # noqa: BLE001 - asked as before
        return ""
    if not names:
        return ""
    path = _shown(pack, path)
    return (
        "--- The design tokens the scaffold ships ---\n"
        f"The project's stylesheet `{path}` starts with these design tokens: "
        + ", ".join(f"`{name}`" for name in names)
        + ". The interface design names these tokens (`var(--color-primary)`) for every colour, space, type size "
        "and radius it gives, never a raw value; a product may change a token's value, never write a second set "
        "beside it.\n\n"
    )


def for_an_adviser(request: dict[str, Any], role: str, pack: Any) -> dict[str, Any]:
    """An adviser's request with the bars of its domain (PQ.9) and, for the UI/UX adviser, the pack's tokens (PQ.6);
    as it was when the switch is off. Never raises."""
    try:
        if not enabled() or not request.get("messages"):
            return request
        added = ""
        if role in _ADVISER_BARS:
            added = "\n\n" + _BARS_LEAD + CHECKLISTS[_ADVISER_BARS[role]].format(tokens="").split(": ", 1)[1]
        elif role == "ui_ux":
            added = "\n\n" + tokens_note(pack).rstrip()
        if added.strip() and isinstance(request["messages"][-1].get("content"), str):
            request["messages"][-1]["content"] += added
    except Exception:  # noqa: BLE001 - the request stands as it was
        logger.debug("Could not add the craft bars to an adviser's request", exc_info=True)
    return request


def _tokens_clause(pack: Any, project: str, package: str = "") -> str:
    path, names = design_tokens(pack) if pack is not None else ("", [])
    if not names:
        return ""
    where = _shown(pack, path, project, package)
    shown = ", ".join(f"`{name}`" for name in names[:8]) + (", ..." if len(names) > 8 else "")
    return f" (`{where}` declares them: {shown})"


def checklist(role: str, files: Iterable[str], pack: Any = None, project: str = "", package: str = "") -> str:
    """The craft checklist for the domains `files` are in and `role`'s own; "" when the switch is off or none
    applies. `pack` names the design tokens the interface line points to."""
    if not enabled() or role not in {"ui_ux", "database", "backend", "security_reliability"}:
        return ""
    domains = list(domains_of_files(files))
    own = next((domain for domain, owner in ADVICE_ROLE.items() if owner == role), "")
    if own and own not in domains:
        domains.insert(0, own)
    lines = [
        "- " + CHECKLISTS[domain].format(tokens=_tokens_clause(pack, project, package) if domain == "interface" else "")
        for domain in ("interface", "data", "service") if domain in domains
    ]
    if not lines:
        return ""
    return CHECKLIST_HEADING + "\nCheck your work against each line before you answer:\n" + "\n".join(lines) + "\n\n"


def _the_pack_built(repo_root: Any) -> tuple[Any, str, str]:
    """The pack the workspace was scaffolded from, its project directory and package; (None, "", "") for none."""
    try:
        from app.stacks.contract import the_pack

        found = the_pack(repo_root)
        if found is None:
            return None, "", ""
        return found[0], str(found[1].get("project") or ""), str(found[1].get("package") or "")
    except Exception:  # noqa: BLE001 - no pack, no token names
        return None, "", ""


def with_it(request: dict[str, Any], state: Any, work_order: Any) -> dict[str, Any]:
    """A builder's request with its work order's checklist appended; as it was when off or none applies. Never
    raises."""
    try:
        if not enabled():
            return request
        pack, project, package = _the_pack_built(getattr(state.get("repository"), "root_path", None))
        block = checklist(str(getattr(work_order, "specialist_role", "") or ""),
                          [str(p) for p in getattr(work_order, "files", None) or []], pack, project, package)
        if block and request.get("messages") and isinstance(request["messages"][-1].get("content"), str):
            request["messages"][-1]["content"] += "\n\n" + block.rstrip() + "\n"
    except Exception:  # noqa: BLE001 - the request stands as it was
        logger.debug("Could not add the craft checklist to a builder's request", exc_info=True)
    return request


def for_a_draft(root: str | Path, work_order: Any, path: str) -> str:
    """The checklist for one file drafted whole; "" when off or none applies. Never raises."""
    try:
        if not enabled():
            return ""
        pack, project, package = _the_pack_built(root)
        return checklist(str(getattr(work_order, "specialist_role", "") or ""), [path], pack, project, package).strip()
    except Exception:  # noqa: BLE001 - the draft is asked as before
        return ""


__all__ = ["CHECKLISTS", "CHECKLIST_HEADING", "ON_BY_DEFAULT", "SWITCH", "checklist", "craft_switch",
           "design_tokens", "enabled", "for_a_draft", "for_an_adviser", "tokens_note", "with_it"]
