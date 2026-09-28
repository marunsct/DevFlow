"""A blank environment variable means "not configured", not "configured as empty".

`values.get(key, default)` applies the default only when the key is missing, and
docker-compose's `${VAR:-}` pattern sets every unconfigured variable to "". So in
the deployment these defaults were written for, they never applied.

Found on 2026-09-28 after the stack was rebuilt. Inside the worker
`OPENAI_API_KEY` and `OPENAI_MODEL` were present and empty; the local provider's
placeholder key never replaced the blank, and the OpenAI client refused to
construct - "Missing credentials" - so no run could make its first model call,
and every test that builds an agent failed the same way (37 of them).
"""

from __future__ import annotations

import pytest

from app.config import load_settings

LOCAL = {"OPENAI_BASE_URL": "http://host.docker.internal:8888/v1"}


class TestTheLocalProvider:
    def test_a_blank_key_gets_the_placeholder(self) -> None:
        """The regression: the client cannot be built with ""."""
        settings = load_settings({**LOCAL, "LLM_PROVIDER": "local", "OPENAI_API_KEY": ""})

        assert settings.openai_api_key == "lm-studio"

    def test_a_whitespace_key_is_blank_too(self) -> None:
        settings = load_settings({**LOCAL, "OPENAI_API_KEY": "   "})

        assert settings.openai_api_key == "lm-studio"

    def test_an_absent_key_is_unchanged(self) -> None:
        assert load_settings(LOCAL).openai_api_key == "lm-studio"

    def test_a_real_key_is_kept_as_given(self) -> None:
        settings = load_settings({**LOCAL, "OPENAI_API_KEY": "sk-real"})

        assert settings.openai_api_key == "sk-real"

    def test_the_client_can_be_built(self) -> None:
        """What the worker could not do: construct the model it runs on."""
        from app.models import build_default_chat_model

        settings = load_settings({**LOCAL, "LLM_PROVIDER": "local", "OPENAI_API_KEY": "", "OPENAI_MODEL": ""})

        assert build_default_chat_model(settings) is not None


class TestTheCloudProvidersKeepABlankKeyBlank:
    """A placeholder there would be worse than the blank."""

    @pytest.mark.parametrize("provider", ["anthropic", "gemini", "openai"])
    def test_blank_stays_blank(self, provider: str) -> None:
        """Under anthropic and gemini a non-empty key switches on a fallback to
        real OpenAI, which would then authenticate with a fake key; under openai
        it would turn a clear start-up error into a 401 on the first call."""
        settings = load_settings({"LLM_PROVIDER": provider, "OPENAI_API_KEY": ""})

        assert settings.openai_api_key == ""


class TestEveryDefaultedSetting:
    @pytest.mark.parametrize(
        ("key", "field", "expected"),
        [
            ("LLM_PROVIDER", "llm_provider", "local"),
            ("OPENAI_BASE_URL", "openai_base_url", "http://localhost:1234/v1"),
            ("EXECUTION_MODE", "execution_mode", "linear"),
            ("MODEL_THINKING_MODE", "thinking_mode", "default"),
            ("MODEL_THINKING_EFFORT", "thinking_effort", "medium"),
            ("LANGSMITH_PROJECT", "langsmith_project", "product-development-workflow"),
            ("WORKFLOW_ARTIFACT_DIRECTORY", "artifact_directory", "docs/generated"),
            ("OPENAI_MODEL", "model_name", "default-model"),
        ],
    )
    def test_blank_reads_as_the_default(self, key: str, field: str, expected: str) -> None:
        assert getattr(load_settings({key: ""}), field) == expected

    def test_a_set_value_still_wins(self) -> None:
        settings = load_settings({"EXECUTION_MODE": " Parallel ", "LLM_PROVIDER": "Anthropic"})

        assert settings.execution_mode == "parallel"
        assert settings.llm_provider == "anthropic"
