"""Every switch can be turned on or off on the admin page, with what it does; one nobody set follows Docker.

Owner request 2026-10-27: an admin page where every switch can be switched on or off, each with an explanation of
what it does, which uses the stored setting when there is one and the deployed (Docker) value when there is not.
"""
from __future__ import annotations

import pytest

from app import switches
from app.observability.provenance import SWITCHES
from app.server import runtime_settings, switch_catalogue

#: What a switch object said of itself before it had an explanation of its own.
_GENERIC = ("One switch of this module", "One guide's switch", "as the switch registry reads one", "PH.4's switch")


@pytest.fixture
def stored(monkeypatch):
    values: dict[str, bool] = {}
    monkeypatch.setattr(runtime_settings, "switch_overrides", lambda refresh=False: dict(values))
    return values


def test_a_stored_setting_beats_docker_which_beats_the_code_default(monkeypatch, stored):
    monkeypatch.setenv("SWITCH_OVERRIDES_FROM_SETTINGS", "on")
    monkeypatch.setenv("TARGETED_SUITE_REPAIR", "on")
    assert switches.is_on("TARGETED_SUITE_REPAIR", False) is True
    stored["TARGETED_SUITE_REPAIR"] = False
    assert switches.is_on("TARGETED_SUITE_REPAIR", False) is False
    monkeypatch.delenv("TARGETED_SUITE_REPAIR")
    stored.clear()
    assert switches.is_on("TARGETED_SUITE_REPAIR", False) is False
    assert switches.is_on("TARGETED_SUITE_REPAIR", True) is True


def test_a_bundle_s_stored_setting_turns_its_features_off(monkeypatch, stored):
    monkeypatch.setenv("SWITCH_OVERRIDES_FROM_SETTINGS", "on")
    monkeypatch.setenv("PREMIUM_MODEL_TUNING", "on")
    monkeypatch.delenv("MODEL_GUIDANCE", raising=False)
    assert switches.is_on("MODEL_GUIDANCE", False) is True
    stored["PREMIUM_MODEL_TUNING"] = False
    assert switches.is_on("MODEL_GUIDANCE", True) is False


def test_outside_the_services_the_stored_settings_are_not_read(monkeypatch, stored):
    monkeypatch.delenv("SWITCH_OVERRIDES_FROM_SETTINGS", raising=False)
    monkeypatch.setenv("TARGETED_SUITE_REPAIR", "on")
    stored["TARGETED_SUITE_REPAIR"] = False
    assert switches.is_on("TARGETED_SUITE_REPAIR", False) is True


def test_the_bundles_and_experiments_are_listed_with_what_they_do_and_where_their_value_comes_from(monkeypatch, stored):
    monkeypatch.setenv("PREMIUM_MODEL_TUNING", "off")
    monkeypatch.delenv("PREMIUM_CHANGE_REQUESTS", raising=False)
    stored["TARGETED_SUITE_REPAIR"] = True

    listed = {entry["name"]: entry for entry in switch_catalogue.entries()}

    assert list(listed) == list(switches.operated())
    for entry in listed.values():
        assert len(entry["summary"]) > 30, entry["name"]
        assert not any(generic in entry["summary"] for generic in _GENERIC), entry["name"]
    assert (listed["PREMIUM_MODEL_TUNING"]["docker"], listed["PREMIUM_MODEL_TUNING"]["on"],
            listed["PREMIUM_MODEL_TUNING"]["source"]) == (False, False, "docker")
    assert (listed["PREMIUM_CHANGE_REQUESTS"]["docker"], listed["PREMIUM_CHANGE_REQUESTS"]["source"]) == (None, "default")
    assert (listed["TARGETED_SUITE_REPAIR"]["setting"], listed["TARGETED_SUITE_REPAIR"]["on"],
            listed["TARGETED_SUITE_REPAIR"]["source"]) == (True, True, "setting")
    assert "- GUIDE_HEED_REFUSALS: " + __import__("app.models.guidance", fromlist=["BY_ID"]).BY_ID[
        "heed_refusals"].title in listed["PREMIUM_MODEL_TUNING"]["details"]


def test_the_page_lists_switches_and_an_administrator_sets_and_clears_one(client, monkeypatch):
    monkeypatch.setenv("PREMIUM_DEEP_VERIFICATION", "on")
    listed = {entry["name"]: entry for entry in client.get("/api/settings/switches").json()}
    assert listed["PREMIUM_DEEP_VERIFICATION"]["source"] == "docker" and listed["PREMIUM_DEEP_VERIFICATION"]["on"] is True

    off = {e["name"]: e for e in client.put("/api/settings/switches/PREMIUM_DEEP_VERIFICATION", json={"setting": False}).json()}
    assert (off["PREMIUM_DEEP_VERIFICATION"]["setting"], off["PREMIUM_DEEP_VERIFICATION"]["on"],
            off["PREMIUM_DEEP_VERIFICATION"]["source"]) == (False, False, "setting")

    back = {e["name"]: e for e in client.put("/api/settings/switches/PREMIUM_DEEP_VERIFICATION", json={"setting": None}).json()}
    assert (back["PREMIUM_DEEP_VERIFICATION"]["setting"], back["PREMIUM_DEEP_VERIFICATION"]["source"]) == (None, "docker")

    assert client.put("/api/settings/switches/NO_SUCH_SWITCH", json={"setting": True}).status_code == 404
    assert client.put("/api/settings/switches/STALL_RULE", json={"setting": False}).status_code == 404  # built in
