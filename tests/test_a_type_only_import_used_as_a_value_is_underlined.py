"""A class imported with `import type` and then constructed is underlined: types are stripped, so it is not defined.

Measured on one run: a fixer wrote `import type { NoteStore } from './services/noteStore.ts'` and
`new NoteStore(dataDir)` in the product's `createApp`. Node strips the import with the types, and the
product died at start with `ReferenceError: NoteStore is not defined`. The write was not refused, so
four fixes in a row were each made, measured and reverted.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.analysis import language_service as service
from app.analysis.typescript_parse import compiler_for

needs_the_compiler = pytest.mark.skipif(
    shutil.which("node") is None or compiler_for(None) is None,
    reason="no TypeScript compiler beside Node here (the worker image has one)",
)


@needs_the_compiler
def test_a_class_imported_as_a_type_and_constructed_is_underlined(tmp_path: Path) -> None:
    project = tmp_path / "app"
    (project / "src").mkdir(parents=True)
    (project / "src" / "store.ts").write_text("export class Store { constructor(public dir: string) {} }\n")
    content = ("import type { Store } from './store.ts';\n"
               "export function createApp(): Store { return new Store('data'); }\n")

    found = service.underlined_any(tmp_path, project / "src" / "app.ts", content, project)

    assert [f["code"] for f in found.here] == [1361]


@needs_the_compiler
def test_a_type_import_used_only_as_a_type_is_left_alone(tmp_path: Path) -> None:
    project = tmp_path / "app"
    (project / "src").mkdir(parents=True)
    (project / "src" / "store.ts").write_text("export class Store { constructor(public dir: string) {} }\n")
    content = "import type { Store } from './store.ts';\nexport function keep(s: Store): Store { return s; }\n"

    assert service.underlined_any(tmp_path, project / "src" / "app.ts", content, project).here == []
