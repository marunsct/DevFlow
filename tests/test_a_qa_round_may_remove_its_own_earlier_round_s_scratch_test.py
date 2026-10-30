"""A QA round is not "another stage" to the tests an earlier round of the same author wrote.

Measured on a held-out run: QA left two probe specs in its first round. Later rounds are stages of the same name
with a round number, so the delete tool refused them as "a test that acceptance_author_1 wrote". The suite was
locked with the probes, reopened for one of them, and QA spent thirty calls editing and deleting a scratch file it
had written itself.
"""
from __future__ import annotations

from pathlib import Path

from app.analysis import project_memory
from app.observability import transcript
from app.tools.repository import _another_stage_s_test, _this_stage_created

SPEC = "shop/acceptance/probe.spec.js"


def _written_by(root: Path, monkeypatch, created_by: str, running: str) -> None:
    target = root / SPEC
    target.parent.mkdir(parents=True)
    target.write_text("import { test } from '@playwright/test';\ntest('p', () => {});\n", encoding="utf-8")
    monkeypatch.setattr(project_memory, "who_created", lambda r, shown: created_by)
    monkeypatch.setattr(transcript, "_stage_from_config", lambda default="": running)


def test_a_later_round_of_the_same_author_owns_an_earlier_round_s_test(tmp_path: Path, monkeypatch) -> None:
    _written_by(tmp_path, monkeypatch, "acceptance_author_1", "acceptance_author_2")
    assert _another_stage_s_test(tmp_path, SPEC) == ""
    assert _this_stage_created(tmp_path, SPEC) is True


def test_a_test_another_kind_of_stage_wrote_is_still_its_own(tmp_path: Path, monkeypatch) -> None:
    _written_by(tmp_path, monkeypatch, "acceptance_author_1", "specialist_testing_1")
    assert _another_stage_s_test(tmp_path, SPEC) == "acceptance_author_1"
    assert _this_stage_created(tmp_path, SPEC) is False


def test_rounds_of_other_stages_are_not_one_author() -> None:
    from app.tools.repository import _the_same_author

    assert _the_same_author("acceptance_author_0", "acceptance_author_3") is True
    assert _the_same_author("specialist_testing_1", "specialist_testing_2") is False
    assert _the_same_author("acceptance_author_1", "acceptance_review_1") is False
