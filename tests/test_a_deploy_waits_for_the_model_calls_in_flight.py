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
    assert "a_model_call(str(self.openai_api_base" in inspect.getsource(CompatibleChatOpenAI._generate)


def test_the_deploy_holds_waits_and_lifts():
    script = (Path(__file__).resolve().parents[1] / "scripts" / "loop" / "loop.sh").read_text()
    deploy = script[script.index("\ndeploy)"):script.index("\nfreshness)")]
    assert deploy.index("touch $gate/hold") < deploy.index("docker compose up -d app worker")
    assert "ls $gate/inflight" in deploy and "rm -f $gate/inflight/* $gate/hold" in deploy


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
