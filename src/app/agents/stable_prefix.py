"""A stage's system prompt and project memory kept byte for byte through its calls, and a shorter memory for a small product (behind `STABLE_STAGE_PREFIX`).

A server's prompt cache reuses only a byte-identical prefix, and the prefix of a call is its system prompt, the tools,
then the opening messages with the project memory. The memory is already taken once per stage visit; what still
changed the start of a call mid-stage was the instructions the plugins append to the system prompt - the stack's
guidance, the lessons, the owner's direction - read again on every call, so a stack document written mid-stage, a
lesson approved, a transient failure of the keyword lookup (an empty list for one call) or a note the owner added each
rewrote the system prompt and the server prefilled the whole conversation again. With the switch on, the system prompt
keeps the instructions as the stage's first call that had any read them; what a later call would add is sent at the
end of that call, after the transcript, as the text it adds, and a call that reads fewer instructions than the
stage began with leaves the system prompt as it was. Nothing is withheld: the model reads every instruction it read
before, only where it sits moves.

A product of fewer than `SMALL_PRODUCT_FILES` files has its memory made mostly of documents: the specification, the
sprint plan, the acceptance criteria and tests, the milestone plan. Held whole they are the larger share of every
call's prefix and the model reads little of them past its first calls. With the switch on, such a product's documents
longer than `SMALL_DOCUMENT_CHARACTERS` are held as their outline and the sections the request points at (the digest a
document too large to hold already gets), the rest to be read by line; the code is held whole as before.
"""

from __future__ import annotations

from typing import Any

from app.switches import is_on

#: `STABLE_STAGE_PREFIX` set to on or off overrides this.
ON_BY_DEFAULT = False
#: A product with fewer files than this (not counting its documents) has the shorter memory.
SMALL_PRODUCT_FILES = 20
#: The longest a document is held whole in a small product's memory, in characters; a longer one is held as its digest.
SMALL_DOCUMENT_CHARACTERS = 12_000
#: How the text a later call adds to the held instructions begins.
ADDED_NOTE = "[Instructions that apply from here on, added since this stage began]"


class _StableStagePrefix:
    """`STABLE_STAGE_PREFIX` as the switch registry reads one: off in code and in compose until measured."""

    ON_BY_DEFAULT = ON_BY_DEFAULT
    #: What the admin page says this switch does.
    explanation = ("A stage keeps its system prompt as its first call read it (what a later call would add goes to "
                   "the end of that call), and a product of under 20 files holds long documents as their outline "
                   "and the sections the request points at, so a server's prompt cache reuses the whole prefix "
                   "through the stage's calls. The cache share was 71% on one model; this raises it.")

    @staticmethod
    def enabled() -> bool:
        return is_on("STABLE_STAGE_PREFIX", _StableStagePrefix.ON_BY_DEFAULT)


stable_stage_prefix_switch = _StableStagePrefix()


def enabled() -> bool:
    return stable_stage_prefix_switch.enabled()


def held_instructions(current: str, fallback: dict[str, Any]) -> tuple[str, str]:
    """(the instructions for the system prompt, the text to add at the end of the call).

    The first non-empty `current` of a stage visit is held, in the stage's memory (`fallback` outside a graph run). A
    later `current` that continues it adds only its continuation; one that differs adds itself whole; one that is
    empty or the same adds nothing. Off, `current` and nothing.
    """
    if not enabled():
        return current, ""
    from app.agents.stage_memory import store

    held = store("stable_prefix", fallback)
    first = held.get("instructions")
    if first is None:
        if current:
            held["instructions"] = current
        return current, ""
    if not current or current == first:
        return first, ""
    added = current[len(first):] if current.startswith(first) else current
    return first, f"{ADDED_NOTE}\n{added.strip()}"


def document_limit(files: dict[str, str]) -> int | None:
    """The longest a document is held whole in this project's memory, or None for the usual limit."""
    if not enabled():
        return None
    product = [path for path in files if not path.startswith(("docs/", "."))]
    return SMALL_DOCUMENT_CHARACTERS if 0 < len(product) < SMALL_PRODUCT_FILES else None


__all__ = ["ADDED_NOTE", "ON_BY_DEFAULT", "SMALL_DOCUMENT_CHARACTERS", "SMALL_PRODUCT_FILES", "document_limit", "enabled",
           "held_instructions"]
