"""The specialists' advice reviews of a sprint as one call, when their advice fits one request (plan PA.9, the rest).

Measured on a medium run: after each sprint the UI/UX, database, backend and security-and-reliability reviews each
opened with about 32,000 tokens of input - the same project memory, sprint and changed files four times over - to
check 6-10 adopted items each; on small runs the advice reviews took 25 minutes in 6 runs (4% of model time, 96% of
their output reasoning) and can only find "not built" lines. The plan's one call for all specialists was never built.

So when two or more specialists have items due and their items together fit one request (`roles_together`), one
reviewer is shown each specialist's items under its own heading and the sprint, its changed files and the files held
for it once (`build_request`); it answers in the same schema, every line starting with the item's id, and the
answer is split back to each specialist by the id's prefix (`split`), so the milestone review, the Sprint Record
and the send-back of an item owed (SP.1) read each specialist's findings as before.

Each review stays its own call when it needs what one call cannot give: a UI/UX reviewer whose model reads images
(it is shown the page as screenshots), every role while `SPECIALIST_DOMAIN_REVIEW` is on (each also reviews its own
domain, with its own schema), and items too long for one request. Always on: a quality-neutral merge of the same
check, and the requests it removes are measured (advice-review minutes and input tokens per sprint).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Mapping, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver

from app.agents.structured_response import STRUCTURED_RESPONSE_RULE

logger = logging.getLogger(__name__)

#: The name the one call goes by among the sprint's reviews, and in its stage name (`advice_review_together`).
TOGETHER = "together"
#: The share of the request room the specialists' items may take together; the rest is memory, files and reads.
ROOM_SHARE = 0.25
#: The items' characters together when the room is not known.
MOST_CHARACTERS = 12_000

_SYSTEM_PROMPT = (
    "You check, for several specialists of a product team at once, whether a sprint built what they advised. Before "
    "the specification was written each advised the architect, and the specification adopted some of that advice. "
    "Now a sprint's work is done. The request lists each specialist's adopted items under its own heading. Read the "
    "code that was built - the changed files first - before deciding. When a heading says the items listed are due, "
    "every one of them is due now. Otherwise an item is due when this sprint, or an earlier one, built the part of the "
    "product it is about; an item about a part a later sprint builds is not missing yet and is not reported. Report "
    "only what you can point to in the code - a file, and what is there or is not - never a guess. Start every line "
    "with the id of the item it is about, as the request gives it. When everything due is built, return empty lists: "
    "an empty answer is a good answer. You write no code and no files.\n\n"
    + STRUCTURED_RESPONSE_RULE
)


def _room_characters() -> int:
    """The characters the specialists' items may take in one request: a share of the request room, else a fixed cap."""
    try:
        from app.models.request_fit import chars_per_token, room_tokens

        room = room_tokens()
        if room:
            return int(room * chars_per_token() * ROOM_SHARE)
    except Exception:  # noqa: BLE001 - the fixed cap
        pass
    return MOST_CHARACTERS


def roles_together(
    due: Mapping[str, Sequence[str]], *, sees_images: bool, domain_review: bool, room_characters: int | None = None,
) -> list[str]:
    """The roles among `due` (each role's items due now) reviewed in one call, in their order; [] for one call each.

    Never a UI/UX reviewer whose model reads images, never while each role also reviews its own domain, and only when
    two or more roles are left and their items fit `room_characters` (a share of the request room by default)."""
    if domain_review:
        return []
    roles = [role for role, items in due.items() if items and not (role == "ui_ux" and sees_images)]
    if len(roles) < 2:
        return []
    room = room_characters if room_characters is not None else _room_characters()
    if sum(len(str(item)) + 3 for role in roles for item in due[role]) > room:
        return []
    return roles


def build_request(
    due: Mapping[str, tuple[Sequence[str], str]],
    sprint_goal: str,
    sprint_scope: str,
    changed_files: Sequence[str],
    held: Sequence[str] = (),
) -> dict[str, list[dict[str, str]]]:
    """The one request: each role's items under its own heading - with why they are due now, when the sprint plan says
    - then the sprint, its changed files and the files held for it, once."""
    from app.agents.advice_review import _where_the_files_are
    from app.agents.specialist_advice import ROLE_TITLE

    sections = []
    for role, (items, due_because) in due.items():
        title = ROLE_TITLE.get(role, role)
        heading = (f"--- The {title}'s advice the specification adopted, due now: {due_because} ---"
                   if due_because else f"--- The {title}'s advice the specification adopted ---")
        sections.append(heading + "\n" + ("\n".join(f"- {item}" for item in items) or "- (none)"))
    files = "\n".join(f"- {name}" for name in changed_files) or "- (none recorded)"
    content = (
        "The workspace is rooted at '/'; all paths you use are relative to it.\n\n"
        + "\n\n".join(sections)
        + f"\n\n--- The sprint just finished ---\n{sprint_goal}\n\n"
        f"{sprint_scope}"
        f"--- The files it changed ---\n{files}\n\n"
        + _where_the_files_are(held)
        + "For each specialist above, check each of its items against the code and report the ones not built, each "
        "line starting with the item's id."
    )
    return {"messages": [{"role": "user", "content": content}]}


def split(roles: Sequence[str], answer: Any, due_ids: Mapping[str, Sequence[str]]) -> dict[str, list[str]]:
    """The one answer as each role's findings, as `advice_review.findings_from` gives them for one role's review.

    A line goes to the role its item's id belongs to; a line naming no item of any role, and every design line, go to
    the first role - the UI/UX specialist's when it is one, since only it is shown the page."""
    from app.agents.advice_review import AdviceReview, ITEM_ID, findings_from
    from app.agents.specialist_advice import ID_PREFIX

    roles = list(roles)
    if not roles:
        return {}
    first = "ui_ux" if "ui_ux" in roles else roles[0]
    by_prefix = {ID_PREFIX.get(role, ""): role for role in roles}
    lines: dict[str, list[str]] = {role: [] for role in roles}
    for line in getattr(answer, "not_built", None) or []:
        named = ITEM_ID.search(str(line)[:40])
        role = by_prefix.get(named.group(0).split("-", 1)[0], first) if named else first
        lines[role].append(str(line))
    found: dict[str, list[str]] = {}
    for role in roles:
        one = AdviceReview(
            not_built=lines[role],
            design_problems=list(getattr(answer, "design_problems", None) or []) if role == first else [],
        )
        found[role] = findings_from(role, one, due_ids.get(role))
    return found


def create_agent(
    model: str | BaseChatModel | None = None,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    repo_root: str | Path | None = None,
    allow_subdirectories: bool = True,
) -> Any:
    """The agent that checks several roles' adopted advice in one call. It reads; it writes nothing."""
    from app.agents.advice_review import AdviceReview
    from app.agents.role_agent import create_role_agent

    return create_role_agent(
        name=f"{TOGETHER}_advice_reviewer",
        stage="advice_review",
        system_prompt=_SYSTEM_PROMPT,
        response_format=AdviceReview,
        model=model,
        checkpointer=checkpointer,
        repo_root=repo_root,
        allow_subdirectories=allow_subdirectories,
        can_write=False,
    )


__all__ = ["MOST_CHARACTERS", "ROOM_SHARE", "TOGETHER", "build_request", "create_agent", "roles_together", "split"]
