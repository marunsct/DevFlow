"""Typed configuration for local and hosted model providers.

Keeping configuration in one module gives the rest of the workflow a stable,
typed interface. It also gives us one place to validate required settings and
avoid accidentally printing secrets while debugging.
"""

import os  # Reads environment variables supplied by the operating system.
from dataclasses import dataclass  # Creates a small class that stores settings.
from typing import Mapping  # Describes dictionary-like input without requiring a concrete dict.

from dotenv import load_dotenv  # Reads local .env files during local development.


class ConfigurationError(ValueError):
    """Explain configuration mistakes separately from network or model failures."""


@dataclass(frozen=True)
class Settings:
    """Store validated settings so later workflow code does not parse strings repeatedly."""

    openai_base_url: str  # URL where the model provider accepts OpenAI-compatible requests.
    openai_api_key: str  # Credential or local placeholder used by the model client.
    model_name: str  # Exact model identifier accepted by the configured provider.
    langsmith_tracing: bool  # Whether LangChain/LangGraph calls should be traced.
    langsmith_endpoint: str  # LangSmith server URL receiving traces.
    langsmith_api_key: str | None  # Optional secret; None means no key was configured.
    langsmith_project: str  # Logical LangSmith project used to group workflow traces.
    artifact_directory: str  # Directory where later workflow stages will write artifacts.
    require_approval: bool  # Safety switch for human approval before sensitive actions.
    allow_command_execution: bool  # Safety switch for tools that may run shell commands.


def _read_bool(environment: Mapping[str, str], name: str, default: bool) -> bool:
    """Convert text such as ``true`` into a real Python ``bool`` value."""
    # Environment variables are always text, so we normalize the text before testing it.
    raw_value = environment.get(name)
    if raw_value is None:
        return default

    normalized_value = raw_value.strip().lower()
    if normalized_value in {"1", "true", "yes", "on"}:
        return True
    if normalized_value in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(
        f"{name} must be one of true/false, yes/no, on/off, or 1/0."
    )


def load_settings(environment: Mapping[str, str] | None = None) -> Settings:
    """Load and validate settings without exposing secret values.

    The optional mapping makes this function easy to test without changing the
    real process environment. Production code can omit it and use ``os.environ``.
    LM Studio supplies an OpenAI-compatible endpoint, so its local placeholder
    key is safe as a development default but must not be treated as a production
    credential.
    """
    if environment is None:
        # Loading the local file here lets the command-line app use the same
        # configuration developers see in `.env`, while keeping secrets out of
        # source code and preserving injectable settings for tests.
        load_dotenv()
        values = os.environ
    else:
        values = environment
    # The model name is required because the provider cannot know which model to load for us.
    model_name = values.get("OPENAI_MODEL", "").strip()
    if not model_name or model_name.startswith("replace-with-"):
        raise ConfigurationError(
            "OPENAI_MODEL is required and must identify a loaded local or hosted model."
        )

    # Construct Settings only after validation, so callers receive a trusted configuration object.
    return Settings(
        openai_base_url=values.get("OPENAI_BASE_URL", "http://localhost:1234/v1").strip(),
        openai_api_key=values.get("OPENAI_API_KEY", "lm-studio"),
        model_name=model_name,
        langsmith_tracing=_read_bool(values, "LANGSMITH_TRACING", False),
        langsmith_endpoint=values.get(
            "LANGSMITH_ENDPOINT", "https://api.smith.langchain.com"
        ).strip(),
        langsmith_api_key=values.get("LANGSMITH_API_KEY") or None,
        langsmith_project=values.get("LANGSMITH_PROJECT", "product-development-workflow").strip(),
        artifact_directory=values.get("WORKFLOW_ARTIFACT_DIRECTORY", "docs/generated").strip(),
        require_approval=_read_bool(values, "WORKFLOW_REQUIRE_APPROVAL", True),
        allow_command_execution=_read_bool(values, "WORKFLOW_ALLOW_COMMAND_EXECUTION", False),
    )