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


def test_a_model_can_look_before_it_writes_with_the_module_exports_tool(tmp_path):
    _hono(tmp_path)
    tools = package_exports.exports_tools(tmp_path)
    assert [t.name for t in tools] == ["module_exports"]

    answered = tools[0].invoke({"module": "hono/testing"})

    assert answered["exports"] == ["testClient"] and "Only these names exist" in answered["note"]
    assert "error" in tools[0].invoke({"module": "nothing-installed"})
    assert "error" in tools[0].invoke({"module": "./local"})


def test_the_tool_is_offered_to_a_specialist_and_not_when_the_switch_is_off(tmp_path, monkeypatch):
    from app.agents import specialists

    assert "exports_tools" in vars(specialists)
    monkeypatch.setenv("PACKAGE_EXPORTS_NAMED", "off")
    assert package_exports.exports_tools(tmp_path) == []


def _hono_with_paths(project: Path) -> None:
    package = project / "node_modules" / "hono"
    package.mkdir(parents=True, exist_ok=True)
    (package / "package.json").write_text(json.dumps({"name": "hono", "exports": {
        ".": {"types": "./a.d.ts"}, "./cors": {"types": "./b.d.ts"}, "./body-limit": {"types": "./c.d.ts"},
        "./package.json": "./package.json"}}))


def test_a_path_a_package_does_not_export_comes_back_with_the_paths_it_does(tmp_path):
    """`import ... from 'hono/middleware'`: Hono exports no such path; the compiler said only "cannot find module"."""
    _hono_with_paths(tmp_path)
    assert package_exports.package_paths(tmp_path, "hono/middleware") == ["hono", "hono/body-limit", "hono/cors"]
    assert package_exports.package_paths(tmp_path, "hono/cors") is None  # a path it exports
    assert package_exports.package_paths(tmp_path, "nothing-installed/x") is None
    assert package_exports.package_paths(tmp_path, "./local") is None


def test_the_finding_for_a_missing_path_names_the_paths(tmp_path):
    _hono_with_paths(tmp_path)
    importer = tmp_path / "src" / "app.ts"
    importer.parent.mkdir()
    finding = {"message": "Cannot find module 'hono/middleware' or its corresponding type declarations.",
               "text": "import { bodyLimit } from 'hono/middleware';"}

    said = language_service.the_names_the_module_has(tmp_path, importer, finding)

    assert "`hono/middleware` is not a path that package exports" in said and "hono/body-limit, hono/cors" in said


def test_the_defect_for_a_missing_path_carries_the_paths(tmp_path, monkeypatch):
    from types import SimpleNamespace

    _hono_with_paths(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.ts").write_text("import { bodyLimit } from 'hono/middleware';\n")
    finding = {"line": 1, "message": "Cannot find module 'hono/middleware' or its corresponding type declarations.",
               "text": "import { bodyLimit } from 'hono/middleware';"}
    monkeypatch.setattr("app.graph.engineering.ci.changed_since", lambda root, since: ["src/app.ts"])
    monkeypatch.setattr("app.analysis.language_service.underlined_in", lambda root, files, project, most: {"src/app.ts": [finding]})
    monkeypatch.setattr(engineering, "_what_the_compiler_says", lambda *a, **k: [])
    monkeypatch.setattr(engineering, "_owner_of", lambda state, text: "backend")

    defects = engineering.underlined_in_the_batch(SimpleNamespace(), str(tmp_path), "abc")

    assert any("hono/body-limit, hono/cors" in d.expected_behavior for d in defects)
