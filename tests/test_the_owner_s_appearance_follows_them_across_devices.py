"""The owner's theme, accent and density are kept on their account (plan Part 15.2).

localStorage is the fast path and the server's value wins when the interface
starts, so a choice made on one device is there on the next. The patch changes
only what it names, and only known values are accepted. The interface's side is
tested in `langchain-ui/src/lib/appearance.test.ts`.
"""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.server import auth


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


def test_a_choice_saved_from_one_device_is_the_account_s_on_the_next_sign_in(client, test_db, test_user):
    with auth.get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO users (username, hashed_password, disabled, role, tenant_id, preferences) "
                        "VALUES ('testuser', 'x', FALSE, 'admin', 'default', '{\"theme\": \"paper\"}')")
        conn.commit()
    test_user.preferences = {"theme": "paper"}  # as the sign-in read it

    client.patch("/api/auth/me/preferences", json={"accent": "teal"})

    assert auth.get_user("testuser").preferences == {"theme": "paper", "accent": "teal"}
