"""The project memory and snapshot in the same bytes for every visit of a sprint (plan PX.3, behind `CANONICAL_MEMORY`).

The opening messages are where most of a request's tokens are, and they
changed between calls that should have shared them: the snapshot carried the
clock, the memory put the files a request names first, and a large document's
digest - chosen by the request's words - sat ahead of the code. Measured post
hoc on two gate runs (PX.1): a changed opening was the first break behind
18-25% of uncached input tokens. With the switch on, the snapshot says when
without a time, the memory's order no longer depends on the request (the
held-files line at the request's end already points at what to start with),
and digested documents follow the code, so siblings of one fan-out share
everything up to them.
"""

from __future__ import annotations

from app.switches import is_on

#: `CANONICAL_MEMORY` set to on or off overrides this.
ON_BY_DEFAULT = False


def enabled() -> bool:
    return is_on("CANONICAL_MEMORY", ON_BY_DEFAULT)


def when(clock: str) -> str:
    """The snapshot's "when": the time when off, a time-free phrase when on."""
    return "as this stage started" if enabled() else clock


__all__ = ["ON_BY_DEFAULT", "enabled", "when"]
