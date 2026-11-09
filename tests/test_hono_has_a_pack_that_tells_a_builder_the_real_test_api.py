"""Hono in TypeScript is set up by the harness, from a pack, instead of by a model inventing its test harness.

Measured on a benchmark stack: with no pack, a small model's setup stage wrote a unit test against
`createTestClient` from `hono/testing` (which does not exist), could not get one test to run, and the run
failed because its acceptance suite could not run. The pack scaffolds a service whose two smoke tests passed
for real (install, `npm test`, `npx playwright test`) and tells every builder how a Hono app is tested.
"""
from __future__ import annotations

import json

from app.stacks import pack_named


def test_the_pack_builds_a_hono_app_that_its_unit_test_calls_in_memory():
    pack = pack_named("node-hono-api")
    assert pack is not None and pack.language == "typescript" and pack.frameworks == ("hono",)
    assert "createApp().request('/health')" in pack.smoke_files["test/scaffold-smoke.spec.ts"]
    assert "serve(" in pack.files["src/main.ts"] and "createApp" in pack.files["src/app.ts"]


def test_the_guide_names_the_test_api_a_builder_must_not_invent():
    guide = pack_named("node-hono-api").guide
    flat = guide.replace("\n", " ")
    assert "createApp().request" in flat
    # `hono/testing` exports `testClient` and nothing else: the guide must not deny what exists nor allow what does not.
    assert "exports only `testClient`" in flat and "no `createClient`" in flat and "no `createTestClient`" in flat
    assert "There is no `hono/testing`" not in flat


def test_the_manifest_declares_hono_and_the_runner_the_commands_use():
    manifest = json.loads(pack_named("node-hono-api").files["package.json"].replace("{{project}}", "demo"))
    assert "hono" in manifest["dependencies"] and "@hono/node-server" in manifest["dependencies"]
    assert manifest["scripts"]["test"].startswith("jest") and "ts-jest" in manifest["devDependencies"]
