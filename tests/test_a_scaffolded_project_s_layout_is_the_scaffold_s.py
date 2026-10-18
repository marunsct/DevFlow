"""Once a pack scaffolds the project, the prompt's layout section names where it is served from (Initiative X.4).

The general section's "one directory per tier - `backend/`, `frontend/`" was in
every specialist's prompt on a scaffolded full-stack run served from `src/` and
the package's `main.py`; the run drafted both tiers beside the served files.
"""

from __future__ import annotations

import json
import re

from app.agents.project_layout import PROJECT_LAYOUT, for_this_workspace


def _scaffolded(tmp_path):
    (tmp_path / ".harness").mkdir()
    (tmp_path / ".harness" / "stack-pack.json").write_text(json.dumps({
        "pack": "fullstack-react-fastapi", "project": "board", "package": "board", "title": "Board",
    }))
    return tmp_path


def test_a_scaffolded_workspace_is_told_where_the_product_is_served_from(tmp_path) -> None:
    text = for_this_workspace("Rules.\n" + PROJECT_LAYOUT, _scaffolded(tmp_path))

    assert "`board/src/App.tsx`" in text and "`board/board/main.py`" in text
    assert "task-dashboard/frontend/" not in text
    assert "ONE LANGUAGE PER DIRECTORY" in text and "`docs/` already exists" in text


def test_a_workspace_no_pack_scaffolded_keeps_the_general_section(tmp_path) -> None:
    assert for_this_workspace(PROJECT_LAYOUT, tmp_path) == PROJECT_LAYOUT


def test_every_role_agent_gets_the_workspace_s_section() -> None:
    import inspect

    from app.agents import role_agent

    assert "for_this_workspace(full_system_prompt, resolved_repo_root)" in inspect.getsource(role_agent.create_role_agent)


def test_the_new_section_avoids_the_banned_words(tmp_path) -> None:
    text = for_this_workspace(PROJECT_LAYOUT, _scaffolded(tmp_path))
    new = text[: text.index("- ONE LANGUAGE PER DIRECTORY")]
    words = set(re.findall(r"[\w-]+", re.sub(r"`[^`]*`", "", new).lower()))
    assert not words & {"task", "tasks", "to-do", "todo", "button", "click", "checkbox"}
