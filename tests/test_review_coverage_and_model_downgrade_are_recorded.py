"""A review that saw part of the source, or ran on a weaker model, says so.

The security reviewer's request carries at most `SOURCE_BUDGET` characters of
source. It used to stop at the first file that did not fit, drop every later
one without naming it, and record a plain "passed". A configured judgement
model that could not be built fell back to the default model with a worker
log line nobody reads, while the run still read as independently reviewed.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from app.agents import security_reviewer
from app.agents.review_document import render_security_review
from app.agents.security_reviewer import (
    SecurityReviewOutput,
    _the_source_under_review,
    source_coverage,
)
from app.models import roles


def _files(root: Path, sizes: dict[str, int]) -> list[str]:
    for name, size in sizes.items():
        (root / name).write_text("x" * size)
    return list(sizes)


def test_every_file_that_does_not_fit_is_named_and_smaller_ones_still_fit(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(security_reviewer, "SOURCE_BUDGET", 1_000)
    names = _files(tmp_path, {"a.js": 600, "big.js": 900, "huge.js": 950, "b.js": 300})

    shown, not_shown = source_coverage(names, str(tmp_path))
    request = _the_source_under_review(names, str(tmp_path))

    assert shown == ["a.js", "b.js"] and not_shown == ["big.js", "huge.js"]
    assert "--- big.js (not shown" in request and "--- huge.js (not shown" in request
    assert "2 file(s) above are not shown" in request


def test_a_request_that_fits_says_nothing_about_missing_files(tmp_path) -> None:
    names = _files(tmp_path, {"a.js": 100})
    assert "not shown" not in _the_source_under_review(names, str(tmp_path))


def test_a_pass_over_part_of_the_source_is_recorded_as_one() -> None:
    review = SecurityReviewOutput(status="passed")
    partial = render_security_review(review, ["a.js"], ["big.js"])
    whole = render_security_review(review, ["a.js", "b.js"], [])

    assert "## Status: passed (over part of the source)" in partial and "- big.js" in partial
    assert "## Status: passed\n" in whole and "shown to the reviewer in full" in whole


def test_the_workflow_records_the_coverage() -> None:
    import inspect

    from app.graph import workflow

    source = inspect.getsource(workflow)
    assert "render_security_review(review, shown, not_shown)" in source


def test_a_judgement_model_that_cannot_be_built_is_named(monkeypatch) -> None:
    import app.models as models

    def broken(settings):
        raise ValueError("no key")

    monkeypatch.setattr(models, "build_default_chat_model", broken)
    default = object()

    assert roles.build_judgement_model(default, {"JUDGEMENT_MODEL": "strong-model"}) is default
    assert "strong-model" in roles.judgement_downgrade()
    assert "not independent reviews" in roles.judgement_downgrade()

    assert roles.build_judgement_model(default, {}) is default
    assert roles.judgement_downgrade() is None


def test_the_runner_puts_the_downgrade_in_the_run_history(monkeypatch) -> None:
    from app.server.runner import WorkflowRunner

    published = []

    class Bus:
        async def next_sequence(self, run_id):
            return 1

        async def publish(self, run_id, event):
            published.append(event)

    runner = SimpleNamespace(event_bus=Bus())
    record = SimpleNamespace(run_id="r", current_stage="stack_selector")
    monkeypatch.setattr(roles, "judgement_downgrade", lambda: "The judgement model 'm' could not be built")

    asyncio.run(WorkflowRunner._say_if_the_judgement_model_was_replaced(runner, record))

    assert len(published) == 1 and published[0].event_type == "log"
    assert published[0].metadata["kind"] == "judgement_model_replaced"


def test_no_downgrade_publishes_nothing(monkeypatch) -> None:
    from app.server.runner import WorkflowRunner

    runner = SimpleNamespace(event_bus=None)
    monkeypatch.setattr(roles, "judgement_downgrade", lambda: None)
    asyncio.run(WorkflowRunner._say_if_the_judgement_model_was_replaced(runner, SimpleNamespace(run_id="r")))
