"""A fixer's memory puts the documents that hold for every fix before the code that each fix changes (LR.52, behind `STABLE_MEMORY_ORDER`).

A server's prompt cache reuses a request's prefix up to the first byte that differs. A fixer's memory led with the
product's code (`project_memory.render(for_a_fixer=True)`), and the code is what every fix changes: the next fixer's
request - another attempt, the next defect, the next file of a whole-file rewrite - differed from the first file
on, and the acceptance criteria and the specification behind it, the same for every fixer of the sprint, were read
again each time. With the switch on, the same blocks come in a stable order: the documents held whole (the
acceptance criteria), then the specification's sections the defect points at, then the code; and a whole-file
rewrite's request puts its stable parts - the stack, the facts, the project memory, the file's specification -
before the defect, its failure and the file as it is now. What is held, and what fits the budget, does not change:
only the order does.

An efficiency change, so a switch (off in code like every switch), kept only if measured runs lose no hidden test
by it.
"""
from __future__ import annotations

from app.switches import is_on

#: Off in code like every switch; the compose file says whether it is on.
ON_BY_DEFAULT = False

#: The words its memory gives, which the audit's switch-firing check reads.
SAID = "The documents that hold for every fix come first, the code after them."


def enabled() -> bool:
    return is_on("STABLE_MEMORY_ORDER", ON_BY_DEFAULT)


__all__ = ["ON_BY_DEFAULT", "SAID", "enabled"]
