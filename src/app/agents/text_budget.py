"""Character budgets for text interpolated into an agent's first message.

`SummarizationMiddleware` compacts a conversation *between* model calls, keeping
the most recent `CTX_KEEP_MESSAGES`. It cannot help a request that is already
too large on its first call: with one user message there is nothing older to
summarise, so the call overflows and the middleware never runs.

That is not hypothetical. The technical specification is the largest artifact
this pipeline produces, and two builders interpolated all of it into a single
first message - `build_architecture_review_request` and
`build_sprint_planning_request`. The Principal Architect already solved the same
problem for its uploaded documents (`INITIAL_DOCUMENT_BUDGET`); this module is
that idea, reusable.

Trimming is made visible to the model rather than silent, so it can ask for the
part it is missing instead of reasoning from a specification it does not know is
incomplete.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

DEFAULT_SPECIFICATION_BUDGET = 150_000
"""Characters of the technical specification to carry into one request.

About 40-50k tokens at 3-4 characters a token - not the 15k this once said.
On a ~126k-token local window that leaves room for the system prompt, the
tool schemas, project memory's share and a structured response; a smaller
window should set `CTX_SPECIFICATION_BUDGET`. `0` sends the whole
specification. Section-aware selection (plan item O.1) is what would shrink
it without cutting the specification's tail.
"""


def _budget(name: str, default: int) -> int:
    """Read a character budget from the environment without ever raising.

    A malformed value logs a warning and yields the default - the same
    never-raise convention as `ContextPolicy.from_environment` and
    `principal_architect._initial_document_budget`. A budget is an operational
    guard rail; a typo in one must not stop every agent from starting.
    """
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("Malformed %s=%r; using %d", name, raw, default)
        return default
    return max(value, 0)


def specification_budget() -> int:
    """Characters of the specification to carry into one request.

    Derived from the configured context window, so retuning for a different
    model carries this with it. `CTX_SPECIFICATION_BUDGET` still overrides, and
    0 still means "send the whole specification".
    """
    from app.agents.context_budget import ContextBudget

    return _budget("CTX_SPECIFICATION_BUDGET", ContextBudget.resolve().specification_budget_chars)


def excerpt(text: str, budget: int, *, what: str) -> str:
    """`text`, trimmed to `budget` characters with the trim made visible.

    A budget of 0, or text already inside it, returns the text unchanged.
    """
    if budget <= 0 or len(text) <= budget:
        return text
    return (
        text[:budget]
        + f"\n\n[Excerpt: {len(text):,} characters of {what} were trimmed to "
        f"{budget:,} for this request. Use your repository read tools to open the "
        "full document if you need a section that is not shown above.]"
    )


__all__ = [
    "DEFAULT_SPECIFICATION_BUDGET",
    "excerpt",
    "specification_budget",
]
