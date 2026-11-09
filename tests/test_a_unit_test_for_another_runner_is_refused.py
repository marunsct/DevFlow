"""A unit test that imports a framework the project's kept unit command does not run is refused at the write.

Measured on one run: the pack's kept `test` script runs `node --test`; the drafter wrote two unit test files importing
from `vitest`, and both crashed with "Vitest failed to access its internal state".
"""
from __future__ import annotations

import re

import pytest

from app.stacks import contract, pack_named
from app.tools.repository import RepositoryToolError, _refuse_a_test_for_another_runner

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
VITEST = "import { describe, it, expect } from 'vitest';\ndescribe('notes', () => { it('works', () => expect(1).toBe(1)); });\n"
NODE = "import { test } from 'node:test';\nimport assert from 'node:assert/strict';\ntest('works', () => assert.equal(1, 1));\n"


def _project(tmp_path, pack):
    contract.write(tmp_path, pack_named(pack), "notes", "Notes")
    (tmp_path / "notes" / "test").mkdir(parents=True)
    return tmp_path / "notes" / "test" / "notes.test.ts"


def test_a_vitest_import_under_node_s_runner_is_refused_with_the_correction(tmp_path):
    target = _project(tmp_path, "node-hono-native-api")
    with pytest.raises(RepositoryToolError) as refused:
        _refuse_a_test_for_another_runner(target, "notes/test/notes.test.ts", VITEST)
    said = str(refused.value)
    assert "'vitest'" in said and "node --test" in said and "import { test, describe } from 'node:test'" in said
    assert not BANNED.search(said)


def test_node_s_own_runner_and_a_product_file_are_left(tmp_path):
    target = _project(tmp_path, "node-hono-native-api")
    _refuse_a_test_for_another_runner(target, "notes/test/notes.test.ts", NODE)
    _refuse_a_test_for_another_runner(tmp_path / "notes" / "src" / "app.ts", "notes/src/app.ts", "import { x } from 'vitest';\n")


def test_a_pack_whose_unit_command_is_not_node_s_runner_is_not_checked(tmp_path):
    contract.write(tmp_path, pack_named("browser-react"), "web", "Web")
    (tmp_path / "web" / "src").mkdir(parents=True)
    _refuse_a_test_for_another_runner(tmp_path / "web" / "src" / "App.test.tsx", "web/src/App.test.tsx", VITEST)
