"""A service in another language than JavaScript keeps the acceptance runner's manifest as the harness wrote it.

Measured on one Ruby run: the drafting pass rewrote `package.json` - which holds only the acceptance runner - with a
second Playwright (`playwright` 1.40 beside `@playwright/test` 1.64); the runner collected no test ("Playwright Test
did not expect test() to be called here") and the suite went back to its writer.
"""
from __future__ import annotations

import json

import pytest

from app.stacks import contract, pack_named


@pytest.mark.parametrize("pack", ["ruby-sinatra-api", "php-slim-api", "go-http-api", "csharp-aspnet-api",
                                  "rust-axum-api", "java-spring-api"])
def test_a_service_in_another_language_keeps_package_json(pack):
    assert "package.json" in pack_named(pack).kept_files


@pytest.mark.parametrize("pack", ["node-hono-api", "node-nest-api"])
def test_a_javascript_service_s_manifest_is_its_own(pack):
    assert "package.json" not in pack_named(pack).kept_files


def test_a_rewritten_runner_manifest_is_put_back(tmp_path):
    pack = pack_named("ruby-sinatra-api")
    contract.write(tmp_path, pack, "notes-api", "Notes")
    manifest = tmp_path / "notes-api" / "package.json"
    if not manifest.exists():
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(pack.render("notes-api", "Notes", None)["package.json"])
    drafted = json.loads(manifest.read_text())
    drafted["devDependencies"]["playwright"] = "1.40"
    manifest.write_text(json.dumps(drafted))

    contract.enforce(tmp_path)

    assert "playwright\"" not in manifest.read_text().replace("@playwright/test", "")
