"""The project directory the plan names is pinned before any specialist writes.

It was pinned by the first file written. In parallel mode several specialists
start before anything exists; one run's lead named `simple-to-do-list-app/`,
and `specialist_ui_ux_0`, whose task said only "Write index.html", wrote
`task-manager/index.html` and was refused.
"""

from __future__ import annotations

from pathlib import Path

from app.agents.workspace_digest import render_workspace_digest
from app.tools.repository import pin_the_directory_a_plan_names, pinned_project_directory

#: Shaped like the measured plan: the directory twice, `test/` ten times.
PLAN = (
    "Write unit tests (test/app.test.mjs) ... test/e2e/todo.spec.ts ... "
    "test/ test/ test/ test/ test/ test/ test/ test/ "
    "handles empty/whitespace titles ... "
    "The project directory 'simple-to-do-list-app/' does not yet exist. "
    "Put index.html in simple-to-do-list-app/."
)


def _workspace(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "sprint_plan.md").write_text("# Plan\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("node_modules\n", encoding="utf-8")
    return tmp_path


class TestPinning:
    def test_the_named_directory_is_pinned(self, tmp_path):
        root = _workspace(tmp_path)

        assert pin_the_directory_a_plan_names(root, PLAN) == "simple-to-do-list-app"
        assert pinned_project_directory(root) == "simple-to-do-list-app"

    def test_a_subfolder_is_never_the_project(self, tmp_path):
        root = _workspace(tmp_path)

        assert pin_the_directory_a_plan_names(root, "test/a test/b e2e-tests/c e2e-tests/d") is None

    def test_one_mention_is_not_enough(self, tmp_path):
        root = _workspace(tmp_path)

        assert pin_the_directory_a_plan_names(root, "see my-app/index.html") is None

    def test_an_existing_pin_is_kept(self, tmp_path):
        root = _workspace(tmp_path)
        (root / ".project-directory").write_text("todo-app\n", encoding="utf-8")

        assert pin_the_directory_a_plan_names(root, PLAN) is None
        assert pinned_project_directory(root) == "todo-app"

    def test_an_existing_project_is_left_alone(self, tmp_path):
        root = _workspace(tmp_path)
        (root / "todo-app").mkdir()

        assert pin_the_directory_a_plan_names(root, PLAN) is None
        assert pinned_project_directory(root) is None


class TestTheDigestSaysSo:
    def test_before_any_code(self, tmp_path):
        root = _workspace(tmp_path)
        pin_the_directory_a_plan_names(root, PLAN)

        digest = render_workspace_digest(root)

        assert "This run's project directory is 'simple-to-do-list-app/'" in digest
        assert "it is empty so far" in digest

    def test_once_it_exists(self, tmp_path):
        root = _workspace(tmp_path)
        pin_the_directory_a_plan_names(root, PLAN)
        (root / "simple-to-do-list-app").mkdir(exist_ok=True)
        (root / "simple-to-do-list-app" / "index.html").write_text("<p>x</p>\n", encoding="utf-8")

        digest = render_workspace_digest(root, refresh=True)

        assert "This run's project directory is 'simple-to-do-list-app/'" in digest
        assert "empty so far" not in digest

    def test_nothing_pinned_adds_nothing(self, tmp_path):
        assert "project directory is" not in render_workspace_digest(_workspace(tmp_path))


def test_the_lead_node_pins_before_dispatch():
    import inspect

    from app.graph import workflow

    source = inspect.getsource(workflow)
    pin = source.index("pin_the_directory_a_plan_names(\n")
    dispatch = source.index('update["specialist_task_index"] = 0', pin)

    assert pin < dispatch


class TestTheProductNamesItFirst:
    """The architect and the lead both listed `/simple-to-do-list-app` for a
    product called "Simple To-Do List App" before anything had pinned or made it."""

    def test_the_name_becomes_the_directory(self, tmp_path):
        from app.tools.repository import pin_the_directory_the_product_names, pinned_project_directory

        assert pin_the_directory_the_product_names(tmp_path, "Simple To-Do List App") == "simple-to-do-list-app"
        assert pinned_project_directory(tmp_path) == "simple-to-do-list-app"
        assert (tmp_path / "simple-to-do-list-app").is_dir()

    def test_a_later_plan_does_not_move_it(self, tmp_path):
        from app.tools.repository import pin_the_directory_the_product_names, pinned_project_directory

        pin_the_directory_the_product_names(tmp_path, "Inventory Service")
        assert pin_the_directory_a_plan_names(tmp_path, PLAN) is None
        assert pinned_project_directory(tmp_path) == "inventory-service"

    def test_an_existing_codebase_is_left_where_it_is(self, tmp_path):
        from app.tools.repository import pin_the_directory_the_product_names, pinned_project_directory

        (tmp_path / "billing-api").mkdir()
        assert pin_the_directory_the_product_names(tmp_path, "Billing API") is None
        assert pinned_project_directory(tmp_path) is None

    def test_a_name_with_no_latin_letters_pins_nothing(self, tmp_path):
        from app.tools.repository import pin_the_directory_the_product_names

        assert pin_the_directory_the_product_names(tmp_path, "待办事项") is None
