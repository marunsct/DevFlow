"""A finding about a name a module does not have says which names it does have, for TypeScript and JavaScript as well as Python.

Measured over one night with a small model: `create_access_token` imported from a module that defined `create_token`,
`createApp` imported by seven test files from a module that exported `app`. The compiler says which name is missing and
not which exist, so each writer guessed again. Python already had this at the gate; TypeScript and JavaScript had none,
and neither the drafting repair nor a stage's exit check carried it.
"""
from __future__ import annotations

from pathlib import Path

from app.analysis import language_service
from app.graph import engineering


def _project(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "test").mkdir()
    (tmp_path / "src" / "app.ts").write_text(
        "import { Hono } from 'hono';\n"
        "export interface Options { x: number }\n"
        "export const app = new Hono();\n"
        "export function buildThing(): number { return 1 }\n"
        "export { helper as publicHelper, other };\n"
        "export default app;\n"
    )
    (tmp_path / "test" / "app.spec.ts").write_text("import { createApp } from '../src/app';\n")
    return tmp_path


TS_FINDING = {"line": 1, "message": "Module '\"../src/app\"' has no exported member 'createApp'.",
              "text": "import { createApp } from '../src/app';"}


def test_a_typescript_module_says_what_it_exports(tmp_path):
    root = _project(tmp_path)

    found = language_service.what_the_module_defines(root, root / "test" / "app.spec.ts", TS_FINDING["text"])

    assert found is not None and found[0].name == "app.ts"
    assert found[1] == ["Options", "app", "buildThing", "default", "other", "publicHelper"]


def test_a_dot_js_specifier_finds_the_dot_ts_file(tmp_path):
    root = _project(tmp_path)

    found = language_service.what_the_module_defines(root, root / "test" / "app.spec.ts", "import { x } from '../src/app.js';")

    assert found is not None and found[0].name == "app.ts"


def test_a_package_import_is_left_alone(tmp_path):
    root = _project(tmp_path)

    assert language_service.what_the_module_defines(root, root / "test" / "app.spec.ts", "import { Hono } from 'hono';") is None


def test_the_note_names_the_names_the_module_has(tmp_path):
    root = _project(tmp_path)

    note = language_service.the_names_the_module_has(root, root / "test" / "app.spec.ts", TS_FINDING)

    assert note.startswith(" `src/app.ts` defines:") and "app" in note and "createApp" not in note


def test_the_python_wording_is_answered_too(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "auth.py").write_text("def create_token(): ...\ndef decode_token(): ...\n")
    (tmp_path / "pkg" / "routes.py").write_text("from .auth import create_access_token\n")
    finding = {"message": '"create_access_token" is unknown import symbol', "text": "from .auth import create_access_token"}

    note = language_service.the_names_the_module_has(tmp_path, tmp_path / "pkg" / "routes.py", finding)

    assert "`pkg/auth.py` defines: create_token, decode_token" in note


def test_a_finding_that_is_not_about_a_name_gets_no_note(tmp_path):
    root = _project(tmp_path)

    assert language_service.the_names_the_module_has(
        root, root / "test" / "app.spec.ts", {"message": "Type 'string' is not assignable to type 'number'.", "text": TS_FINDING["text"]}
    ) == ""


def test_the_gate_bundles_a_typescript_name_with_its_module(tmp_path):
    root = _project(tmp_path)
    (root / "test" / "other.spec.ts").write_text("import { createApp } from '../src/app';\n")
    findings = {
        "test/app.spec.ts": [dict(TS_FINDING)],
        "test/other.spec.ts": [dict(TS_FINDING)],
    }

    missing = engineering._names_their_modules_lack(str(root), root, findings)

    module, defined, importers = missing[("test/app.spec.ts", TS_FINDING["message"])]
    assert module == "src/app.ts" and "app" in defined
    assert sorted(importers) == ["test/app.spec.ts", "test/other.spec.ts"]
