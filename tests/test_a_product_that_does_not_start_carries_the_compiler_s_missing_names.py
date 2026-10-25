"""A product that does not start is reported with every name the compiler cannot find, not the runtime's first crash alone.

Measured on three small-model runs of a TypeScript service: the product did not start for the first half hour, and each
fixer saw the one crash the runtime printed (a package path Hono does not export, a name `node:fs/promises` lacks, a
mistyped host), a fix and a round apart, while the compiler listed them all in the first round. Behind
`START_DEFECT_NAMES_COMPILER_ERRORS`; a pack names its `typecheck` command.
"""
from __future__ import annotations

import re

import pytest

from app.stacks import compiler_errors, contract, pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

OUTPUT = """src/routes/notes.ts(25,14): error TS2339: Property 'is' does not exist on type 'HonoRequest<any, unknown>'.
src/server.ts(6,10): error TS2305: Module '"node:fs/promises"' has no exported member 'promises'.
src/middleware/errorHandler.ts(6,39): error TS7006: Parameter 'c' implicitly has an 'any' type.
test/handlers.test.ts(24,23): error TS18046: 'client' is of type 'unknown'.
test/handlers.test.ts(3,24): error TS2305: Module '"node:test"' has no exported member 'expect'.
node_modules/foo/index.d.ts(1,1): error TS2304: Cannot find name 'x'.
"""


def test_only_the_errors_that_name_something_missing_are_kept():
    kept = compiler_errors.parse(OUTPUT)
    assert [(f, line) for f, line, _c, _m in kept] == [("src/routes/notes.ts", 25), ("src/server.ts", 6), ("test/handlers.test.ts", 3)]


@pytest.fixture()
def project(tmp_path):
    pack = pack_named("node-hono-native-api")
    contract.write(tmp_path, pack, "notes", "Notes")
    (tmp_path / "notes" / "src").mkdir(parents=True)
    return tmp_path


def test_the_native_pack_names_its_typecheck_command():
    assert pack_named("node-hono-native-api").typecheck == ("npm", "run", "typecheck")
    assert pack_named("node-hono-api").typecheck == ()


def test_the_errors_are_added_when_the_switch_is_on(project, monkeypatch):
    monkeypatch.setenv("START_DEFECT_NAMES_COMPILER_ERRORS", "on")
    asked = []

    def runner(argv, category, working_directory):
        asked.append((list(argv), working_directory))
        return {"stdout": OUTPUT, "stderr": "", "returncode": 2}

    text = compiler_errors.the_errors(project, runner)

    assert asked == [(["npm", "run", "typecheck"], "notes")]
    assert "notes/src/server.ts line 6: Module '\"node:fs/promises\"' has no exported member 'promises'" in text
    assert "notes/src/routes/notes.ts line 25" in text and "implicitly" not in text
    assert not BANNED.search(text)


def test_nothing_is_added_when_off_or_the_compiler_is_clean_or_cannot_run(project, monkeypatch):
    monkeypatch.setenv("START_DEFECT_NAMES_COMPILER_ERRORS", "off")
    assert compiler_errors.the_errors(project, lambda *a: {"stdout": OUTPUT}) == ""
    monkeypatch.setenv("START_DEFECT_NAMES_COMPILER_ERRORS", "on")
    assert compiler_errors.the_errors(project, lambda *a: {"stdout": ""}) == ""

    def broken(*a):
        raise RuntimeError("no sandbox")

    assert compiler_errors.the_errors(project, broken) == ""


def test_a_pack_with_no_typecheck_adds_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("START_DEFECT_NAMES_COMPILER_ERRORS", "on")
    contract.write(tmp_path, pack_named("node-hono-api"), "notes", "Notes")
    assert compiler_errors.the_errors(tmp_path, lambda *a: {"stdout": OUTPUT}) == ""


def test_the_start_defect_carries_the_errors(project, monkeypatch):
    from types import SimpleNamespace

    from app.acceptance import suite
    from app.graph import acceptance_nodes

    monkeypatch.setenv("START_DEFECT_NAMES_COMPILER_ERRORS", "on")
    saved = {"ran": True, "problem": suite.the_product_did_not_start(
        "Error: Process from config.webServer was not able to start. Exit code: 1"), "runtime_problems": []}
    monkeypatch.setattr(acceptance_nodes, "_failing_due", lambda state: ([{"id": "AC-1", "text": "x", "tests": []}], "npm run test:acceptance"))
    monkeypatch.setattr(suite, "last_result", lambda root: saved)
    monkeypatch.setattr(acceptance_nodes, "_root", lambda state: str(project))
    monkeypatch.setattr(acceptance_nodes, "_stack", lambda state: SimpleNamespace(product_kind="http_api"))
    monkeypatch.setattr(compiler_errors, "the_errors", lambda root, runner=None: "\n\nThe compiler also reports: X")

    defects = acceptance_nodes.failing_due_defects({}, [])

    assert defects and "The compiler also reports: X" in defects[0].actual_behavior


def test_a_package_path_the_package_does_not_export_comes_back_with_the_paths_it_does(project, monkeypatch):
    import json

    monkeypatch.setenv("START_DEFECT_NAMES_COMPILER_ERRORS", "on")
    monkeypatch.setenv("PACKAGE_EXPORTS_NAMED", "on")
    package = project / "notes" / "node_modules" / "hono"
    package.mkdir(parents=True)
    (package / "package.json").write_text(json.dumps({"name": "hono", "exports": {
        ".": "./dist/index.js", "./cors": "./dist/cors.js", "./body-limit": "./dist/body-limit.js"}}))
    (project / "notes" / "src" / "app.ts").write_text("import { bodyLimit } from 'hono/middleware';\n")

    def runner(argv, category, working_directory):
        return {"stdout": "src/app.ts(1,26): error TS2307: Cannot find module 'hono/middleware' or its corresponding "
                          "type declarations.\n"}

    text = compiler_errors.the_errors(project, runner)

    assert "hono/body-limit" in text and "hono/cors" in text


def test_a_value_of_the_wrong_kind_is_kept_and_the_product_s_files_come_first():
    output = (
        "test/app.test.ts(3,5): error TS2345: Argument of type 'x' is not assignable to parameter of type 'y'.\n"
        "src/app.ts(25,3): error TS2769: No overload matches this call.\n"
        "src/app.ts(7,1): error TS7006: Parameter 'c' implicitly has an 'any' type.\n"
    )
    kept = compiler_errors.parse(output)
    assert [(f, c) for f, _l, c, _m in kept] == [("src/app.ts", 2769), ("test/app.test.ts", 2345)]


def test_the_native_pack_keeps_its_tsconfig(tmp_path):
    pack = pack_named("node-hono-native-api")
    assert "tsconfig.json" in pack.kept_files
    contract.write(tmp_path, pack, "notes", "Notes")
    project = tmp_path / "notes"
    project.mkdir(exist_ok=True)
    (project / "tsconfig.json").write_text('{"compilerOptions": {"module": "esnext", "moduleResolution": "nodenext"}}')

    contract.enforce(tmp_path)

    assert '"module": "nodenext"' in (project / "tsconfig.json").read_text()
