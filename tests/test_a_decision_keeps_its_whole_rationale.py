"""A decision keeps its whole rationale; only the rendered log shortens it.

Callers cut rationales at 1500 characters, and one run's decision log showed a
suite summary where the lead's own decisions had been: they came after the cut.
And every locked version of the acceptance suite is kept, with what changed.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from app import decisions
from app.acceptance import suite


def test_the_record_is_whole_and_the_log_says_where(tmp_path) -> None:
    long = "x" * 1600 + " the part that used to be cut"
    update: dict = {}

    decisions.record_decision(
        {"repository": SimpleNamespace(root_path=str(tmp_path))}, update,
        point="sprint", question="Is it done?", decision="accept", rationale=long,
    )

    assert update["decisions"][-1]["rationale"] == long
    full = json.loads((tmp_path / decisions.FULL_RECORDS).read_text())
    assert full[-1]["rationale"] == long
    rendered = (tmp_path / "docs" / "decision_log.md").read_text()
    assert "the part that used to be cut" in rendered


def test_only_a_very_long_one_is_shortened_when_rendered() -> None:
    record = decisions.make_record(number=3, point="p", question="q", decision="d", rationale="y" * 5000)

    text = decisions.render([record])

    assert "shortened here; the whole of it is DR-3" in text


class TestEveryLockedVersionIsKept:
    @staticmethod
    def _suite(root, text: str) -> None:
        (root / ".project-directory").write_text("notes\n")
        target = root / "notes" / "acceptance" / "notes.spec.js"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def test_each_lock_is_a_version_and_a_relock_says_what_changed(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(suite, "suite_files", lambda root: sorted((tmp_path / "notes" / "acceptance").glob("*.js")))
        self._suite(tmp_path, "test('[AC-1] adds', () => { expect(2) });\n")
        suite.lock(tmp_path)
        assert suite.changes_at_this_lock(tmp_path) == ""

        self._suite(tmp_path, "test('[AC-1] adds', () => { expect(1) });\n")
        suite.lock(tmp_path)

        changed = suite.changes_at_this_lock(tmp_path)
        assert changed.startswith("Locked as version 2: 1 line(s) added and 1 removed since version 1")
        assert "-test('[AC-1] adds', () => { expect(2) });" in changed
        assert (tmp_path / suite.LOCKS_DIR / "v1").is_dir() and (tmp_path / suite.LOCKS_DIR / "v2.diff").is_file()
