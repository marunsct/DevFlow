"""Model calls a deploy waits for, and a hold that keeps new ones from starting.

Owner, 2026-10-15: deploy between model calls - if a call is in progress,
deploy once it is done, then resume. A restart in the middle of a call threw
away a reply the run had already waited minutes for (one local call took
5 minutes) and the stage asked again from its last checkpoint.

Each call registers itself as a file under `<gate>/inflight/` for as long as
it runs. A deploy sets `<gate>/hold`, waits until `inflight/` is empty, and
restarts; a call that would start while the hold is set waits for it to be
lifted, so nothing new begins in the window. The gate lives in the data
volume the app and worker share (`MODEL_CALL_GATE_DIR`).
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)

#: How long a call waits for a hold to be lifted before going ahead anyway.
#: A deploy that died with the hold set must not stop every run for good.
MOST_SECONDS_HELD = 20 * 60
POLL_SECONDS = 2.0


def gate_directory() -> Path:
    return Path(os.environ.get("MODEL_CALL_GATE_DIR") or "/app/data/loop/gate")


def held() -> bool:
    try:
        return (gate_directory() / "hold").exists()
    except OSError:
        return False


def in_flight() -> list[str]:
    try:
        return sorted(path.name for path in (gate_directory() / "inflight").iterdir())
    except OSError:
        return []


def forget_calls_from_before(started: float) -> int:
    """Remove the markers of calls registered before `started`: their process is gone.

    A marker is removed when its call returns, so one left behind belongs to a
    process that died mid-call. Measured on 2026-10-20: the host lost power
    during a call, the marker survived on the data volume, and the next deploy
    waited its full gate time for a call that no longer existed. Called by a
    worker as it starts, with its own start time; returns how many were removed.
    """
    removed = 0
    try:
        for path in (gate_directory() / "inflight").iterdir():
            try:
                if path.stat().st_mtime < started:
                    path.unlink()
                    removed += 1
            except OSError:
                continue
    except OSError:
        return removed
    return removed


def _wait_while_held(sleep=time.sleep, clock=time.monotonic) -> None:
    if not held():
        return
    logger.info("A deploy is waiting for model calls to finish; this call starts after it")
    started = clock()
    while held() and clock() - started < MOST_SECONDS_HELD:
        sleep(POLL_SECONDS)


#: A call this long, on a server another run was using, is reported to the run.
SHARED_NOTICE_SECONDS = 60


def _this_run() -> tuple[str, str]:
    try:
        from app.observability.log_context import _TASK_RUN, _from_the_graph

        run, stage = _from_the_graph()
        return str(run or _TASK_RUN.get() or ""), str(stage or "")
    except Exception:  # noqa: BLE001 - a call outside a run
        return "", ""


def _server_key(server: str) -> str:
    import hashlib

    return hashlib.sha1(server.encode("utf-8")).hexdigest()[:10] if server else "any"


#: What `_runs_on` names a call no run claims.
UNCLAIMED = "<unclaimed>"


def _runs_on(server_key: str, besides: str) -> set[str]:
    """The other runs with a call in flight on this server now."""
    runs = set()
    for name in in_flight():
        run, _, rest = name.partition("__")
        if rest.startswith(f"{server_key}__") and run and run != besides:
            # A call made outside any run is marked `none` (`a_model_call`):
            # a paused run's calls still in flight, a probe. It is not another run.
            runs.add(UNCLAIMED if run == "none" else run)
    return runs


def _tell_the_run(run: str, stage: str, text: str) -> None:
    try:
        from app.server.agent_stream import AgentActivityStream

        AgentActivityStream(run, stage or "-").publish_outcome(text)
    except Exception:  # noqa: BLE001 - narration is never load-bearing
        pass


@contextmanager
def a_model_call(server: str = "") -> Iterator[None]:
    """Hold this call while a deploy is pending, then mark it in flight until it returns.

    A call that took long while another run was using the same model server
    says so on its run's page: two runs on one local server each waited for
    the other, and one call went from about 40 seconds to about 5 minutes with
    nothing on either page to say why.
    """
    _wait_while_held()
    run, stage = _this_run()
    if run:
        # The server's own facts, asked again now and then (Initiative S).
        try:
            from app.models import server_profile

            noticed = server_profile.check_again(run)
            if any(part.startswith("model ") for part in noticed.split(": ", 1)[-1].split(", ")):
                # Another model behind the same server: diagnosed before this
                # call, as a run's first segment would (`app.models.diagnostics`).
                from app.models import build_default_chat_model
                from app.models.diagnostics import diagnose_if_new
                from app.models.reply_salvage import measure_if_new

                served = build_default_chat_model()
                diagnose_if_new(served)
                measure_if_new(served)
                from app.models.diagnostics import apply, recorded
                from app.models.model_guidance import deep_if_new
                from app.models.reply_salvage import served_name

                deep_if_new(served)
                apply(served, recorded(served_name(served)))
        except Exception:  # noqa: BLE001 - telemetry never stops a call
            pass
    key = _server_key(server)
    marker = None
    try:
        directory = gate_directory() / "inflight"
        directory.mkdir(parents=True, exist_ok=True)
        marker = directory / f"{run or 'none'}__{key}__{os.getpid()}-{uuid.uuid4().hex[:12]}"
        marker.write_text(str(time.time()))
    except OSError:
        marker = None  # a gate that cannot be written never stops a call
    started = time.perf_counter()
    shared = _runs_on(key, run) if run else set()
    try:
        yield
    finally:
        if marker is not None:
            try:
                marker.unlink()
            except OSError:
                pass
        if run:
            shared |= _runs_on(key, run)
            took = time.perf_counter() - started
            if shared and took >= SHARED_NOTICE_SECONDS:
                others = sorted(r[:12] for r in shared if r != UNCLAIMED)
                parts = ([f"{len(others)} other run(s) ({', '.join(others)})"] if others else []) + (
                    ["calls no run claims (a paused run's calls still in flight, or a probe)"] if UNCLAIMED in shared else [])
                text = (
                    f"A model call took {took:.0f}s while the model server was also serving "
                    + " and ".join(parts) + "; calls that share one model server wait for each other."
                )
                logger.warning(text)
                _tell_the_run(run, stage, text)



def _stop_if_this_run_was_stopped() -> None:
    """Raise the run's stop when this process paused or cancelled the run whose stage is calling (`workflow.stopped_here`)."""
    import sys

    if "app.graph.workflow" not in sys.modules:
        return
    from app.graph.workflow import RunCancelled, stopped_here

    try:
        from langgraph.config import get_config

        from app.tracing import APP_RUN_ID_KEY

        run_id = (get_config() or {}).get("configurable", {}).get(APP_RUN_ID_KEY)
    except Exception:  # noqa: BLE001 - outside a run there is nothing to stop
        return
    if stopped_here(run_id):
        raise RunCancelled(f"Run {run_id} was stopped; this stage's call is not made.")
