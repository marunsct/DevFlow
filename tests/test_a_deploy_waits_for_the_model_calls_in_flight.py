"""A deploy waits for the model calls in flight, and holds new ones until it restarts.

Owner, 2026-10-15: deploy between model calls. A restart in the middle of a
call threw away a reply the run had waited minutes for.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from app.models import CompatibleChatOpenAI, call_gate


def test_a_call_is_in_flight_while_it_runs_and_not_after(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_CALL_GATE_DIR", str(tmp_path))
    with call_gate.a_model_call():
        assert len(call_gate.in_flight()) == 1
    assert call_gate.in_flight() == []


def test_a_call_waits_while_a_deploy_holds_and_starts_when_it_lifts(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_CALL_GATE_DIR", str(tmp_path))
    (tmp_path / "hold").write_text("")
    waits = []

    def sleep(seconds):
        waits.append(seconds)
        if len(waits) == 3:
            (tmp_path / "hold").unlink()

    call_gate._wait_while_held(sleep=sleep)
    assert len(waits) == 3 and not call_gate.held()


def test_a_hold_left_behind_does_not_stop_calls_for_good(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_CALL_GATE_DIR", str(tmp_path))
    (tmp_path / "hold").write_text("")
    now = [0.0]

    def sleep(seconds):
        now[0] += seconds

    call_gate._wait_while_held(sleep=sleep, clock=lambda: now[0])
    assert now[0] >= call_gate.MOST_SECONDS_HELD


def test_every_call_of_the_model_class_goes_through_the_gate():
    # The server it marks is the one the request goes to (the run's model pin may send it elsewhere).
    assert "a_model_call(self._served_by()[0])" in inspect.getsource(CompatibleChatOpenAI._generate)


def test_the_deploy_holds_waits_and_lifts():
    script = (Path(__file__).resolve().parents[1] / "scripts" / "loop" / "loop.sh").read_text()
    deploy = script[script.index("\ndeploy)"):script.index("\nfreshness)")]
    assert deploy.index("touch $gate/hold") < deploy.index("docker compose up -d app worker")
    assert "find $gate/inflight -type f -mmin -40" in deploy and "rm -f $gate/inflight/* $gate/hold" in deploy


def test_a_long_call_on_a_server_another_run_uses_is_reported_to_the_run(tmp_path, monkeypatch):
    """Two runs on one local server each waited for the other, with nothing on either page to say why."""
    monkeypatch.setenv("MODEL_CALL_GATE_DIR", str(tmp_path))
    monkeypatch.setattr(call_gate, "_this_run", lambda: ("run-mine", "scrum_master"))
    told = []
    monkeypatch.setattr(call_gate, "_tell_the_run", lambda run, stage, text: told.append((run, text)))
    clock = iter([0.0, 400.0])
    monkeypatch.setattr(call_gate.time, "perf_counter", lambda: next(clock))
    key = call_gate._server_key("http://gpu:9090/v1")
    (tmp_path / "inflight").mkdir()
    (tmp_path / "inflight" / f"run-theirs__{key}__9-abc").write_text("")
    (tmp_path / "inflight" / f"run-other__{call_gate._server_key('https://cloud/v1')}__9-def").write_text("")

    with call_gate.a_model_call("http://gpu:9090/v1"):
        pass

    assert len(told) == 1 and told[0][0] == "run-mine"
    assert "took 400s" in told[0][1] and "1 other run(s) (run-theirs)" in told[0][1]


def test_a_call_a_dead_worker_left_is_forgotten_when_the_next_one_starts(tmp_path, monkeypatch):
    """Measured on 2026-10-20: the host lost power during a call, its marker survived on the
    data volume, and the next deploy waited its whole gate time for a call that no longer existed."""
    import os
    import time

    monkeypatch.setenv("MODEL_CALL_GATE_DIR", str(tmp_path))
    (tmp_path / "inflight").mkdir()
    left = tmp_path / "inflight" / "run-x__key__16-dead"
    left.write_text("1")
    os.utime(left, (time.time() - 7200, time.time() - 7200))
    started = time.time() - 5
    live = tmp_path / "inflight" / "run-x__key__17-live"
    live.write_text("2")

    assert call_gate.forget_calls_from_before(started) == 1
    assert call_gate.in_flight() == ["run-x__key__17-live"]


def test_the_deploy_counts_only_calls_younger_than_a_call_can_run():
    text = (Path(__file__).resolve().parents[1] / "scripts" / "loop" / "loop.sh").read_text()

    assert "find $gate/inflight -type f -mmin -40" in text


def test_the_deploy_counts_only_calls_whose_process_still_runs():
    """A paused run's task is stopped with SIGTERM mid-call and leaves its marker; the worker is not restarted."""
    text = (Path(__file__).resolve().parents[1] / "scripts" / "loop" / "loop.sh").read_text()
    deploy = text[text.index("\ndeploy)"):text.index("\nfreshness)")]

    assert "[ -d /proc/\\$p ]" in deploy



def test_a_call_no_run_claims_is_not_called_another_run(tmp_path, monkeypatch):
    """After a pause, the paused task's calls still in flight were reported as "1 other run(s) (none)"."""
    monkeypatch.setenv("MODEL_CALL_GATE_DIR", str(tmp_path))
    monkeypatch.setattr(call_gate, "_this_run", lambda: ("run-mine", "principal_architect"))
    told = []
    monkeypatch.setattr(call_gate, "_tell_the_run", lambda run, stage, text: told.append(text))
    clock = iter([0.0, 400.0])
    monkeypatch.setattr(call_gate.time, "perf_counter", lambda: next(clock))
    key = call_gate._server_key("http://gpu:9090/v1")
    (tmp_path / "inflight").mkdir()
    (tmp_path / "inflight" / f"none__{key}__9-abc").write_text("")

    with call_gate.a_model_call("http://gpu:9090/v1"):
        pass

    assert told and "other run" not in told[0] and "(none)" not in told[0] and "calls no run claims" in told[0]
