"""The model server is asked about itself again during a run (Initiative S, mid-run health telemetry).

The server's profile was read once per run segment. The owner restarted the
server from one slot to two between runs on one day; a run in flight would have
kept budgeting for the old slot's context until a deploy re-read it, and a
server that stopped answering mid-run left no record of when.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from app.models import server_profile as sp


@pytest.fixture(autouse=True)
def _fresh():
    sp.forget()
    yield
    sp.forget()


def _start(profile):
    sp._TRIED = True
    sp._RECORDED = profile


def test_a_change_is_noticed_used_and_recorded(monkeypatch):
    written = []
    monkeypatch.setattr("app.observability.transcript.record", lambda run, stage, kind, **f: written.append((kind, f)))
    _start(sp.ServerProfile(slots=1, slot_context=126464))

    noticed = sp.check_again("run-x", clock=lambda: 1000.0, reader=lambda: sp.ServerProfile(slots=2, slot_context=63232))

    assert "slots 1 -> 2" in noticed and "tokens per slot 126464 -> 63232" in noticed
    assert sp.current().slots == 2
    assert written and written[0][0] == "server_changed"


def test_it_asks_at_most_every_few_minutes():
    _start(sp.ServerProfile(slots=1))
    asked = []

    def reader():
        asked.append(1)
        return sp.ServerProfile(slots=1)

    sp.check_again("run-x", clock=lambda: 1000.0, reader=reader)
    sp.check_again("run-x", clock=lambda: 1000.0 + sp.HEALTH_CHECK_SECONDS - 1, reader=reader)
    sp.check_again("run-x", clock=lambda: 1000.0 + sp.HEALTH_CHECK_SECONDS + 1, reader=reader)

    assert len(asked) == 2


def test_a_server_that_stops_answering_is_recorded_once_and_its_return_too(monkeypatch):
    written = []
    monkeypatch.setattr("app.observability.transcript.record", lambda run, stage, kind, **f: written.append(kind))
    _start(sp.ServerProfile(slots=1))

    for second, reply in ((1000.0, None), (2000.0, None), (3000.0, sp.ServerProfile(slots=1))):
        sp.check_again("run-x", clock=lambda s=second: s, reader=lambda r=reply: r)

    assert written == ["server_unreachable", "server_reachable"]


def test_a_server_never_asked_or_with_no_props_is_left_alone():
    assert sp.check_again("run-x", clock=lambda: 1e9, reader=lambda: sp.ServerProfile(slots=4)) == ""


def test_the_kpis_count_them():
    spec = importlib.util.spec_from_file_location("kpi_s", Path(__file__).resolve().parents[1] / "scripts" / "loop" / "kpi.py")
    kpi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kpi)
    got = kpi.kpis([{"at": "2026-10-19T00:00:00+00:00", "stage": "-", "kind": "server_changed"},
                    {"at": "2026-10-19T00:01:00+00:00", "stage": "-", "kind": "server_unreachable"}])
    assert got["server_changed"] == 1 and got["server_unreachable"] == 1


def test_every_model_call_goes_through_the_check():
    import inspect

    from app.models import call_gate

    assert "server_profile.check_again(run)" in inspect.getsource(call_gate.a_model_call)
