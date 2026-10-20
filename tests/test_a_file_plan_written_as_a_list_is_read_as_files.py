"""A file plan written as a markdown list, with files nested under their directory, is read as its files.

Measured on one gate run: every entry was a list item (``- **`path`** - ...``)
and the files of three directories were bare names indented under them. The
plan read as its five headings, the work orders the harness made from it held
none of the product's files, and the lead was sent back three times for
services nobody was given.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.graph.drafting import planned_files

LISTED = [
    "Project configuration",
    "- **`package.json`** — the manifest.",
    "- **`Dockerfile`** — the service image.",
    "Service source",
    "- **`shop/main.py`** — the application.",
    "- **`shop/services/`** — business logic.\n  - **`__init__.py`** — exports.",
    "  - **`orders.py`** — `place(order)`.",
    "  - **`stock.py`** — `reserve(item)`.",
    "Service tests",
    "- **`tests/unit/test_orders.py`** — order cases.",
]


def test_list_items_and_nested_names_are_read_as_paths():
    assert planned_files(SimpleNamespace(file_plan=LISTED)) == [
        "package.json", "Dockerfile", "shop/main.py", "shop/services/__init__.py",
        "shop/services/orders.py", "shop/services/stock.py", "tests/unit/test_orders.py",
    ]


def test_the_plain_forms_read_as_before():
    plan = ["notes/src/app.ts - routes", "notes/src/store.ts: the store", "1. `notes/README.md` the guide"]

    assert planned_files(SimpleNamespace(file_plan=plan)) == [
        "notes/src/app.ts", "notes/src/store.ts", "notes/README.md",
    ]


def test_a_heading_ends_the_directory_above_it():
    plan = ["- `web/components/`", "  - `Card.tsx`", "Tests", "  - `tests/Card.test.tsx`"]

    assert planned_files(SimpleNamespace(file_plan=plan)) == ["web/components/Card.tsx", "tests/Card.test.tsx"]
