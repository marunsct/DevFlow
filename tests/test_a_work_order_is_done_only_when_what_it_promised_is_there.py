"""A drafted work order is done when its files define what it promised, not merely when they were written.

Measured on one run: a work order to add a SQLite store listed `export function makePersistence(...)` and
`export interface Persistence` among its interfaces. Files are drafted from the specification, which described only the
JSON store, so `store.ts` came out as it was. Every file wrote without error, the work order was recorded as done, and
the feature was never built; a reviewer found it later.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from app.agents.technical_lead import SpecialistTask
from app.graph import drafting

SPEC = SimpleNamespace(
    product_scope="Notes.",
    file_plan=["notes/src/store.ts - keeps notes"],
    function_contracts=["notes/src/store.ts loadNotes(dir): Note[]"],
    library_usage=[],
)


class _Model:
    def __init__(self, reply: str):
        self.reply = reply

    def invoke(self, messages, **kwargs):
        return SimpleNamespace(content=f"```ts\n{self.reply}\n```")


def _write(root: str, path: str, content: str) -> None:
    target = Path(root) / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _order(interfaces: list[str]):
    return SpecialistTask(specialist_role="backend", task_description="Add a SQLite store behind the store seam.",
                          acceptance_criteria=["works"], files=["notes/src/store.ts"], interfaces=interfaces)


PROMISES = ["store.ts new exports: export interface Persistence { list(): Note[] }",
            "store.ts new export: export function makePersistence(dataDir: string): Persistence"]


def test_the_names_a_work_order_promises_are_read_from_its_interfaces():
    assert drafting.promised_names(_order(PROMISES)) == ["Persistence", "makePersistence"]
    assert drafting.promised_names(_order(["def make_store(path) -> Store", "class Store"])) == ["make_store", "Store"]
    assert drafting.promised_names(_order(["Import from '../src/store.js': makePersistence"])) == []


def test_a_file_that_only_mentions_a_name_does_not_define_it():
    texts = {"a.ts": "import { makePersistence } from './x.js';\nconst s = makePersistence('d');"}

    assert drafting.not_defined_in(["makePersistence"], texts) == ["makePersistence"]
    assert drafting.not_defined_in(["makePersistence"], {"a.ts": "export function makePersistence(d: string) {}"}) == []
    assert drafting.not_defined_in(["Persistence"], {"a.ts": "export interface Persistence { list(): Note[] }"}) == []


def test_a_work_order_whose_file_came_out_without_what_it_promised_is_left_to_the_agent_loop(tmp_path):
    model = _Model("export function loadNotes(dir: string) { return []; }")

    drafted = drafting.draft_work_orders([_order(PROMISES)], SPEC, None, str(tmp_path), model, write=_write)

    assert drafted == {}


def test_a_work_order_whose_file_defines_what_it_promised_is_done(tmp_path):
    model = _Model("export interface Persistence { list(): Note[] }\nexport function makePersistence(d: string): Persistence { return null as any; }")

    drafted = drafting.draft_work_orders([_order(PROMISES)], SPEC, None, str(tmp_path), model, write=_write)

    assert list(drafted) == [0] and drafted[0].changed_files == ["notes/src/store.ts"]


def test_a_work_order_that_names_nothing_is_done_as_before(tmp_path):
    model = _Model("export function loadNotes(dir: string) { return []; }")

    drafted = drafting.draft_work_orders([_order(["Reads notes from DATA_DIR"])], SPEC, None, str(tmp_path), model, write=_write)

    assert list(drafted) == [0]
