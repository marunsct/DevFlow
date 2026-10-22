"""How a run delivers: `fast` or `thorough` (`DELIVERY_MODE`, a setting).

Measured on one run of a five-route notes service: 13 hours, 1,081 model
calls one after another, 2.8 million output tokens (half of them reasoning)
for 549 lines of product and 5,058 lines of tests. Most of the time went to
ceremony - four sprints each re-planned, reviewed and test-rounded - and to
an agent loop of about forty tool calls per work order.

Fast delivery keeps every stage and record and changes how much each does:

- a product with few criteria is one sprint (`scrum_master.max_sprints_for_criteria_count`);
- each work order's files are drafted straight from the specification, one
  call per file, several at once (`graph.drafting`), with the agent loop as
  the fallback for what a draft cannot do;
- a test round is the harness's own: the locked suite and the unit tests
  run, and what fails becomes a defect without a model reading it;
- tests are the ones the specification plans;
- the stages that build run with reasoning off: the specification has
  decided what they write. A fix reasons as configured - it has to find out
  why something fails first.

Thorough is the pipeline as it was. Each run is started in one or the other
(`for_the_run`, kept on the run's record); a run started without a choice
takes the deployment's `DELIVERY_MODE`, and the code's default is thorough.

What makes a run faster without taking anything out - the project memory,
errors refused at the write, a silent suite run file by file, gathering on
the build model, candidate fixes - is on in both.
"""

from __future__ import annotations

import contextvars
import os
from contextlib import contextmanager
from typing import Iterator, Mapping

FAST = "fast"
THOROUGH = "thorough"
MODES = (FAST, THOROUGH)


#: The mode the run being executed was started with; see `for_the_run`.
_THIS_RUN: contextvars.ContextVar[str | None] = contextvars.ContextVar("delivery_mode_of_the_run", default=None)


@contextmanager
def for_the_run(chosen: str | None) -> Iterator[None]:
    """Everything inside runs in the mode its run was started with.

    A run's mode is its own, chosen when it starts and kept on its record: it
    used to be a deployment setting beside the models, so changing it for
    one run changed it for every run, including ones already going.
    """
    value = str(chosen or "").strip().lower()
    token = _THIS_RUN.set(value if value in MODES else None)
    try:
        yield
    finally:
        _THIS_RUN.reset(token)


def mode(environment: Mapping[str, str] | None = None) -> str:
    """The delivery mode in force: the running run's own, else `fast` or `thorough` as deployed."""
    if environment is None and _THIS_RUN.get():
        return str(_THIS_RUN.get())
    if environment is None:
        try:
            from app.server.runtime_settings import effective_environment

            environment = effective_environment()
        except Exception:  # noqa: BLE001 - the deployed environment still stands
            environment = os.environ
    chosen = str(environment.get("DELIVERY_MODE") or "").strip().lower()
    return chosen if chosen in MODES else THOROUGH


def fast(environment: Mapping[str, str] | None = None) -> bool:
    """Whether this deployment delivers fast. See the module docstring."""
    return mode(environment) == FAST


def reviews_code_when_fast(environment: Mapping[str, str] | None = None) -> bool:
    """Whether fast delivery still runs the judgement model's code review over each batch's diff (Q amendment).

    Off unless the owner sets `FAST_CODE_REVIEW`: fast delivery leaves the
    review to the tests and checks, and the tests are what a weak suite makes
    weak. On, it is one review per batch over the diff since the last accepted
    state - bounded, fresh context, its findings anchored to a criterion, a
    test or a check as in thorough delivery. Benchmarked before any default
    changes.
    """
    if environment is None:
        try:
            from app.server.runtime_settings import effective_environment

            environment = effective_environment()
        except Exception:  # noqa: BLE001 - the deployed environment still stands
            environment = os.environ
    return str(environment.get("FAST_CODE_REVIEW") or "").strip().lower() in {"1", "true", "yes", "on"}

