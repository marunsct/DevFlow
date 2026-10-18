"""The owner's theme, accent and density are kept on their account (plan Part 15.2).

localStorage is the fast path and the server's value wins when the interface
starts, so a choice made on one device is there on the next. The patch changes
only what it names, and only known values are accepted.
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.server import auth

UI = Path(__file__).resolve().parents[1] / "langchain-ui" / "src"


def test_a_patch_names_only_what_it_changes_and_only_known_values():
    assert auth.Preferences(theme="paper").model_dump(exclude_none=True) == {"theme": "paper"}
    assert auth.Preferences().model_dump(exclude_none=True) == {}
    for bad in ({"theme": "neon"}, {"accent": "green"}, {"density": "tiny"}):
        with pytest.raises(ValidationError):
            auth.Preferences(**bad)


def test_stored_preferences_are_read_back_and_a_bad_value_is_empty():
    assert auth._read_preferences(json.dumps({"theme": "contrast", "accent": "teal"})) == {"theme": "contrast", "accent": "teal"}
    assert auth._read_preferences("not json") == {}
    assert auth._read_preferences(None) == {}
    assert auth._read_preferences("[1, 2]") == {}


def test_the_user_carries_them_and_the_table_has_the_column():
    assert auth.User(username="a").preferences == {}
    source = inspect.getsource(auth)
    assert "ADD COLUMN IF NOT EXISTS preferences TEXT NOT NULL DEFAULT '{}'" in source
    assert "COALESCE(preferences, '{}')" in source
    assert '"/api/auth/me/preferences"' in source and "preferences=current_user.preferences" in source


def test_the_interface_pulls_applies_and_pushes_them():
    store = (UI / "lib/appearance.ts").read_text()
    assert "api.patch('/auth/me/preferences'" in store and "adoptServerPreferences" in store
    assert "adoptServerPreferences(me.data?.preferences)" in (UI / "App.tsx").read_text()
    assert "<ThemeToggle />" in (UI / "components/Layout.tsx").read_text()
    assert "<AppearanceSettings />" in (UI / "pages/Settings.tsx").read_text()
    assert "event.key !== 't'" in (UI / "components/ThemeToggle.tsx").read_text()
