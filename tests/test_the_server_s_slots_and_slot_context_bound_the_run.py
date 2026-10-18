"""The build model's server bounds the context window and each fan-out (Initiatives M.1, O.2, AB).

Measured across runs: forty-odd calls refused with "Context size has been
exceeded" at 20,000-48,000 input tokens under a 100,000-token setting, in
parallel waves on a server that splits its context across its slots.
"""

from __future__ import annotations

import pytest

from app.models import server_profile
from app.models.server_profile import ServerProfile, from_props


@pytest.fixture(autouse=True)
def _clean():
    server_profile.forget()
    yield
    server_profile.forget()


def _recorded(profile: ServerProfile) -> None:
    server_profile._RECORDED = profile


def test_props_give_slots_slot_context_and_quantisation() -> None:
    profile = from_props({
        "total_slots": 4,
        "default_generation_settings": {"n_ctx": 32768},
        "model_path": "/models/Some-Model-30B-Q4_K_M.gguf",
    })
    assert (profile.slots, profile.slot_context, profile.quantisation, profile.bits) == (4, 32768, "Q4_K_M", 4)
    assert "4-bit" in profile.advisory()


def test_a_path_with_no_quantisation_names_none_and_warns_of_nothing() -> None:
    profile = from_props({"total_slots": 1, "default_generation_settings": {"n_ctx": 126464},
                          "model_path": "org/Model-35B-GGUF"})
    assert profile.quantisation == "" and profile.advisory() == ""
    assert from_props({"model_path": "x-Q8_0.gguf"}).advisory() == ""


def test_the_window_is_no_larger_than_a_slot_s_context() -> None:
    from app.agents.context_budget import context_window

    env = {"MODEL_CONTEXT_WINDOW": "100000"}
    assert context_window(env) == 100000
    _recorded(ServerProfile(slots=4, slot_context=32768))
    assert context_window(env) == 32768
    _recorded(ServerProfile(slots=1, slot_context=200000))
    assert context_window(env) == 100000


def test_a_fan_out_is_no_wider_than_the_server_s_slots(monkeypatch) -> None:
    from app.graph.workflow import concurrent_requests, max_parallel

    monkeypatch.setenv("HARNESS_MAX_PARALLEL", "6")
    assert concurrent_requests() == 6
    _recorded(ServerProfile(slots=2))
    assert concurrent_requests() == 2
    assert max_parallel() == 6  # whether to fan out at all is still the owner's setting


def test_the_fan_outs_use_the_capped_width() -> None:
    import inspect

    from app.graph import workflow

    source = inspect.getsource(workflow)
    assert source.count("concurrent_requests()") >= 5
    assert "pending[: max_parallel()]" not in source


def test_each_run_segment_reads_the_profile_and_ready_prints_it() -> None:
    import inspect
    from pathlib import Path

    from app.server import tasks

    assert "server_profile.record()" in inspect.getsource(tasks.execute_workflow_run)
    ready = (Path(__file__).resolve().parents[1] / "scripts" / "loop" / "model_ready.py").read_text()
    assert "from app.models.server_profile import read" in ready and "ADVISORY" in ready


def test_no_server_records_nothing(monkeypatch) -> None:
    assert server_profile.read("") is None
    assert server_profile.read("http://127.0.0.1:9/v1") is None
