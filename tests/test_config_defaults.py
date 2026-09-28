"""The deployed defaults must agree with the defaults in the code.

Every tunable here exists twice: once as a fallback in Python, and once as
`${VAR:-default}` in `docker-compose.yml`. Compose always wins, because it sets
the variable before the process starts - so a default "fixed" only in Python is
not fixed at all, and the code reads as though it were.

This has now happened twice, in both directions:

- `CTX_KEEP_MESSAGES` was changed 20 -> 10 on the `ContextPolicy` field while
  `ContextPolicy.from_environment` kept reading a hard-coded 20. The commit
  message even noted that an env override would shadow a code default, caught
  it for compose, and missed the one two lines from the field it edited.
- `WORKFLOW_MAX_GATES_PER_STAGE` was raised 25 -> 120 in `runner.py`, with a
  docstring explaining at length why 25 strands an iterative specialist mid-work
  - while compose went on passing 25. On one run `specialist_testing_3` was
  stopped at exactly 25 gates, having made real progress the whole way, and lost
  all of it.

Reading the two files and comparing them is the only check that catches this,
because both halves are individually correct and the bug lives in the gap.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

COMPOSE = Path(__file__).resolve().parent.parent / "docker-compose.yml"

#: `NAME: ${NAME:-default}` - the only form this file uses for a tunable.
_DEFAULT = re.compile(r"^\s*([A-Z0-9_]+):\s*\$\{\1:-([^}]*)\}\s*$", re.MULTILINE)


def _compose_defaults() -> dict[str, str]:
    return {name: value for name, value in _DEFAULT.findall(COMPOSE.read_text())}


def _code_default(monkeypatch, variable: str, read):
    """The value the code falls back to when the variable is absent."""
    monkeypatch.delenv(variable, raising=False)
    return read()


def _gates_per_stage():
    from app.server.runner import _max_gates_per_stage

    return _max_gates_per_stage()


def _gates():
    from app.server.runner import _max_gates

    return _max_gates()


def _output_tokens():
    from app.models import _max_output_tokens

    return _max_output_tokens()


def _sandbox_output():
    from app.tools.sandbox import _max_output_size

    return _max_output_size()


def _keep_messages():
    from app.agents.context_policy import ContextPolicy

    return ContextPolicy.from_environment().keep_recent_messages


def _max_context_tokens():
    from app.agents.context_policy import ContextPolicy

    return ContextPolicy.from_environment().max_context_tokens


def _celery_soft():
    from app.server.tasks import celery_app

    return celery_app.conf.task_soft_time_limit


#: variable -> how to read the code's own fallback for it.
TUNABLES = {
    "WORKFLOW_MAX_GATES_PER_STAGE": _gates_per_stage,
    "WORKFLOW_MAX_GATES": _gates,
    "MODEL_MAX_OUTPUT_TOKENS": _output_tokens,
    "SANDBOX_MAX_OUTPUT": _sandbox_output,
    "CTX_KEEP_MESSAGES": _keep_messages,
    "CTX_MAX_TOKENS": _max_context_tokens,
}


@pytest.mark.parametrize("variable", sorted(TUNABLES))
def test_the_compose_default_matches_the_code_default(variable, monkeypatch):
    compose = _compose_defaults()
    if variable not in compose:
        pytest.skip(f"{variable} is not given a default in docker-compose.yml")

    expected = _code_default(monkeypatch, variable, TUNABLES[variable])

    assert int(compose[variable]) == int(expected), (
        f"docker-compose.yml passes {variable}={compose[variable]}, but the code "
        f"falls back to {expected}. Compose wins at runtime, so the code default "
        "is dead and whatever reasoning its docstring gives is not in effect."
    )


def test_celery_limits_leave_room_for_the_soft_one_to_fire(monkeypatch):
    """A soft limit at or above the hard limit never fires, so nothing unwinds."""
    compose = _compose_defaults()
    soft = int(compose["CELERY_TASK_SOFT_TIME_LIMIT"])
    hard = int(compose["CELERY_TASK_TIME_LIMIT"])

    assert soft < hard
    monkeypatch.delenv("CELERY_TASK_SOFT_TIME_LIMIT", raising=False)
    assert soft == int(_celery_soft())


def test_every_compose_default_is_parseable():
    """A guard on the guard: a formatting change must not silently empty this."""
    assert len(_compose_defaults()) > 10
