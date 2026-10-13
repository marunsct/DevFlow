"""The judgement model's longest reply follows its own settings, not the default model's.

Measured on one run: the frontier model served a 1M-token window and 300k-token
replies, and its window was set in the settings, but every reply it was asked
for was capped at the default model's 20,000 tokens - the reply ceiling was
read from the process environment, which describes the default model. A stage
writing a specification to the smallest detail spent a whole reply on
reasoning. The ceiling is now read from the environment the model is built
from, and the judgement model has a reply ceiling of its own.
"""

from __future__ import annotations

import pytest

from app.models.roles import build_judgement_model, judgement_environment

BASE = {
    "LLM_PROVIDER": "local",
    "OPENAI_BASE_URL": "http://localhost:8888/v1",
    "OPENAI_MODEL": "build-model",
    "OPENAI_API_KEY": "local-placeholder",
    "MODEL_CONTEXT_WINDOW": "130000",
    "MODEL_MAX_OUTPUT_TOKENS": "20000",
    "JUDGEMENT_MODEL": "frontier-model",
    "JUDGEMENT_BASE_URL": "https://frontier.example/v1",
}


@pytest.fixture(autouse=True)
def the_process_describes_the_default_model(monkeypatch):
    for key, value in BASE.items():
        if key.startswith("MODEL_") or key.startswith("OPENAI_") or key == "LLM_PROVIDER":
            monkeypatch.setenv(key, value)


def _ceiling(model) -> int:
    return getattr(model, "max_tokens", None) or getattr(model, "max_output_tokens", None)


def test_its_own_reply_ceiling_is_the_one_it_is_built_with():
    environment = {**BASE, "JUDGEMENT_CONTEXT_WINDOW": "1000000", "JUDGEMENT_MAX_OUTPUT_TOKENS": "300000"}

    assert judgement_environment(environment)["MODEL_MAX_OUTPUT_TOKENS"] == "300000"
    assert _ceiling(build_judgement_model("default", environment)) == 300_000


def test_without_one_its_ceiling_is_derived_from_its_own_window():
    environment = {**BASE, "JUDGEMENT_CONTEXT_WINDOW": "1000000"}

    ceiling = _ceiling(build_judgement_model("default", environment))

    assert ceiling != 20_000, "the default model's pinned ceiling"
    assert ceiling >= 32_000


def test_the_default_model_keeps_its_own():
    from app.config import load_settings
    from app.models import build_default_chat_model

    assert _ceiling(build_default_chat_model(load_settings(BASE))) == 20_000
