"""A work order carries the adopted advice of the domains its files are in, and goes to the role that owns them
(plan SK.1, always on: a bug).

The specialists advise before the specification, and the architect adopts or declines each item by id
(`app.agents.specialist_advice`). A builder was handed only the items its lead chose to name. Measured on a medium run
(thorough delivery, a Python service with a React page): only the backend and testing builders ran, and the backend
builder's first request named BE-2 and SR-8 of the adopted items - none of the database specialist's DB items - while
it wrote the database models. The models had integer ids where the specification adopted UUIDs, no timestamps and no
indexes, and the database specialist then reported each of those items as not built.

So the harness reads, mechanically, which domains a work order's files are in (`app.analysis.file_domains`) and hands
its builder every adopted item of those domains' specialists - with its own role's - bounded in size. A work order
whose files are mainly one owning domain goes to the role that owns it; one spanning domains keeps its role, and its
builder is also given the other domains' role guidance, one line each. The same items and lines reach a file drafted
whole from the specification (`app.graph.drafting.draft_request`).
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

from app.analysis.file_domains import ADVICE_ROLE, BUILDER_ROLES, OWNER, domains_of_files, main_domain

logger = logging.getLogger(__name__)

#: The roles whose work orders build the product and so carry advice and guidance.
_BUILDS = frozenset({*BUILDER_ROLES, "security_reliability"})

#: The longest one adopted item is shown at, and the most characters of items one request carries.
MOST_ITEM_CHARACTERS = 360
MOST_ADVICE_CHARACTERS = 4_000

ADVICE_HEADING = "--- The specialists' adopted advice for your files (build to it; each item is checked against your work) ---"
GUIDANCE_HEADING = "--- Your files in another specialist's domain ---"

#: What a builder is told for files in a domain another role owns: the role's guidance, one line.
ROLE_GUIDANCE: dict[str, str] = {
    "data": (
        "build them as the database specialist would - every kind of record, its fields and types, how a record is "
        "identified and which fields are required, exactly as the specification's data model and the adopted "
        "database advice give them; stored and loaded the way this run's stack chose; and what must stay consistent "
        "between records kept so."
    ),
    "service": (
        "build them as the backend specialist would - each operation accepts and returns exactly what the interface "
        "contract says, its input is checked before anything is read or stored, and each failure is answered with "
        "the status code and message the specification gives."
    ),
    "interface": (
        "build them as the UI/UX specialist would - to the specification's interface design: the layout at a "
        "phone's width and a desktop's, each control's states, the feedback after each action, a label for every "
        "control, and the visual style, styled rather than left in the browser's defaults."
    ),
    "security": (
        "build them as the security specialist would - who may do what is checked on every operation that reads or "
        "changes a record, a secret is never logged or sent to the client, and a password is kept only as a salted "
        "hash."
    ),
}
_DOMAIN_TITLE = {"data": "The data layer", "service": "The service", "interface": "The interface",
                 "security": "Sign-in and authorisation"}


def _role_of(work_order: Any) -> str:
    return str(getattr(work_order, "specialist_role", "") or "")


def _files_of(work_order: Any) -> list[str]:
    return [str(path) for path in getattr(work_order, "files", None) or [] if str(path).strip()]


def _named(files: Iterable[str], most: int = 4) -> str:
    listed = list(files)
    shown = ", ".join(f"`{path}`" for path in listed[:most])
    return shown + (f" and {len(listed) - most} more" if len(listed) > most else "")


def _clipped(item: str) -> str:
    text = " ".join(str(item).split())
    return text if len(text) <= MOST_ITEM_CHARACTERS else text[:MOST_ITEM_CHARACTERS - 3].rstrip() + "..."


def advice_section(advice: dict[str, list[str]] | None, specification: Any, role: str, files: Iterable[str]) -> str:
    """The adopted items of each specialist whose domain `files` touch, and of `role` itself, as one bounded block;
    "" for a role that builds nothing, or when no item applies."""
    if role not in _BUILDS or not advice or specification is None:
        return ""
    from app.agents.specialist_advice import ROLE_TITLE, adopted

    by_domain = domains_of_files(files)
    # Its own role's items first, then each touched domain's, each role once.
    roles: list[tuple[str, list[str]]] = [(role, [])]
    for domain, paths in by_domain.items():
        owner = ADVICE_ROLE[domain]
        if owner == role:
            roles[0] = (role, paths)
        elif owner not in [r for r, _ in roles]:
            roles.append((owner, paths))
    lines: list[str] = []
    used = 0
    left_out = 0
    for owner, paths in roles:
        items = adopted(advice, specification, owner)
        if not items:
            continue
        head = f"The {ROLE_TITLE.get(owner, owner)}, for " + (_named(paths) if paths else "this work order") + ":"
        kept: list[str] = []
        for item in items:
            line = f"- {_clipped(item)}"
            if used + len(line) > MOST_ADVICE_CHARACTERS:
                left_out += 1
                continue
            kept.append(line)
            used += len(line)
        if kept:
            lines += [head, *kept]
    if not lines:
        return ""
    if left_out:
        lines.append(f"({left_out} more adopted item(s) are in the specification's Specialist Advice and Decisions.)")
    return ADVICE_HEADING + "\n" + "\n".join(lines) + "\n\n"


def guidance_section(role: str, files: Iterable[str]) -> str:
    """One guidance line for each domain the files touch that another role owns; "" when none does."""
    if role not in _BUILDS:
        return ""
    lines = [
        f"- {_DOMAIN_TITLE[domain]} ({_named(paths)}): {ROLE_GUIDANCE[domain]}"
        for domain, paths in domains_of_files(files).items()
        if ADVICE_ROLE[domain] != role
    ]
    return GUIDANCE_HEADING + "\n" + "\n".join(lines) + "\n\n" if lines else ""


def for_a_work_order(advice: dict[str, list[str]] | None, specification: Any, work_order: Any) -> str:
    """The adopted advice and the other domains' guidance for one work order's builder; "" when none applies."""
    role, files = _role_of(work_order), _files_of(work_order)
    return advice_section(advice, specification, role, files) + guidance_section(role, files)


def for_a_draft(advice: dict[str, list[str]] | None, specification: Any, work_order: Any, path: str) -> str:
    """The same for one file drafted whole from the specification. Never raises."""
    try:
        role = _role_of(work_order)
        return (advice_section(advice, specification, role, [path]) + guidance_section(role, [path])).strip()
    except Exception:  # noqa: BLE001 - the draft is asked as before
        logger.debug("Could not add the domain advice to a draft", exc_info=True)
        return ""


def with_it(request: dict[str, Any], state: Any, work_order: Any) -> dict[str, Any]:
    """`request` with the work order's domain advice and guidance appended; as it was when none applies. Never
    raises."""
    try:
        block = for_a_work_order(state.get("specialist_advice"), state.get("technical_specification"), work_order)
        if block and request.get("messages") and isinstance(request["messages"][-1].get("content"), str):
            request["messages"][-1]["content"] += "\n\n" + block.rstrip() + "\n"
    except Exception:  # noqa: BLE001 - the request stands as it was
        logger.debug("Could not add the domain advice to a builder's request", exc_info=True)
    return request


def owner_by_domain(work_order: Any) -> str:
    """The role a builder's work order goes to: the owner of the domain more than half its files are in, else its
    own role. A testing, documentation or security work order keeps its role."""
    role = _role_of(work_order)
    if role not in BUILDER_ROLES:
        return role
    return OWNER.get(main_domain(_files_of(work_order)), role)


def with_roles_owning_their_domains(plan: Any) -> tuple[Any, list[str]]:
    """`plan` with each builder's work order given to the role owning its files' main domain, and one line per
    order moved ("<title>: backend -> database"). The plan as it was when none moves. Never raises."""
    try:
        tasks = list(getattr(plan, "delegated_tasks", None) or [])
        moved: list[str] = []
        changed = []
        for task in tasks:
            owner = owner_by_domain(task)
            if owner and owner != _role_of(task):
                moved.append(f"{getattr(task, 'title', '') or _named(_files_of(task))}: {_role_of(task)} -> {owner}")
                task = task.model_copy(update={"specialist_role": owner})
            changed.append(task)
        if not moved:
            return plan, []
        return plan.model_copy(update={"delegated_tasks": changed}), moved
    except Exception:  # noqa: BLE001 - the lead's roles stand
        logger.debug("Could not give work orders to the roles owning their domains", exc_info=True)
        return plan, []


__all__ = ["ADVICE_HEADING", "GUIDANCE_HEADING", "MOST_ADVICE_CHARACTERS", "ROLE_GUIDANCE", "advice_section",
           "for_a_draft", "for_a_work_order", "guidance_section", "owner_by_domain", "with_it",
           "with_roles_owning_their_domains"]
