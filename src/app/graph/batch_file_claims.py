"""Fixers working side by side in one batch never write the same file (LR.15).

A batch fixes defects together when their files do not meet, as predicted before it starts. Measured on one run: two
fixers of one batch both rewrote the same database module - the prediction had not named it for either - and each
write then failed on the other's ("the file changed after you last read it", "it already exists, the other stage
wrote the version there now"), until both reached their call budgets. Now a fixer's first successful write claims the
file for it while it runs; another fixer's write to that file is refused before it runs, plainly, and its answer says
what the file needs. The claims end with the fixer. Only stages registered as a batch's fixers are concerned: a fix
made alone, and every other stage, writes as before.
"""
from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator

#: The write tools, and the argument each names its file by.
WRITES = {"write_artifact": "relative_path", "edit_artifact": "relative_path", "replace_lines": "relative_path",
          "delete_artifact": "relative_path", "move_artifact": "relative_path", "write_file": "file_path",
          "edit_file": "file_path"}
#: The refusal's opening, which the guards that count refusals recognise.
REFUSED = "Refusing: `{path}` is being changed by another fix running beside you ({owner})."

_lock = threading.Lock()
_active: dict[str, set[str]] = {}
_claims: dict[tuple[str, str], str] = {}
#: (run, fixer) -> {file: when it last wrote it}: kept after the fixer ends, so the batch's measurement can tell whose
#: change broke it (A3) and put back that fixer's files alone.
_written: dict[tuple[str, str], dict[str, float]] = {}


@contextmanager
def holding(run_id: str | None, stage: str) -> Iterator[None]:
    """While inside, `stage` is one of its run's batch fixers: its writes claim files; the claims end with it."""
    run = str(run_id or "")
    with _lock:
        _active.setdefault(run, set()).add(stage)
    try:
        yield
    finally:
        with _lock:
            _active.get(run, set()).discard(stage)
            for key in [key for key, owner in _claims.items() if key[0] == run and owner == stage]:
                del _claims[key]


def _path_of(tool: str, args: Any) -> str:
    field = WRITES.get(tool)
    if not field or not isinstance(args, dict):
        return ""
    return str(args.get(field) or "").strip().lstrip("./")


def owner_of(run_id: str | None, stage: str, tool: str, args: Any) -> str:
    """The other batch fixer that holds this write's file, or "" when the write may go ahead."""
    run, path = str(run_id or ""), _path_of(tool, args)
    if not path:
        return ""
    with _lock:
        if stage not in _active.get(run, set()):
            return ""
        owner = _claims.get((run, path), "")
        return owner if owner and owner != stage and owner in _active.get(run, set()) else ""


def claim(run_id: str | None, stage: str, tool: str, args: Any) -> None:
    """After a successful write, its file is the writer's while it runs."""
    run, path = str(run_id or ""), _path_of(tool, args)
    if not path:
        return
    with _lock:
        if stage in _active.get(run, set()):
            _claims.setdefault((run, path), stage)
            _written.setdefault((run, stage), {})[path] = time.monotonic()


def held_by_another(run_id: str | None, stage: str, path: str) -> str:
    """The other fixer of `stage`'s batch that holds `path` or has written it, or "" when `stage` may write it: the
    filter of a rewrite a batch fixer is given after it gave up (LF.1404), which writes no file through a tool."""
    run, name = str(run_id or ""), str(path or "").strip().lstrip("./")
    if not name:
        return ""
    with _lock:
        if stage not in _active.get(run, set()):
            return ""
        owner = _claims.get((run, name), "")
        if owner and owner != stage and owner in _active.get(run, set()):
            return owner
        return next((other for (each, other), files in _written.items()
                     if each == run and other != stage and name in files), "")


def written_by_a_rewrite(run_id: str | None, stage: str, paths: list[str]) -> None:
    """The files a batch fixer's rewrite wrote are its, as its own writes are: claimed while it runs, and told apart
    when its batch is measured."""
    for path in paths or []:
        claim(run_id, stage, "write_artifact", {"relative_path": str(path)})


def written_by(run_id: str | None, stage: str) -> list[str]:
    """The files batch fixer `stage` wrote, as its writes named them; [] when none was recorded."""
    with _lock:
        return sorted(_written.get((str(run_id or ""), stage), {}))


def last_write_at(run_id: str | None, stage: str) -> float:
    """When batch fixer `stage` last wrote, on this process's clock; 0.0 when it wrote nothing recorded."""
    with _lock:
        return max(_written.get((str(run_id or ""), stage), {}).values(), default=0.0)


def forget(run_id: str | None, stages: list[str]) -> None:
    """Drop what these fixers wrote, once their batch is settled."""
    with _lock:
        for stage in stages:
            _written.pop((str(run_id or ""), stage), None)


def build_middleware() -> Any:
    """The middleware that refuses a write to a file another batch fixer holds; a pass-through otherwise."""
    from langchain.agents.middleware import AgentMiddleware
    from langchain_core.messages import ToolMessage

    from app.observability.transcript import _run_id_from_config, _stage_from_config

    class BatchFileClaimsMiddleware(AgentMiddleware):
        name = "BatchFileClaimsMiddleware"

        def wrap_tool_call(self, request: Any, handler: Any) -> Any:
            if not _active:
                return handler(request)
            call = getattr(request, "tool_call", None) or {}
            tool, args = str(call.get("name") or ""), call.get("args") or {}
            run, stage = _run_id_from_config(), _stage_from_config("")
            owner = owner_of(run, stage, tool, args)
            if owner:
                return ToolMessage(
                    content=REFUSED.format(path=_path_of(tool, args), owner=owner)
                    + " Leave this file: say in your answer what change it needs for your defect, and fix what is "
                    "yours elsewhere. The harness measures the batch together when every fixer has answered.",
                    tool_call_id=str(call.get("id") or ""), name=tool, status="error")
            result = handler(request)
            if getattr(result, "status", None) != "error" and not str(getattr(result, "content", "")).lstrip().startswith(
                    ("Refusing", '{"error"', "Error")):
                claim(run, stage, tool, args)
            return result

    return BatchFileClaimsMiddleware()


__all__ = ["REFUSED", "WRITES", "build_middleware", "claim", "forget", "held_by_another", "holding", "last_write_at",
           "owner_of", "written_by", "written_by_a_rewrite"]
