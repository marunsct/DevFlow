"""The sentence naming what was checked, against the checks that ran.

It was hand-written and hand-maintained, and by the time four more checks had
been added it described none of them: a reviewer reading "here is what was
checked" got a list four items short, in the one block of the brief that is
labelled "deterministic, not a model's opinion".

One list now produces both, so they cannot drift.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.analysis.integration_checks import _CHECKS, summarise_integration


def test_every_check_is_described() -> None:
    for describe, check in _CHECKS:
        assert describe, "every check needs a phrase a reviewer can read"
        assert callable(check)


def test_no_two_checks_share_a_description() -> None:
    """A duplicate means one of them was added by copying and left unrenamed."""
    descriptions = [describe for describe, _ in _CHECKS]

    assert len(set(descriptions)) == len(descriptions)


def test_the_sentence_names_every_check(tmp_path: Path) -> None:
    project = tmp_path / "app"
    project.mkdir()
    (project / "package.json").write_text(json.dumps({"name": "app"}), encoding="utf-8")
    (project / "app.js").write_text("export const a = 1;\n", encoding="utf-8")

    summary = summarise_integration(str(tmp_path))

    for describe, _ in _CHECKS:
        assert describe in summary, f"the summary does not mention {describe!r}"


def test_the_named_checks_are_the_ones_that_run(tmp_path: Path) -> None:
    """A check in the list that is never called, or called and not listed, is
    the drift this registry exists to stop."""
    import app.analysis.integration_checks as module

    called = set()
    wrapped = tuple(
        (describe, _spy(check, describe, called)) for describe, check in _CHECKS
    )
    original = module._CHECKS
    module._CHECKS = wrapped
    try:
        project = tmp_path / "app"
        project.mkdir()
        (project / "app.js").write_text("export const a = 1;\n", encoding="utf-8")
        summarise_integration(str(tmp_path))
    finally:
        module._CHECKS = original

    assert called == {describe for describe, _ in _CHECKS}


def _spy(check, describe, called):
    def wrapper(files, root, stack):
        called.add(describe)
        return check(files, root, stack)

    return wrapper


def test_a_workspace_that_cannot_be_read_says_so(tmp_path: Path) -> None:
    assert "could not" in summarise_integration(str(tmp_path / "nowhere"))
