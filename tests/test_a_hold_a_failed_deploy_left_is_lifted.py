"""A model-call hold a deploy left behind is lifted, by the deploy's own exit and by the next worker to start.

Found in review: `loop.sh deploy` sets the hold, waits for the calls in
flight, restarts and lifts it - under `set -e` and with no `trap`. A failed
`compose up`, or a deploy interrupted while it waited, exited with the hold
still set, and every model call of every run then waited the gate's whole
20 minutes (`call_gate.MOST_SECONDS_HELD`) before going ahead, call after
call, for a deploy that was gone.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from app.models import call_gate

LOOP = Path(__file__).resolve().parents[1] / "scripts" / "loop" / "loop.sh"


def _the_deploy() -> str:
    script = LOOP.read_text()
    return script[script.index("\ndeploy)"):script.index("\nfreshness)")]


def test_the_deploy_lifts_its_hold_however_it_exits():
    deploy = _the_deploy()

    trap = deploy.index("trap ")
    assert trap < deploy.index("touch $gate/hold"), "the trap is set before the hold it lifts"
    line = deploy[trap:deploy.index("\n", trap)]
    assert "rm -f $gate/hold" in line and line.rstrip().endswith("EXIT")


def test_a_hold_set_before_the_worker_started_is_lifted(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_CALL_GATE_DIR", str(tmp_path))
    hold = tmp_path / "hold"
    hold.write_text("")
    os.utime(hold, (time.time() - 3600, time.time() - 3600))

    assert call_gate.lift_a_hold_from_before(time.time() - 5) is True
    assert not call_gate.held()


def test_a_hold_a_deploy_set_after_the_worker_started_stays(tmp_path, monkeypatch):
    """A deploy in progress holds calls on a worker that is already up; that hold is the deploy's to lift."""
    monkeypatch.setenv("MODEL_CALL_GATE_DIR", str(tmp_path))
    (tmp_path / "hold").write_text("")

    assert call_gate.lift_a_hold_from_before(time.time() - 60) is False
    assert call_gate.held()


def test_no_hold_is_nothing_to_lift(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_CALL_GATE_DIR", str(tmp_path))

    assert call_gate.lift_a_hold_from_before(time.time()) is False


def test_a_starting_worker_lifts_the_hold_it_finds(tmp_path, monkeypatch):
    from celery.signals import worker_ready

    from app.server import tasks

    monkeypatch.setenv("MODEL_CALL_GATE_DIR", str(tmp_path))
    hold = tmp_path / "hold"
    hold.write_text("")
    os.utime(hold, (time.time() - 3600, time.time() - 3600))
    monkeypatch.setattr(tasks, "_WORKER_STARTED", time.time())

    tasks._lift_a_hold_a_previous_deploy_left()

    assert not hold.exists()
    import weakref

    connected = [
        receiver() if isinstance(receiver, weakref.ReferenceType) else receiver
        for _key, receiver in worker_ready.receivers
    ]
    assert tasks._lift_a_hold_a_previous_deploy_left in connected, "connected to the worker's start"
