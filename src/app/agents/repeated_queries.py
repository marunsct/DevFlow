"""Say when a listing or a search comes back exactly as it did before.

`read_file` has had this since finding 59, and after finding 80 keyed it on the
bytes returned it catches almost everything: on run-fa7b7286 only 1 of 50 reads
returned content the stage had already been given. The tools beside it never
had it, and the same waste simply moved there - 4 of 10 `ls` calls and 4 of 12
`grep` calls in that run returned byte-identical results, with
`ls {'path': 'task-manager'}` run five times in one stage.

Those results have nowhere to put a note: `LsResult` carries `entries` and an
`error` and nothing else, and writing into `error` would report a working call
as a failure. The tool boundary does have somewhere - a `ToolMessage` is text -
so the notice lives here rather than in the backend.

Why no write-invalidation, unlike every other repeat notice in this codebase:
these results are self-describing. A listing carries each entry's size and
modification time, and a search carries the matching lines, so anything that
changed what the call reports also changes the bytes it returns. A
byte-identical result therefore *is* the evidence that nothing the agent asked
about has moved, and no separate tracking of writes can tell it better.
"""

from __future__ import annotations

import hashlib
from typing import Any

#: One repeat is ordinary; the second is the one worth mentioning. Matches
#: `app.agents.workspace_backend.REPEATS_BEFORE_SAYING_SO`, deliberately: the
#: two notices should not disagree about what counts as circling.
REPEATS_BEFORE_SAYING_SO = 2

#: Read-only queries with no note of their own. `read_file` is excluded because
#: the backend already gives it a better one, keyed on the file's identity as
#: well as the bytes, and two notices on one result would just be noise.
QUERY_TOOLS = frozenset({"ls", "grep", "glob"})


def build_repeated_query_middleware() -> Any:
    """Middleware that tells a stage when a query answered exactly as before."""
    from langchain.agents.middleware import AgentMiddleware

    class RepeatedQueryMiddleware(AgentMiddleware):
        """State lives on the instance, which is built per stage."""

        def __init__(self) -> None:
            super().__init__()
            self._seen: dict[tuple[str, str], dict[str, int]] = {}

        def wrap_tool_call(self, request: Any, handler: Any) -> Any:
            result = handler(request)
            try:
                note = self._note_for(request, result)
            except Exception:  # noqa: BLE001 - never fail a tool over a hint
                return result
            if not note:
                return result
            try:
                return result.model_copy(update={"content": result.content + note})
            except Exception:  # noqa: BLE001 - a Command, or some other shape
                return result

        def _note_for(self, request: Any, result: Any) -> str:
            call = getattr(request, "tool_call", None) or {}
            name = call.get("name", "")
            if name not in QUERY_TOOLS:
                return ""
            content = getattr(result, "content", None)
            if not isinstance(content, str) or not content:
                return ""

            key = (name, repr(sorted((call.get("args") or {}).items())))
            digest = hashlib.sha1(content.encode("utf-8", "replace")).hexdigest()
            counts = self._seen.setdefault(key, {})
            count = counts.get(digest, 0)
            counts[digest] = count + 1
            if count < REPEATS_BEFORE_SAYING_SO:
                return ""
            return (
                f"\n\n[This `{name}` returned exactly what it returned the {count} "
                "previous times you ran it in this stage. A listing reports each "
                "entry's size and modification time and a search reports the lines "
                "it matched, so an identical result means nothing you asked about "
                "has changed. Running it again will return this again.]"
            )

    return RepeatedQueryMiddleware()


__all__ = ["QUERY_TOOLS", "REPEATS_BEFORE_SAYING_SO", "build_repeated_query_middleware"]
