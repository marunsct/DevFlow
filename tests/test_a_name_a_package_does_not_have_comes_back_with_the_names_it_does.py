"""An import of a name a package does not export is answered with what the package really exports.

Measured over one night: a small model imported `createClient` and `createTestClient` from `hono/testing`, which
exports one name, `testClient`. The compiler said which name was missing and not which exist, so each rewrite guessed
again and four runs ended with a product that did not build. The package's own type file says what it exports.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.analysis import language_service, package_exports
from app.graph import engineering


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("PACKAGE_EXPORTS_NAMED", "on")


def _hono(project: Path) -> None:
    package = project / "node_modules" / "hono"
    (package / "dist" / "types" / "helper" / "testing").mkdir(parents=True)
    (package / "package.json").write_text(json.dumps({
        "name": "hono", "types": "dist/types/index.d.ts",
        "exports": {".": {"types": "./dist/types/index.d.ts"},
                    "./testing": {"types": "./dist/types/helper/testing/index.d.ts", "import": "./dist/x.js"}},
    }))
    (package / "dist" / "types" / "helper" / "testing" / "index.d.ts").write_text(
        'import { Hono } from "../../hono.js";\n//#region x\nexport declare const testClient: <T>(app: T) => unknown;\n')
    (package / "dist" / "types" / "index.d.ts").write_text(
        'import { Hono } from "./hono.js";\nexport { type Env, Context, Hono as Hono, type Next };\n'
        'export * from "./more.js";\n')
    (package / "dist" / "types" / "more.d.ts").write_text("export declare function cors(): void;\nexport interface Extra {}\n")


def test_a_subpath_of_a_package_lists_its_real_exports(tmp_path):
    _hono(tmp_path)
    assert package_exports.script_package_exports(tmp_path, "hono/testing") == ["testClient"]


def test_the_root_follows_a_listed_export_and_a_star_re_export(tmp_path):
    _hono(tmp_path)
    names = package_exports.script_package_exports(tmp_path, "hono")
    assert {"Hono", "Context", "Env", "Next", "cors", "Extra"} <= set(names)


def test_a_package_that_is_not_installed_or_a_relative_import_says_nothing(tmp_path):
    assert package_exports.script_package_exports(tmp_path, "hono/testing") is None
    assert package_exports.script_package_exports(tmp_path, "./local") is None
    assert package_exports.script_package_exports(tmp_path, "node:fs") is None


def test_a_python_package_lists_its_top_level_names(tmp_path):
    site = tmp_path / ".venv" / "lib" / "python3.12" / "site-packages" / "fakejwt"
    site.mkdir(parents=True)
    (site / "__init__.py").write_text("from .api import encode, decode as _d\nclass PyJWTError(Exception): ...\nDEFAULT = 1\n_private = 2\n")
    names = package_exports.python_package_exports(tmp_path, "fakejwt")
    assert names == ["DEFAULT", "PyJWTError", "encode"]


def test_a_finding_about_a_missing_name_names_the_package_and_what_it_exports(tmp_path):
    _hono(tmp_path)
    importer = tmp_path / "test" / "errors.spec.ts"
    importer.parent.mkdir()
    importer.write_text("import { createClient } from 'hono/testing';\n")
    finding = {"message": "Module '\"hono/testing\"' has no exported member 'createClient'.",
               "text": "import { createClient } from 'hono/testing';"}

    said = language_service.the_names_the_module_has(tmp_path, importer, finding)

    assert "`hono/testing` is a package; it exports only: testClient" in said


def test_the_defect_for_such_an_import_does_not_ask_for_a_name_to_be_added_to_the_package(tmp_path):
    _hono(tmp_path)
    importer = tmp_path / "test" / "errors.spec.ts"
    importer.parent.mkdir()
    findings = {"test/errors.spec.ts": [{
        "line": 2, "message": "Module '\"hono/testing\"' has no exported member 'createClient'.",
        "text": "import { createClient } from 'hono/testing';"}]}

    seen = engineering._names_their_modules_lack(str(tmp_path), tmp_path, findings)

    module, defined, importers = seen[("test/errors.spec.ts", findings["test/errors.spec.ts"][0]["message"])]
    assert module == "hono/testing" and defined == ["testClient"] and importers == []


def test_off_it_says_nothing(tmp_path, monkeypatch):
    _hono(tmp_path)
    monkeypatch.setenv("PACKAGE_EXPORTS_NAMED", "off")
    assert package_exports.script_package_exports(tmp_path, "hono/testing") is None
