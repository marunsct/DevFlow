"""The start form opens as the owner last started a run (plan UI-S5, run defaults).

About a dozen choices - delivery mode, model, unattended, the review points,
the approval timeout - were reset on every visit to the start page. They are
kept with the user's preferences, so they follow the owner to another browser,
and an empty object forgets them.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.server import auth

UI = Path(__file__).resolve().parents[1] / "langchain-ui" / "src"


def test_run_defaults_are_a_preference_with_known_values_only():
    saved = auth.Preferences(run_defaults={"delivery_mode": "thorough", "reviews": {"release": False}})
    assert saved.model_dump(exclude_none=True) == {"run_defaults": {"delivery_mode": "thorough", "reviews": {"release": False}}}
    assert auth.Preferences(run_defaults={}).model_dump(exclude_none=True) == {"run_defaults": {}}
    for bad in ({"delivery_mode": "slow"}, {"approval_timeout_minutes": 0}, {"use_frontier_model": "maybe"}):
        with pytest.raises(ValidationError):
            auth.Preferences(run_defaults=bad)


def test_the_route_keeps_them_beside_the_appearance(client):
    body = client.patch("/api/auth/me/preferences", json={"run_defaults": {"delivery_mode": "thorough", "unattended": True}}).json()
    assert body["preferences"]["run_defaults"] == {"delivery_mode": "thorough", "unattended": True}


def test_the_start_form_reads_and_saves_them_and_settings_can_forget_them():
    home = (UI / "pages/Home.tsx").read_text()
    assert "readRunDefaults()" in home and "await saveRunDefaults(" in home
    assert "<RunDefaultsCard />" in (UI / "pages/Settings.tsx").read_text()
    assert "run_defaults: {}" in (UI / "lib/runDefaults.ts").read_text()
