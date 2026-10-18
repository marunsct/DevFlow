"""A harness switch set in `.env` reaches the worker, and one limit has one default.

Compose reads `.env` only to fill the values `x-app-env` names; a variable it
does not name never reaches the container. The switches the plan's A/B
comparisons turn - line edits, the environment contract, the workspace
digest, project memory, the task list, when a fix escalates - were none of
them named, so every "A/B" was the same configuration twice.

And the sandbox's per-process memory limit had three defaults: 4g in the
code, 1g in compose (the measured one - several concurrent test workers must
fit in the container), 2g, twice, in `.env.example`, which a copied `.env`
would have applied over compose's.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TOGGLES = (
    "LINE_EDITS",
    "ENVIRONMENT_CONTRACT",
    "WORKSPACE_DIGEST",
    "PROJECT_MEMORY",
    "HARNESS_TASK_LIST",
    "ESCALATE_AFTER_ATTEMPTS",
)


def _app_env() -> dict[str, str]:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    return {str(k): str(v) for k, v in compose["x-app-env"].items()}


def test_every_switch_is_passed_to_the_worker() -> None:
    env = _app_env()
    assert [name for name in TOGGLES if name not in env] == []


def test_a_derived_model_budget_is_not_among_them() -> None:
    """The reply cap is derived from the model and set per model in Settings;
    compose deliberately names no value for it (see the note above
    MODEL_CONTEXT_WINDOW there)."""
    assert "MODEL_MAX_OUTPUT_TOKENS" not in _app_env()


def test_a_switch_left_unset_keeps_the_code_s_default() -> None:
    """An empty value reads as unset at every one of these sites."""
    env = _app_env()
    assert {name: env[name] for name in TOGGLES} == {name: f"${{{name}:-}}" for name in TOGGLES}


def test_the_memory_limit_has_one_default() -> None:
    from app.tools import sandbox

    compose = re.fullmatch(r"\$\{SANDBOX_MEMORY_LIMIT:-(\w+)\}", _app_env()["SANDBOX_MEMORY_LIMIT"]).group(1)
    example = re.findall(r"^#?\s*SANDBOX_MEMORY_LIMIT=(\w+)", (ROOT / ".env.example").read_text(), re.M)
    source = re.search(
        r'MEMORY_LIMIT = os\.environ\.get\("SANDBOX_MEMORY_LIMIT", "(\w+)"\)', Path(sandbox.__file__).read_text()
    ).group(1)
    assert compose == source
    assert example in ([], [compose])
