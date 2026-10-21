"""A builder or fixer can ask the harness's code graph where a name is defined and what uses a file (plan CG.4).

Behind `CODE_GRAPH_TOOL`, off until CG.2 is measured: a stage found these by
searching and reading.
"""
from __future__ import annotations

import inspect
import os
import re
from unittest import mock

from app.agents import specialists
from app.analysis import project_graph

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _project(tmp_path, monkeypatch):
    (tmp_path / ".project-directory").write_text("items-api")
    package = tmp_path / "items-api" / "items_api"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "store.py").write_text("def load_items():\n    return []\n\nclass ItemStore:\n    pass\n")
    (package / "routes.py").write_text("from items_api.store import load_items\n")
    return tmp_path


def test_where_a_name_is_defined_and_what_uses_a_file(tmp_path, monkeypatch):
    root = _project(tmp_path, monkeypatch)
    tool = project_graph.build_tool(root)

    assert tool.invoke({"where_is_name": "load_items"}) == {"defined_in": ["items-api/items_api/store.py"]}
    assert tool.invoke({"where_is_name": "itemstore"}) == {"defined_in": ["items-api/items_api/store.py"]}
    used = tool.invoke({"who_uses_path": "items-api/items_api/store.py"})
    assert used["imported_by"] == ["items-api/items_api/routes.py"] and "load_items" in used["defines"]
    assert "error" in tool.invoke({"who_uses_path": "items-api/items_api/gone.py"}) and "error" in tool.invoke({})
    assert not BANNED.search(tool.description)


def test_it_is_offered_only_when_on():
    assert "project_graph.tool_enabled()" in inspect.getsource(specialists.create_specialist_agent)
    with mock.patch.dict(os.environ, {"CODE_GRAPH_TOOL": ""}):
        assert not project_graph.tool_enabled()
    with mock.patch.dict(os.environ, {"CODE_GRAPH_TOOL": "on"}):
        assert project_graph.tool_enabled()
