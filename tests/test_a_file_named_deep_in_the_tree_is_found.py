"""A file a failure or a work order names is found however deep in the tree it is.

A name was looked up as `root/name` or one folder down, nothing deeper. In a
large codebase a traceback's `items/store.py` is
`shop/services/items/store.py`, so the defect that named it was given no file
and went to an agent loop to find it by reading. A name two files share at the
same depth is not guessed.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.analysis.walk import the_file_ending
from app.graph import drafting, rewritten_fixes


def _tree(root: Path) -> Path:
    deep = root / "shop" / "services" / "items"
    deep.mkdir(parents=True)
    (deep / "store.py").write_text("def load():\n    return []\n")
    (root / "shop" / "services" / "users").mkdir()
    (root / "shop" / "services" / "users" / "models.py").write_text("class User: ...\n")
    (root / "shop" / "services" / "items" / "models.py").write_text("class Item: ...\n")
    (root / "shop" / "node_modules" / "items").mkdir(parents=True)
    (root / "shop" / "node_modules" / "items" / "store.py").write_text("")
    return deep / "store.py"


def test_the_one_file_whose_path_ends_so_is_found(tmp_path):
    store = _tree(tmp_path)

    assert the_file_ending(tmp_path, "items/store.py", {"node_modules"}) == store
    assert the_file_ending(tmp_path, "store.py", {"node_modules"}) == store


def test_two_files_at_the_same_depth_are_not_guessed_between(tmp_path):
    _tree(tmp_path)

    assert the_file_ending(tmp_path, "models.py", {"node_modules"}) is None
    assert the_file_ending(tmp_path, "users/models.py", {"node_modules"}).parent.name == "users"


def test_the_shallowest_wins(tmp_path):
    _tree(tmp_path)
    (tmp_path / "shop" / "models.py").write_text("")

    assert the_file_ending(tmp_path, "models.py") == tmp_path / "shop" / "models.py"


def test_a_fix_is_given_the_deep_file_its_failure_names(tmp_path):
    _tree(tmp_path)

    found = rewritten_fixes._the_files(tmp_path, ["items/store.py"], [], False, False, lambda _: True)

    assert found == ["shop/services/items/store.py"]


def test_a_draft_is_shown_the_deep_file_its_work_order_names(tmp_path):
    _tree(tmp_path)

    shown = drafting._neighbours(tmp_path, "shop/app.py", SimpleNamespace(files=["items/store.py"]), "")

    assert "shop/services/items/store.py" in shown and "def load" in shown
