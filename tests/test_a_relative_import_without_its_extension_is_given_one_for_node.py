"""A relative import names the file Node will load: the harness adds the `.ts` the model leaves off.

Measured on the first run of the pack that Node runs itself: its guide says to name the extension, the model wrote
`./middleware/bodyLimit` anyway, and the service answered ERR_MODULE_NOT_FOUND for three rounds.
"""
from __future__ import annotations

from app.stacks import contract, import_extensions, pack_named


def _project(tmp_path):
    root = tmp_path / "notes"
    for folder in ("src/middleware", "src/routes", "src/store", "test"):
        (root / folder).mkdir(parents=True)
    (root / "src" / "middleware" / "bodyLimit.ts").write_text("export const bodyLimit = 1;\n")
    (root / "src" / "routes" / "notes.ts").write_text("export const notes = 1;\n")
    (root / "src" / "store" / "index.ts").write_text("export const store = 1;\n")
    return root


def test_an_extensionless_import_of_a_file_that_exists_gets_its_extension(tmp_path):
    root = _project(tmp_path)
    app = root / "src" / "app.ts"
    app.write_text(
        "import { bodyLimit } from './middleware/bodyLimit';\n"
        "import { notes } from \"./routes/notes\";\n"
        "import { store } from './store';\n"
        "export * from './routes/notes';\n"
        "const lazy = await import('./routes/notes');\n"
    )

    said = import_extensions.put_the_extensions_on(root)

    assert said and "5 relative import(s) in 1 file(s)" in said[0]
    assert app.read_text() == (
        "import { bodyLimit } from './middleware/bodyLimit.ts';\n"
        "import { notes } from \"./routes/notes.ts\";\n"
        "import { store } from './store/index.ts';\n"
        "export * from './routes/notes.ts';\n"
        "const lazy = await import('./routes/notes.ts');\n"
    )


def test_a_js_import_whose_ts_file_exists_is_rewritten_because_that_is_what_node_loads(tmp_path):
    root = _project(tmp_path)
    (root / "src" / "app.ts").write_text("import { notes } from './routes/notes.js';\n")
    import_extensions.put_the_extensions_on(root)
    assert (root / "src" / "app.ts").read_text() == "import { notes } from './routes/notes.ts';\n"


def test_tests_are_rewritten_too_and_packages_and_unresolved_imports_are_left_alone(tmp_path):
    root = _project(tmp_path)
    spec = root / "test" / "a.test.ts"
    spec.write_text("import { test } from 'node:test';\nimport { Hono } from 'hono';\nimport { x } from './missing';\n"
                    "import { bodyLimit } from '../src/middleware/bodyLimit';\nimport data from './d.json';\n")
    import_extensions.put_the_extensions_on(root)
    assert spec.read_text() == ("import { test } from 'node:test';\nimport { Hono } from 'hono';\nimport { x } from './missing';\n"
                                "import { bodyLimit } from '../src/middleware/bodyLimit.ts';\nimport data from './d.json';\n")


def test_it_is_idempotent_and_says_nothing_when_there_is_nothing_to_do(tmp_path):
    root = _project(tmp_path)
    (root / "src" / "app.ts").write_text("import { notes } from './routes/notes';\n")
    assert import_extensions.put_the_extensions_on(root)
    assert import_extensions.put_the_extensions_on(root) == []
    assert import_extensions.put_the_extensions_on(tmp_path / "nowhere") == []


def test_the_contract_repair_runs_it_for_the_pack_that_node_runs_itself_and_no_other(tmp_path):
    pack = pack_named("node-hono-native-api")
    assert pack.relative_import_extension == ".ts"
    assert pack_named("node-hono-api").relative_import_extension == ""
    contract.write(tmp_path, pack, "notes", "Notes")
    root = _project(tmp_path)
    for relative, text in pack.render("notes", "Notes", None).items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    (root / "src" / "extra.ts").write_text("import { notes } from './routes/notes';\n")

    repairs = contract.enforce(tmp_path)

    assert any("now name the `.ts` file they mean" in line for line in repairs)
    assert (root / "src" / "extra.ts").read_text() == "import { notes } from './routes/notes.ts';\n"
