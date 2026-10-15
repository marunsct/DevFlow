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


def _runs_on(server_key: str, besides: str) -> set[str]:
    """The other runs with a call in flight on this server now."""
    runs = set()
    for name in in_flight():
        run, _, rest = name.partition("__")
        if rest.startswith(f"{server_key}__") and run and run != besides:
            runs.add(run)
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
                text = (
                    f"A model call took {took:.0f}s while the model server was also serving "
                    f"{len(shared)} other run(s) ({', '.join(sorted(r[:12] for r in shared))}); runs that share "
                    "one model server wait for each other."
                )
                logger.warning(text)
                _tell_the_run(run, stage, text)
