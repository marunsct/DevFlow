"""Fast delivery refuses a product file write that adds errors the language service is sure of.

One run's drafts declared a variable twice and named a type that did not
exist; a test round found it half an hour later, through a model.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from app import delivery
from app.analysis import language_service
from app.tools.repository import RepositoryToolError, _refuse_if_it_adds_errors

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _service(content_to_findings):
    def underlined_any(root, target, content, project=None):
        return SimpleNamespace(here=content_to_findings.get(content, []))
    return underlined_any


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / ".harness").mkdir()
    (tmp_path / "notes-api" / "src").mkdir(parents=True)
    monkeypatch.setattr(delivery, "fast", lambda environment=None: True)
    return tmp_path


def test_an_error_new_to_the_write_is_refused_with_it(project, monkeypatch):
    target = project / "notes-api" / "src" / "validate.ts"
    monkeypatch.setattr(language_service, "underlined_any", _service({
        "after": [{"line": 5, "message": "Cannot redeclare block-scoped variable 'MAX_SAFE_ID'."}],
    }))

    with pytest.raises(RepositoryToolError) as refused:
        _refuse_if_it_adds_errors(target, "notes-api/src/validate.ts", "after", "before")

    assert "line 5: Cannot redeclare block-scoped variable 'MAX_SAFE_ID'" in str(refused.value)
    assert not BANNED.search(str(refused.value))


def test_an_error_that_was_there_already_or_is_about_another_file_is_not(project, monkeypatch):
    target = project / "notes-api" / "src" / "app.ts"
    old = [{"line": 2, "message": "Cannot find name 'Store'."}]
    monkeypatch.setattr(language_service, "underlined_any", _service({
        "before": old,
        "after": [*old, {"line": 1, "message": "Module './store' has no exported member 'createStore'."}],
    }))

    _refuse_if_it_adds_errors(target, "notes-api/src/app.ts", "after", "before")


def test_a_test_file_or_a_thorough_run_is_left_alone(project, monkeypatch):
    monkeypatch.setattr(language_service, "underlined_any", _service({"after": [{"line": 1, "message": "bad"}]}))

    _refuse_if_it_adds_errors(project / "notes-api" / "tests" / "a.test.ts", "notes-api/tests/a.test.ts", "after", "")
    monkeypatch.setattr(delivery, "fast", lambda environment=None: False)
    _refuse_if_it_adds_errors(project / "notes-api" / "src" / "a.ts", "notes-api/src/a.ts", "after", "")
