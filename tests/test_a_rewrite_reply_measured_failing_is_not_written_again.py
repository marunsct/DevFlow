"""A rewrite's reply that writes the same file an earlier rewrite wrote, measured failing, is not written or measured
again: the defect goes to the agent loop (deep review of silent mechanisms, 2026-11-25).

`REPEATED_REWRITE_PROMPT_STOP` fingerprinted only the request, which grows a little every attempt: over 30 runs 1 of
221 rewrite requests repeated an earlier one and the stop never fired, while 35 of 215 replies were byte-identical to
an earlier reply of the same run. The reply here is one a model sent three times for one file over nine minutes.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.graph import repeated_rewrite_prompts, rewritten_fixes

REPLY = (Path(__file__).parent / "captured" / "rewrite-reply-repeated-three-times.txt").read_text(encoding="utf-8")
BEFORE = "import { Hono } from 'hono';\n\nexport function createApp(storage) {\n  return new Hono();\n}\n"


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setenv("REPEATED_REWRITE_PROMPT_STOP", "on")
    repeated_rewrite_prompts.forget()
    yield
    repeated_rewrite_prompts.forget()


class _Model:
    """The model, at the edge: the same reply to every request."""

    def __init__(self):
        self.asked = 0

    def invoke(self, messages, **_):
        self.asked += 1
        return SimpleNamespace(content=REPLY)


def _defect(failure):
    return SimpleNamespace(description="GET /health answers 404", expected_behavior="200", affected_files=["src/app.ts"],
                           actual_behavior=failure, reproduction_steps=[])


def _workspace(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.ts").write_text(BEFORE)
    return tmp_path


def _rewrite(root, model, failure, written):
    def write(base, path, content):
        written.append(path)
        (root / path).write_text(content)

    return rewritten_fixes.fix_by_rewriting(_defect(failure), root, model, files=["src/app.ts"], write=write,
                                            last_failure=failure)


def test_the_same_reply_after_its_fix_was_reverted_is_not_written_again(tmp_path):
    root, model, written = _workspace(tmp_path), _Model(), []
    first = _rewrite(root, model, "expected 200, got 404 at /health", written)
    (root / "src" / "app.ts").write_text(BEFORE)  # the harness measured it failing and reverted it

    second = _rewrite(root, model, "expected 200, got 404 at /health (second attempt)", written)

    assert first is not None and second is None, "the second goes to the agent loop"
    assert written == ["src/app.ts"], "written once, not measured a second time"
    assert (root / "src" / "app.ts").read_text() == BEFORE


def test_a_candidate_that_writes_what_failed_before_is_not_measured_again(tmp_path):
    root, model, written = _workspace(tmp_path), _Model(), []
    _rewrite(root, model, "expected 200, got 404 at /health", written)
    (root / "src" / "app.ts").write_text(BEFORE)
    measured = []

    kept = rewritten_fixes.fix_by_candidates(
        _defect("expected 200, got 404 at /health (again)"), root, model, lambda: measured.append(1) or False,
        files=["src/app.ts"], write=lambda base, path, content: (root / path).write_text(content))

    assert kept is None
    assert measured == [1], "asked only whether the defect has tests to choose by, never to judge a candidate"


def test_with_the_switch_off_the_same_reply_is_written_again(tmp_path, monkeypatch):
    monkeypatch.setenv("REPEATED_REWRITE_PROMPT_STOP", "off")
    root, model, written = _workspace(tmp_path), _Model(), []
    _rewrite(root, model, "expected 200, got 404 at /health", written)
    (root / "src" / "app.ts").write_text(BEFORE)

    _rewrite(root, model, "expected 200, got 404 at /health (second attempt)", written)

    assert written == ["src/app.ts", "src/app.ts"]
