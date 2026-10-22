"""Every worker log line names the run and the stage that wrote it.

Several runs share one worker log over a day of runs and deploys; an audit had
to filter by time window and guess which run a line belonged to.
"""

from __future__ import annotations

import io
import logging

from app.observability import log_context


def _logger() -> tuple[logging.Logger, io.StringIO]:
    stream = io.StringIO()
    logger = logging.getLogger("test.log_context")
    logger.handlers = [logging.StreamHandler(stream)]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    log_context.install(logger)
    return logger, stream


def test_a_line_inside_a_run_names_it_and_one_outside_says_so() -> None:
    logger, stream = _logger()

    logger.info("outside")
    with log_context.for_the_run("run-deadbeef-0000-0000-0000-000000000000"):
        logger.info("inside")

    first, second = stream.getvalue().splitlines()
    assert first.endswith("[- -] outside")
    assert second.endswith("[run-deadbeef -] inside")


def test_the_graph_s_config_names_the_stage(monkeypatch) -> None:
    logger, stream = _logger()
    monkeypatch.setattr(log_context, "_from_the_graph", lambda: ("run-abc12345-x", "defect_fix_1_0"))

    logger.warning("Reverted defect_fix_1_0")

    assert "[run-abc12345 defect_fix_1_0] Reverted defect_fix_1_0" in stream.getvalue()


def test_installing_twice_adds_one_filter() -> None:
    logger, _ = _logger()
    log_context.install(logger)

    assert sum(isinstance(f, log_context.RunContextFilter) for f in logger.handlers[0].filters) == 1
