"""A defect whose failure names no file, or many, is localised by one cheap call before it is rewritten (plan AY step 1).

Behind `LOCALISE_FIRST`, off until measured. A failure that named no file sent
its defect to the agent loop to find it by reading.
"""
from __future__ import annotations

import json
import os
import re
from types import SimpleNamespace
from unittest import mock

from app.graph import localisation, rewritten_fixes

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
ON = {"LOCALISE_FIRST": "on"}
DEFECT = SimpleNamespace(description="[AC-2] Sign in answers 500", expected_behavior="200 with a token",
                         actual_behavior="500", affected_files=[])


class _Model:
    def __init__(self, answer):
        self.answer, self.asked = answer, []

    def model_copy(self, update=None):
        return self

    def invoke(self, messages, **kwargs):
        self.asked.append((messages, kwargs))
        return SimpleNamespace(content=json.dumps(self.answer))


def _project(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "auth.py").write_text("def issue_token(user):\n    return None\n")
    (tmp_path / "app" / "main.py").write_text("from app.auth import issue_token\n")
    return tmp_path


def test_on_a_failure_naming_no_file_is_localised_to_the_files_that_hold_the_named_symbols(tmp_path):
    root = _project(tmp_path)
    model = _Model({"files": ["app/auth.py", "app/main.py", "app/gone.py"], "symbols": ["def issue_token"],
                    "hypothesis": "issue_token returns nothing"})
    with mock.patch.dict(os.environ, ON):
        files = localisation.localised(DEFECT, "500 Internal Server Error", root, model, [], lambda _: True)

    assert files == ["app/auth.py"]
    (messages, kwargs), = model.asked
    assert kwargs["max_tokens"] == localisation.MOST_OUTPUT_TOKENS
    assert not BANNED.search(messages[-1].content.split("What failed:")[1].split("What each file")[0] + messages[-1].content.split("Name at most")[1])


def test_off_few_files_or_an_answer_that_confirms_nothing_leave_the_files_as_found(tmp_path):
    root = _project(tmp_path)
    model = _Model({"files": ["app/gone.py"], "symbols": [], "hypothesis": ""})
    with mock.patch.dict(os.environ, {"LOCALISE_FIRST": ""}):
        assert localisation.localised(DEFECT, "x", root, model, [], lambda _: True) == []
    with mock.patch.dict(os.environ, ON):
        assert localisation.localised(DEFECT, "x", root, model, ["app/main.py"], lambda _: True) == ["app/main.py"]
        assert localisation.localised(DEFECT, "x", root, model, [], lambda _: True) == []
    assert len(model.asked) == 1


def test_the_rewrite_takes_the_localised_files(tmp_path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.setattr(rewritten_fixes, "files_to_fix", lambda *a, **k: [])
    seen = []
    monkeypatch.setattr("app.graph.localisation.localised",
                        lambda defect, failure, root, model, found, may_write: seen.append(found) or [])
    assert rewritten_fixes.fix_by_rewriting(DEFECT, root, None, last_failure="boom") is None
    assert seen == [[]]
