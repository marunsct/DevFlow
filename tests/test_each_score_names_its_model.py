"""Each score names the model the run ran on (owner, 2026-11-04: store the model a run ran on).

A hidden score with no model beside it could not be compared across models. The run's record keeps the model's
non-secret settings; the score takes the name, the endpoint and the provider from there.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCORE = Path(__file__).resolve().parents[1] / "scripts" / "bench" / "score.py"


def _score_module():
    spec = importlib.util.spec_from_file_location("bench_score", SCORE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_model_name_endpoint_and_provider_come_from_the_run_s_record():
    last = json.dumps({"LLM_PROVIDER": "local", "OPENAI_BASE_URL": "http://host.docker.internal:8888/v1",
                       "OPENAI_MODEL": "unsloth/Qwen3.6-35B-A3B-MTP-GGUF", "MODEL_CONTEXT_WINDOW": "180000"})
    assert _score_module().the_model(last) == {
        "model": "unsloth/Qwen3.6-35B-A3B-MTP-GGUF", "endpoint": "host.docker.internal:8888", "provider": "local",
    }


def test_no_record_or_no_model_names_nothing():
    module = _score_module()
    assert module.the_model("") == {}
    assert module.the_model("not json") == {}
    assert module.the_model(json.dumps({"OPENAI_BASE_URL": "http://h:1/v1"})) == {}
