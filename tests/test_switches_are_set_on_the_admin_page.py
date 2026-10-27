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
    monkeypatch.setenv("START_PROBE", "on")
    assert switches.is_on("START_PROBE", False) is True
    stored["START_PROBE"] = False
    assert switches.is_on("START_PROBE", False) is False
    monkeypatch.delenv("START_PROBE")
    stored.clear()
    assert switches.is_on("START_PROBE", False) is False
    assert switches.is_on("START_PROBE", True) is True


def test_outside_the_services_the_stored_settings_are_not_read(monkeypatch, stored):
    monkeypatch.delenv("SWITCH_OVERRIDES_FROM_SETTINGS", raising=False)
    monkeypatch.setenv("START_PROBE", "on")
    stored["START_PROBE"] = False
    assert switches.is_on("START_PROBE", False) is True


def test_every_switch_is_listed_with_what_it_does_and_where_its_value_comes_from(monkeypatch, stored):
    monkeypatch.setenv("START_PROBE", "off")
    monkeypatch.delenv("MEASURE_ONCE", raising=False)
    stored["STALL_RULE"] = True

    listed = {entry["name"]: entry for entry in switch_catalogue.entries()}

    assert list(listed) == list(SWITCHES)
    for entry in listed.values():
        assert len(entry["summary"]) > 30, entry["name"]
        assert not any(generic in entry["summary"] for generic in _GENERIC), entry["name"]
    assert (listed["START_PROBE"]["docker"], listed["START_PROBE"]["on"], listed["START_PROBE"]["source"]) == (
        False, False, "docker")
    assert (listed["MEASURE_ONCE"]["docker"], listed["MEASURE_ONCE"]["source"]) == (None, "default")
    assert (listed["STALL_RULE"]["setting"], listed["STALL_RULE"]["on"], listed["STALL_RULE"]["source"]) == (
        True, True, "setting")
    assert listed["GUIDE_HEED_REFUSALS"]["summary"].startswith(
        __import__("app.models.guidance", fromlist=["BY_ID"]).BY_ID["heed_refusals"].title)


def test_the_page_lists_switches_and_an_administrator_sets_and_clears_one(client, monkeypatch):
    monkeypatch.setenv("START_PROBE", "on")
    listed = {entry["name"]: entry for entry in client.get("/api/settings/switches").json()}
    assert listed["START_PROBE"]["source"] == "docker" and listed["START_PROBE"]["on"] is True

    off = {e["name"]: e for e in client.put("/api/settings/switches/START_PROBE", json={"setting": False}).json()}
    assert (off["START_PROBE"]["setting"], off["START_PROBE"]["on"], off["START_PROBE"]["source"]) == (
        False, False, "setting")

    back = {e["name"]: e for e in client.put("/api/settings/switches/START_PROBE", json={"setting": None}).json()}
    assert (back["START_PROBE"]["setting"], back["START_PROBE"]["source"]) == (None, "docker")

    assert client.put("/api/settings/switches/NO_SUCH_SWITCH", json={"setting": True}).status_code == 404
