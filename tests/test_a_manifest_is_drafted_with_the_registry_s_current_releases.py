"""A dependency manifest is drafted with the registry's current release of each package the specification names
(plan WL.4, trigger T4).

Measured: a model pins the versions it remembers, and one Ruby run lost 267 minutes to a Gemfile pinning a version
RubyGems never had; the registry's real versions reached a fixer only after the install had failed (LF.1132, LF.1138).
Only package registries are asked - package metadata, as every install reads - so it runs whatever the run's "Internet
lookups" choice, and only `PACKAGE_LOOKUP_ENABLED` turns it off.
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest

from app.agents.principal_architect import TechnicalSpecificationOutput
from app.graph import drafting, registry_versions
from app.tools import package_registry

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

SPECIFICATION = TechnicalSpecificationOutput(
    product_scope="Notes.",
    library_usage=["hono 4.6: import { Hono } from 'hono'; new Hono() -> the app",
                   "zod - import { z } from 'zod'; z.object({...}).safeParse(body)"],
    configuration=["PORT: 3000", "dependency: @hono/node-server 1.13"],
)
#: What the npm registry has today, by package.
RELEASES = {"hono": "4.10.2", "zod": "4.1.12", "@hono/node-server": "1.19.5"}


@pytest.fixture
def registry(monkeypatch):
    """The npm registry, answering for the packages it has and 404 for any other; every URL asked is kept."""
    asked: list[str] = []

    def fetch(url, most_bytes=0):
        asked.append(url)
        name = url.removeprefix("https://registry.npmjs.org/").removesuffix("/latest")
        if name in RELEASES:
            return 200, json.dumps({"name": name, "version": RELEASES[name]}).encode()
        return 404, b"{}"

    monkeypatch.setattr(package_registry, "_fetch", fetch)
    monkeypatch.setattr(package_registry, "_CACHE", {})
    monkeypatch.setattr(package_registry, "runtime_here", lambda ecosystem: "v22.12.0")
    monkeypatch.setattr(registry_versions, "_SHOWN", {})
    monkeypatch.setenv("REGISTRY_VERSIONS_BEFORE_A_MANIFEST", "on")
    return asked


def _drafted(root, path="package.json", specification=SPECIFICATION):
    return drafting.draft_request(root, path, SimpleNamespace(task_description="Set up the service"), specification,
                                  SimpleNamespace(language="TypeScript", framework="Hono"))


def test_the_manifest_s_draft_is_shown_each_named_package_s_current_release(tmp_path, registry, monkeypatch):
    recorded = []
    monkeypatch.setattr("app.observability.transcript.record", lambda *a, **k: recorded.append(k))
    monkeypatch.setattr("app.observability.transcript._run_id_from_config", lambda: "run-x")

    request = _drafted(tmp_path)

    shown = request[request.index("--- Current releases from the registry ---"):]
    assert "`hono`: 4.10.2" in shown and "`zod`: 4.1.12" in shown and "`@hono/node-server`: 1.19.5" in shown
    assert "PORT" not in shown and not BANNED.search(shown)
    assert all(url.startswith("https://registry.npmjs.org/") for url in registry)
    assert [entry["detail"].split(" registry")[0] for entry in recorded if entry.get("event") == "lookup"] == ["T4"]


def test_it_holds_when_the_run_chose_no_internet_lookups(tmp_path, registry, monkeypatch):
    monkeypatch.setenv("WEB_LOOKUP_WHEN_STUCK", "off")

    assert "`hono`: 4.10.2" in _drafted(tmp_path, "notes-api/package.json")


def test_a_file_that_declares_no_packages_asks_no_registry(tmp_path, registry):
    request = _drafted(tmp_path, "src/app.ts")

    assert "Current releases from the registry" not in request and registry == []


def test_with_package_lookups_off_no_registry_is_asked(tmp_path, registry, monkeypatch):
    monkeypatch.setenv("PACKAGE_LOOKUP_ENABLED", "off")

    request = _drafted(tmp_path)

    assert "Current releases from the registry" not in request and registry == []


def test_a_rewrite_of_the_manifest_is_shown_them_too(tmp_path, registry):
    from app.graph.rewritten_fixes import fix_request

    (tmp_path / "package.json").write_text('{"dependencies": {"hono": "^9.9.9"}}\n')
    defect = SimpleNamespace(description="The dependencies do not install", expected_behavior="installed",
                             actual_behavior="No matching version found for hono@^9.9.9", attempts=[])

    request = fix_request(tmp_path, "package.json", defect, "npm error notarget", SPECIFICATION,
                          SimpleNamespace(language="TypeScript", framework="Hono"), [], [])

    assert "`hono`: 4.10.2" in request
