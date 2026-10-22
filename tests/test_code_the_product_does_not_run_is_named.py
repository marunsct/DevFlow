"""Code beside the served app that nothing runs is named, to every fixer and at release.

Measured on one run: the drafted page sat in `frontend/src/` and the drafted
service in `backend/app/` while the scaffold served `src/` and the package's
`main.py`. Fixes landed in both trees - one rewrote a migration nothing ran -
and the unit tests imported the unserved service, so their result said nothing
about the product the acceptance suite measured.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from app.stacks.scaffold import code_the_product_does_not_run

PROJECT = "board"


def _workspace(tmp_path, files: dict[str, str]):
    (tmp_path / ".harness").mkdir()
    (tmp_path / ".harness" / "stack-pack.json").write_text(json.dumps({
        "pack": "fullstack-react-fastapi", "project": PROJECT, "package": "board", "title": "Board",
    }))
    for path, text in files.items():
        target = tmp_path / PROJECT / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    return tmp_path


SERVED = {
    # The served page imports its own modules, as a built one does; a module it
    # never imports is a finding of its own (`app.analysis.reachability`).
    "src/App.tsx": "import D from './pages/Dashboard';\nimport { get } from './api/client';\nexport default function App() {}",
    "src/pages/Dashboard.jsx": "export default 1",
    "src/api/client.jsx": "export const get = 1",
    "board/main.py": "app = object()",
}


def test_a_second_copy_of_the_served_folder_is_named(tmp_path) -> None:
    root = _workspace(tmp_path, {
        **SERVED,
        "frontend/src/App.jsx": "x", "frontend/src/pages/Dashboard.jsx": "x", "frontend/src/api/client.jsx": "x",
    })
    [problem] = code_the_product_does_not_run(root)
    assert "`board/frontend/src/` repeats 3 files of the served `board/src/`" in problem


def test_unit_tests_of_other_code_are_named(tmp_path) -> None:
    root = _workspace(tmp_path, {
        **SERVED,
        "backend/app/__init__.py": "def create_app(): ...",
        "tests/conftest.py": "from app import create_app",
        "tests/test_auth.py": "def test_login(client): ...",
    })
    [problem] = code_the_product_does_not_run(root)
    assert "never name `board`" in problem and "tests/test_auth.py" in problem


def test_unit_tests_of_the_served_code_and_one_shared_file_name_nothing(tmp_path) -> None:
    root = _workspace(tmp_path, {
        **SERVED,
        "tests/conftest.py": "from board.main import app",
        "tests/test_auth.py": "def test_login(client): ...",
        "frontend/src/App.jsx": "x",
    })
    assert code_the_product_does_not_run(root) == []


def test_every_fixer_and_the_release_are_told(tmp_path, monkeypatch) -> None:
    import inspect

    from app.graph import delivery, workflow

    root = _workspace(tmp_path, {**SERVED, "frontend/src/App.jsx": "x", "frontend/src/api/client.jsx": "x"})
    assert "Code the product does not run" in workflow._the_unserved_code_section(str(root))
    assert "_the_unserved_code_section(state[\"repository\"].root_path)" in inspect.getsource(workflow)
    gaps = delivery._code_the_product_does_not_run(str(root))
    assert len(gaps) == 1 and gaps[0].startswith("Code the product does not run:")
    assert "gaps.extend(_code_the_product_does_not_run(root))" in inspect.getsource(delivery.release)
    SimpleNamespace()


def test_what_the_fixer_is_told_avoids_the_banned_words(tmp_path) -> None:
    import re

    from app.graph import workflow

    root = _workspace(tmp_path, {
        **SERVED, "frontend/src/App.jsx": "x", "frontend/src/api/client.jsx": "x",
        "tests/test_auth.py": "def test_login(): ...",
    })
    text = re.sub(r"`[^`]*`", "", workflow._the_unserved_code_section(str(root))).lower()
    banned = {"task", "tasks", "to-do", "todo", "button", "click", "checkbox"}
    assert text and not set(re.findall(r"[\w-]+", text)) & banned
