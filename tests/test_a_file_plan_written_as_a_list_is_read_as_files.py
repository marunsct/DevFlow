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


# --- the work orders made from it name the project's own files ------------------------

def _workspace(tmp_path):
    (tmp_path / ".project-directory").write_text("shop-app")
    (tmp_path / ".gitignore").write_text("node_modules/\n")
    project = tmp_path / "shop-app"
    (project / "shop_app" / "services").mkdir(parents=True)
    (project / ".gitignore").write_text(".venv/\n")
    return tmp_path


def test_a_package_named_like_the_project_and_its_own_ignore_file_are_inside_it(tmp_path):
    """Measured on one gate run: `task_management_dashboard/` read as a second project beside
    `task-management-dashboard/`, and the workspace's own `.gitignore` as the one meant."""
    from app.analysis.work_orders import inside_the_project

    root = _workspace(tmp_path)

    assert inside_the_project("shop_app/services/orders.py", root) == "shop-app/shop_app/services/orders.py"
    assert inside_the_project(".gitignore", root) == "shop-app/.gitignore"
    assert inside_the_project("src/App.tsx", root) == "shop-app/src/App.tsx"
    assert inside_the_project("shop-app/src/App.tsx", root) == "shop-app/src/App.tsx"


def test_a_file_the_harness_keeps_is_no_work_order_s_when_the_plan_names_it_from_the_project(tmp_path, monkeypatch):
    from app.graph import planned_work
    from app.stacks import contract

    root = _workspace(tmp_path)
    monkeypatch.setattr(contract, "kept_paths", lambda repo_root: frozenset({"shop-app/vite.config.ts"}))
    spec = SimpleNamespace(file_plan=["- **`vite.config.ts`** — the build.", "- **`shop_app/main.py`** — the app.",
                                      "- **`src/App.tsx`** — the page."])

    plan = planned_work.work_orders_from_the_specification(spec, "goal", ["AC-1: x"], ["npm test"], root)

    assert [f for task in plan.delegated_tasks for f in task.files] == ["shop-app/shop_app/main.py", "shop-app/src/App.tsx"]
