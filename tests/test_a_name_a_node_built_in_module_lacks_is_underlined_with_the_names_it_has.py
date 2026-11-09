"""An import of a name one of Node's own modules does not export is found, and the module's names are listed.

Measured on a small-model run: `import { promises as fs } from 'node:fs/promises'` stopped the product at start-up (the
module has no `promises`), `tsc` reported it, and the language service said nothing - it read none of Node's type
declarations, so every `node:` import was unresolved and left alone. Behind `PACKAGE_EXPORTS_NAMED`.
"""

from __future__ import annotations

import json
import shutil

import pytest

from app.analysis import language_service as service
from app.analysis.typescript_parse import compiler_for

needs_the_compiler = pytest.mark.skipif(
    shutil.which("node") is None or compiler_for(None) is None,
    reason="no TypeScript compiler beside Node here (the worker image has one)",
)

NODE_TYPES = """declare module "node:fs/promises" {
  export function readFile(path: string): Promise<string>;
  export function writeFile(path: string, data: string): Promise<void>;
  export function mkdir(path: string): Promise<void>;
}
declare module "node:path" {
  export function join(...parts: string[]): string;
}
"""


def _project(tmp_path):
    types = tmp_path / "node_modules" / "@types" / "node"
    types.mkdir(parents=True)
    (types / "package.json").write_text(json.dumps({"name": "@types/node", "version": "22.0.0", "types": "index.d.ts"}))
    (types / "index.d.ts").write_text(NODE_TYPES)
    (tmp_path / "src").mkdir()
    return tmp_path


def _findings(root, name, text):
    target = root / "src" / name
    target.write_text(text)
    found = service.underlined(root, target, text, root)
    return [] if found is None else found.here


@needs_the_compiler
def test_a_name_a_built_in_module_lacks_is_found_with_the_names_it_has(tmp_path, monkeypatch):
    monkeypatch.setenv("PACKAGE_EXPORTS_NAMED", "on")
    root = _project(tmp_path)

    found = _findings(root, "server.ts", "import { promises as fs } from 'node:fs/promises';\nexport const x = fs;\n")

    assert len(found) == 1
    assert "has no exported member 'promises'" in found[0]["message"]
    assert "`node:fs/promises` exports only: " in found[0]["message"]
    for name in ("readFile", "writeFile", "mkdir"):
        assert name in found[0]["message"]


@needs_the_compiler
def test_a_name_a_built_in_module_has_is_not_flagged(tmp_path, monkeypatch):
    monkeypatch.setenv("PACKAGE_EXPORTS_NAMED", "on")
    root = _project(tmp_path)

    found = _findings(root, "ok.ts", "import { readFile } from 'node:fs/promises';\nimport { join } from 'node:path';\n"
                                     "export const x = [readFile, join];\n")

    assert found == []


@needs_the_compiler
def test_with_the_switch_off_built_in_modules_are_left_alone(tmp_path, monkeypatch):
    monkeypatch.setenv("PACKAGE_EXPORTS_NAMED", "off")
    root = _project(tmp_path)

    found = _findings(root, "server.ts", "import { promises as fs } from 'node:fs/promises';\nexport const x = fs;\n")

    assert found == []
