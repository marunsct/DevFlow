"""How much a stage reads the documentation and the registries, and what it found.

Measured on one run's specification stage: 59 documentation reads and 30
registry lookups across four attempts, each attempt starting again from
nothing; each read is about a second, and each turn deciding on the next one
was 2-5 minutes of a frontier model reasoning. Two things follow:

- a stage visit has a share of each - `MOST_DOCUMENTATION_READS` and
  `MOST_PACKAGE_LOOKUPS` - and past it is told to write from what it has;
- what was found is remembered for the stage (`app.agents.stage_memory`), so
  an attempt started again on a fresh conversation is handed it
  (`app.agents.carry_over`) instead of looking it all up again.
"""

from __future__ import annotations

from typing import Any

#: Documentation reads one stage visit may make.
MOST_DOCUMENTATION_READS = 8

#: Packages one stage visit may look up in the registries.
MOST_PACKAGE_LOOKUPS = 12

#: Characters of one documentation answer handed to a fresh attempt.
MOST_CARRIED_CHARACTERS = 400

_PURPOSE = "research"

_SHARES = {"documentation": MOST_DOCUMENTATION_READS, "packages": MOST_PACKAGE_LOOKUPS}


def _ledger() -> dict[str, Any]:
    from app.agents.stage_memory import store

    return store(_PURPOSE, {})


def over_its_share(kind: str, count: int = 1) -> str | None:
    """Counts `count` more of `kind` for the running stage; a refusal when that is past its share."""
    ledger = _ledger()
    used = ledger.get(kind, 0)
    share = _SHARES[kind]
    if used + count > share:
        return (f"This stage has had its share of {kind} lookups ({share}). Write your answer from "
                "what you have found; where something is still uncertain, say so in the answer.")
    ledger[kind] = used + count
    return None


#: The tool that spends each share, by the share it spends.
_TOOL_OF = {"documentation": "read_docs", "packages": "look_up_package"}


def spent(kind: str) -> bool:
    """Whether the running stage has used its whole share of `kind`."""
    return _ledger().get(kind, 0) >= _SHARES[kind]


def build_research_share_middleware() -> Any:
    """Middleware that stops offering a lookup tool once the stage has used its share of it.

    Told it had had its share, one run's specification stage asked again eight
    times - each a frontier turn of 2 to 5 minutes for a refusal. A tool that
    is not offered is not asked for.
    """
    from langchain.agents.middleware import AgentMiddleware

    class ResearchShareMiddleware(AgentMiddleware):
        name = "ResearchShareMiddleware"

        def wrap_model_call(self, request: Any, handler: Any) -> Any:
            try:
                gone = {tool for kind, tool in _TOOL_OF.items() if spent(kind)}
                tools = list(getattr(request, "tools", None) or [])
                if gone and tools:
                    kept = [t for t in tools if _named(t) not in gone]
                    if len(kept) != len(tools):
                        request = request.override(tools=kept)
            except Exception:  # noqa: BLE001 - the refusal still answers an extra lookup
                pass
            return handler(request)

    return ResearchShareMiddleware()


def _named(tool: Any) -> str:
    if isinstance(tool, dict):
        return str(tool.get("name") or (tool.get("function") or {}).get("name") or "")
    return str(getattr(tool, "name", "") or "")


def found(label: str, answer: Any) -> None:
    """Remembers what one lookup answered, for an attempt that starts again."""
    if isinstance(answer, dict) and "error" in answer:
        return
    if isinstance(answer, dict) and "excerpt" in answer:
        text = str(answer.get("excerpt") or "")[:MOST_CARRIED_CHARACTERS]
    elif isinstance(answer, dict):
        text = ", ".join(f"{key}: {value}" for key, value in answer.items() if key not in ("description",))
    else:
        text = str(answer)
    _ledger().setdefault("found", {})[label] = text[:MOST_CARRIED_CHARACTERS]


def what_was_found(thread_id: str) -> dict[str, str]:
    """What a stage's lookups answered, by lookup."""
    from app.agents.stage_memory import recall

    return dict(recall(thread_id, _PURPOSE).get("found") or {})
