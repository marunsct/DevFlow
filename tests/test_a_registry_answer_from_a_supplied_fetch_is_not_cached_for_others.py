"""A registry answer read through a fetch the caller supplied is not handed to the next caller asking the same name.

Found when the dependency gate began asking the registry at every install: an answer one caller's stub gave for a
package was cached process-wide and returned to the next caller, whose own stub said something else.
"""
from __future__ import annotations

import json

from app.tools import package_registry


def _answer(home):
    body = {"info": {"version": "1.0.0", "home_page": home, "project_urls": {}}}
    return lambda url: (200, json.dumps(body).encode())


def test_each_supplied_fetch_gets_its_own_answer(monkeypatch):
    monkeypatch.setattr(package_registry, "_CACHE", {})

    first = package_registry.look_up("pypi", "some-library", fetch=_answer("https://one.example"))
    second = package_registry.look_up("pypi", "some-library", fetch=_answer("https://two.example"))

    assert first["homes"] == ["https://one.example"] and second["homes"] == ["https://two.example"]
