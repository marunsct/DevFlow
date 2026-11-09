"""A TypeScript file that Node runs as it is is parsed by Node too, not only by the compiler's parser.

Measured on a small-model run of the pack that Node runs itself: a rewrite declared `const body` twice in one handler,
the compiler's parser passed it, and the service did not start - two fixes reverted in a row for it.
"""
from __future__ import annotations

import shutil

import pytest

from app.analysis import javascript_parse
from app.stacks import contract, pack_named

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs Node")

TWICE = """import { Hono } from 'hono';
interface Note { title: string }
export const app = new Hono();
app.post('/notes', async (c) => {
  const body = await c.req.json();
  const body = (await c.req.json()) as Note;
  return c.json(body, 201);
});
"""
RIGHT = """import { Hono } from 'hono';
import type { Context } from 'hono';
interface Note { title: string }
export const app = new Hono();
app.post('/notes', async (c: Context) => {
  const body = (await c.req.json()) as Note;
  return c.json(body, 201);
});
"""


def _file(tmp_path, pack_name):
    contract.write(tmp_path, pack_named(pack_name), "notes", "Notes")
    target = tmp_path / "notes" / "src" / "app.ts"
    target.parent.mkdir(parents=True)
    (tmp_path / "notes" / "package.json").write_text('{"type": "module"}\n')
    return target


def test_a_name_declared_twice_is_refused_where_node_runs_the_file(tmp_path):
    found = javascript_parse.parse_error(_file(tmp_path, "node-hono-native-api"), TWICE)
    assert found and "has already been declared" in found and "line 6" in found


def test_correct_typescript_with_types_passes(tmp_path):
    assert javascript_parse.parse_error(_file(tmp_path, "node-hono-native-api"), RIGHT) is None


def test_a_pack_that_compiles_its_typescript_is_left_to_the_compiler_s_parser(tmp_path):
    assert javascript_parse.parse_error(_file(tmp_path, "node-hono-api"), TWICE) is None


def test_syntax_node_cannot_strip_is_named(tmp_path):
    found = javascript_parse.parse_error(_file(tmp_path, "node-hono-native-api"), "export enum Kind { A, B }\n")
    assert found and "Node cannot load this file" in found
