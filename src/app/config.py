"""Typed configuration for local and hosted model providers.

Keeping configuration in one module gives the rest of the workflow a stable,
typed interface. It also gives us one place to validate required settings and
avoid accidentally printing secrets while debugging.
"""

import os  # Reads environment variables supplied by the operating system.
from dataclasses import dataclass  # Creates a small class that stores settings.
from typing import Mapping  # Describes dictionary-like input without requiring a concrete dict.

from dotenv import load_dotenv  # Reads local .env files during local development.


DEFAULT_CHECKPOINTER = "postgres"
"""Postgres is already a required service, and it is the only backend that
works across the API and worker containers. The two modules that read this
setting previously disagreed on the default (memory vs sqlite), so behaviour
depended on which one happened to read it first."""


class ConfigurationError(ValueError):
    """Explain configuration mistakes separately from network or model failures."""


@dataclass(frozen=True)
class Settings:
    """Store validated settings so later workflow code does not parse strings repeatedly."""

    llm_provider: str  # The provider to use: 'local', 'openai', 'anthropic', 'gemini'
    openai_base_url: str  # URL where the model provider accepts OpenAI-compatible requests.
    openai_api_key: str  # Credential or local placeholder used by the model client.
    anthropic_api_key: str | None  # Credential for Anthropic API.
    google_api_key: str | None  # Credential for Google Gemini API.
    model_name: str  # Exact model identifier accepted by the configured provider.
    langsmith_tracing: bool  # Whether LangChain/LangGraph calls should be traced.
    langsmith_endpoint: str  # LangSmith server URL receiving traces.
    langsmith_api_key: str | None  # Optional secret; None means no key was configured.
    langsmith_project: str  # Logical LangSmith project used to group workflow traces.
    artifact_directory: str  # Directory where later workflow stages will write artifacts.
    require_approval: bool  # Safety switch for human approval before sensitive actions.
    allow_command_execution: bool  # Safety switch for tools that may run shell commands.
    checkpointer_type: str  # Type of checkpointer to use: 'memory' or 'sqlite'
    thinking_mode: str  # "default" (leave the server alone), "on", or "off".
    thinking_effort: str  # How much of the reply budget thinking may use: low, medium, high.
    execution_mode: str  # "linear" or "parallel"


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
        # override=False: values injected by the orchestrator must win over a
        # stale .env that happens to be in the image. The previous override=True
        # let a leftover file silently replace deployed configuration.
        load_dotenv(override=False)
        values = os.environ
    else:
        values = environment
    # The model name defaults to a placeholder if not set, to allow the UI settings page to load.
    model_name = _read_str(values, "OPENAI_MODEL", "")
    if not model_name or model_name.startswith("replace-with-"):
        model_name = "default-model"

    llm_provider = _read_str(values, "LLM_PROVIDER", "local").lower()

    # Construct Settings only after validation, so callers receive a trusted configuration object.
    return Settings(
        llm_provider=llm_provider,
        openai_base_url=_read_str(values, "OPENAI_BASE_URL", "http://localhost:1234/v1"),
        openai_api_key=_openai_api_key(values, llm_provider),
        anthropic_api_key=values.get("ANTHROPIC_API_KEY") or None,
        # GEMINI_API_KEY is accepted as an alias: docker-compose and
        # .env.example both set that name, so reading only GOOGLE_API_KEY
        # meant the Gemini provider never received a key at all.
        google_api_key=values.get("GOOGLE_API_KEY") or values.get("GEMINI_API_KEY") or None,
        model_name=model_name,
        langsmith_tracing=_read_bool(values, "LANGSMITH_TRACING", False),
        langsmith_endpoint=_read_str(values, "LANGSMITH_ENDPOINT", "https://api.smith.langchain.com"),
        langsmith_api_key=values.get("LANGSMITH_API_KEY") or None,
        langsmith_project=_read_str(values, "LANGSMITH_PROJECT", "product-development-workflow"),
        artifact_directory=_read_str(values, "WORKFLOW_ARTIFACT_DIRECTORY", "docs/generated"),
        require_approval=_read_bool(values, "WORKFLOW_REQUIRE_APPROVAL", True),
        allow_command_execution=_read_bool(values, "WORKFLOW_ALLOW_COMMAND_EXECUTION", False),
        checkpointer_type=_read_str(values, "CHECKPOINTER_TYPE", DEFAULT_CHECKPOINTER).lower(),
        # "default" sends nothing, so adding this setting cannot change how an
        # existing deployment behaves - see `app.agents.thinking.ThinkingMode`.
        thinking_mode=_read_str(values, "MODEL_THINKING_MODE", "default").lower(),
        thinking_effort=_read_str(values, "MODEL_THINKING_EFFORT", "medium").lower(),
        execution_mode=_read_str(values, "EXECUTION_MODE", "linear").lower(),
    )


def _read_str(values: Mapping[str, str], key: str, default: str) -> str:
    """`key`'s value stripped, or `default` when it is absent OR blank.

    `values.get(key, default)` applies the default only when the key is
    missing, and docker-compose's `${VAR:-}` pattern - used throughout this
    repository's compose file - sets every such variable to "" when it is not
    configured. So the defaults below never applied in the deployment they were
    written for: a blank `LLM_PROVIDER` became provider "", a blank
    `EXECUTION_MODE` became mode "", and a blank `OPENAI_API_KEY` reached the
    OpenAI client as "", which refuses to construct. That is how a rebuilt stack
    on 2026-09-28 could not build a model client at all.
    """
    raw = values.get(key)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip()


def _openai_api_key(values: Mapping[str, str], llm_provider: str) -> str:
    """The key for the OpenAI-compatible client.

    An absent key has always meant the local placeholder, and still does. A
    blank one now means the same - but only for the `local` provider, whose
    OpenAI-compatible server ignores the key while the client refuses to be
    built without one.

    Not for the others. Under `anthropic` and `gemini` a non-empty key switches
    on a fallback to real OpenAI (`gpt-4o-mini`), so turning a blank into the
    placeholder there would add a fallback that authenticates with a fake key,
    and under `openai` it would replace a clear "missing credentials" at start-up
    with a 401 on the first call. For those, blank stays blank.
    """
    raw = values.get("OPENAI_API_KEY")
    if raw is None:
        return "lm-studio"
    if not raw.strip():
        return "lm-studio" if llm_provider == "local" else ""
    return raw