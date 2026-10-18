"""A copy of the app that nothing serves comes after the served code in the project memory (plan item AQ).

Measured live: the project memory holds only what fits, and the second copy of
the app (`frontend/` and `backend/` beside the served `src/` and package)
filled it beside the served files, so fixers read the served files again and
again - 70 reads and 4 writes in one 40-call stage. Served files now come first.
"""
from __future__ import annotations

from app.agents import project_memory
from app.stacks import scaffold


def _files():
    return {
        "app/frontend/src/App.jsx": "export default 1\n",
        "app/frontend/src/main.jsx": "import './App'\n",
        "app/src/App.tsx": "export default 2\n",
        "app/src/main.tsx": "import './App'\n",
        "app/server.py": "x = 1\n",
    }


def test_files_in_an_unserved_folder_rank_after_the_served_ones():
    ranked = project_memory._ranked(_files(), "", ("app/frontend",))

    assert ranked[-2:] == ["app/frontend/src/App.jsx", "app/frontend/src/main.jsx"]
    assert set(ranked[:3]) == {"app/src/App.tsx", "app/src/main.tsx", "app/server.py"}


def test_a_file_the_request_names_still_comes_first_even_in_the_unserved_copy():
    ranked = project_memory._ranked(_files(), "the failure is in app/frontend/src/App.jsx", ("app/frontend",))

    assert ranked[0] == "app/frontend/src/App.jsx"


def test_without_an_unserved_folder_the_order_is_as_before():
    assert project_memory._ranked(_files(), "") == project_memory._ranked(_files(), "", ())


def test_the_memory_asks_the_detector_and_a_tight_budget_keeps_the_served_files(tmp_path, monkeypatch):
    monkeypatch.setattr(project_memory, "current", lambda root: _files())
    monkeypatch.setattr(scaffold, "folders_nothing_serves", lambda root: ["app/frontend"])
    served_size = sum(len(f"=== {p} ===\n{t.rstrip()}\n") for p, t in _files().items() if "frontend" not in p) + 1

    text, held = project_memory.render(tmp_path, served_size, "")

    assert "app/src/App.tsx" in held and "app/server.py" in held
    assert "app/frontend/src/App.jsx" not in held
