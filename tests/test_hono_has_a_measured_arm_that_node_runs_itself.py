"""Hono has a second pack, a measured arm that Node runs itself: no compile step, no Jest, no ts-jest.

Five runs of a small model on the Jest pack ended with a product that did not build; ts-jest, a build step and Jest's
configuration were each a way to fail beyond the model's own code. Node 24 strips the types and runs the file, so the arm
starts with `node src/main.ts`, tests with `node:test`, and uses `tsc --noEmit` only as a check. It is off until its runs
are compared with the Jest pack's.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.stacks import choose_pack, pack_named


def _stack():
    return SimpleNamespace(language="TypeScript", framework="Hono", frontend_framework="", database="JSON file",
                           testing_framework="node:test", product_kind="http_api")


def test_the_jest_pack_is_chosen_while_the_arm_is_off(monkeypatch):
    monkeypatch.delenv("HONO_NATIVE_TEST_RUNNER", raising=False)
    assert choose_pack(_stack(), "A small HTTP service API").name == "node-hono-api"


def test_the_native_pack_is_chosen_when_the_arm_is_on(monkeypatch):
    monkeypatch.setenv("HONO_NATIVE_TEST_RUNNER", "on")
    assert choose_pack(_stack(), "A small HTTP service API").name == "node-hono-native-api"


def test_an_arm_on_does_not_change_another_framework_s_pack(monkeypatch):
    monkeypatch.setenv("HONO_NATIVE_TEST_RUNNER", "on")
    nest = SimpleNamespace(language="TypeScript", framework="NestJS 11", frontend_framework="", database="x",
                           testing_framework="x", product_kind="http_api")
    assert choose_pack(nest, "A small HTTP service API").name == "node-nest-api"


def test_the_native_pack_has_no_build_step_no_jest_and_runs_the_file_it_is_given():
    pack = pack_named("node-hono-native-api")
    manifest = json.loads(pack.files["package.json"].replace("{{project}}", "demo"))
    assert manifest["scripts"]["start"] == "node src/main.ts" and "build" not in manifest["scripts"]
    assert "node --test" in manifest["scripts"]["test"] and "jest" not in json.dumps(manifest)
    assert "ts-jest" not in json.dumps(manifest)
    assert manifest["scripts"]["typecheck"] == "tsc --noEmit"
    tsconfig = pack.files["tsconfig.json"]
    assert '"noEmit": true' in tsconfig and '"erasableSyntaxOnly": true' in tsconfig


def test_its_files_import_each_other_with_the_extension_node_needs():
    pack = pack_named("node-hono-native-api")
    assert "from './app.ts'" in pack.files["src/main.ts"]
    assert "from '../src/app.ts'" in pack.smoke_files["test/scaffold-smoke.test.ts"]


def test_its_guide_names_the_limits_of_the_syntax_and_the_tools_to_use():
    guide = pack_named("node-hono-native-api").guide
    for phrase in ("NOT `enum`", "parameter properties", "'./x.ts'", "npm run typecheck", "module_exports", "exports only `testClient`"):
        assert phrase in guide, phrase


def test_it_keeps_the_export_its_scaffold_depends_on():
    assert pack_named("node-hono-native-api").required_exports == {"src/app.ts": ("createApp",)}
