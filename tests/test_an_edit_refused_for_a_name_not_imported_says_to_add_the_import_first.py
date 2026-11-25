"""An edit refused because it uses a name the file never imports says how that is fixed (found on a run).

One run's database stage sent the same edit three times, each refused for `"JSONB" is not defined`: the edit
replaced a block in the middle of the file, the import belongs at its top, and the refusal only said to send it
again fixed - which one edit cannot do.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from app.analysis import language_service
from app.tools import repository
from app.tools.repository import RepositoryToolError


def _refusal(tmp_path, monkeypatch, message, *, editing=True):
    (tmp_path / ".harness").mkdir()
    target = tmp_path / "svc" / "models.py"
    target.parent.mkdir()
    target.write_text("x = 1\n")
    answers = iter([SimpleNamespace(here=[]), SimpleNamespace(here=[{"line": 206, "message": message}])])
    monkeypatch.setattr(language_service, "underlined_any", lambda *a, **k: next(answers))
    with pytest.raises(RepositoryToolError) as raised:
        repository._refuse_if_it_adds_errors(target, "svc/models.py", "y = JSONB\n", "x = 1\n", editing=editing)
    return str(raised.value)


@pytest.mark.parametrize("message", ['"JSONB" is not defined', "Cannot find name 'JSONB'.", "undefined: JSONB"])
def test_an_edit_using_a_name_never_imported_is_told_to_send_the_import_with_it_in_one_call(tmp_path, monkeypatch, message):
    """One call may carry both changes (LF.1423): told to send the import alone, a fixer with two calls left sent the
    refused change again instead."""
    said = _refusal(tmp_path, monkeypatch, message)
    assert "Nothing was written" in said
    assert "its import" in said and "`changes`" in said


def test_any_other_error_is_refused_as_before(tmp_path, monkeypatch):
    said = _refusal(tmp_path, monkeypatch, 'Argument of type "str" cannot be assigned to parameter "n" of type "int"')
    assert said.endswith("Send it again with those fixed.")


def test_a_whole_file_write_is_not_told_to_edit_in_two_steps(tmp_path, monkeypatch):
    said = _refusal(tmp_path, monkeypatch, '"JSONB" is not defined', editing=False)
    assert "`changes`" not in said


def test_the_new_rule_names_no_banned_words():
    text = repository._how_to_name_what_is_not_defined([{"message": '"X" is not defined'}])
    assert text
    assert not re.search(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", text, re.IGNORECASE)
