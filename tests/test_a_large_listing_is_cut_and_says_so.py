"""A listing, glob or search of a large codebase hands over its first entries and says the rest exist.

deepagents stops `ls`, `glob` and `grep` only at 80,000 characters - about
20,000 tokens, most of this model's window. A directory of a large codebase
holds thousands of files, and one listing of it crowded out the work it was
asked for. A small project's listings are unchanged.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.agents.workspace_backend import MOST_ENTRIES_SHOWN, THE_REST_NOT_LISTED, WorkspaceBackend


def _backend(root: Path) -> WorkspaceBackend:
    return WorkspaceBackend(str(root), virtual_mode=True)


def _files(root: Path, count: int) -> None:
    (root / "app").mkdir()
    for number in range(count):
        (root / "app" / f"module_{number:04d}.py").write_text("VALUE = 'needle'\n", encoding="utf-8")


def _paths(result: object) -> list[str]:
    entries = getattr(result, "entries", None) or getattr(result, "matches", None) or []
    return [str(e.get("path")) for e in entries]


def test_a_directory_of_thousands_is_listed_to_the_cap_and_names_how_many_more(tmp_path):
    _files(tmp_path, MOST_ENTRIES_SHOWN + 50)

    paths = _paths(_backend(tmp_path).ls("/app"))

    assert len(paths) == MOST_ENTRIES_SHOWN + 1
    assert "50 more entries" in paths[-1]


def test_a_small_directory_is_listed_whole(tmp_path):
    _files(tmp_path, 12)

    paths = _paths(_backend(tmp_path).ls("/app"))

    assert len(paths) == 12
    assert not any("more entries" in p for p in paths)


def test_a_glob_past_the_cap_is_marked_partial_so_the_model_is_told_to_narrow_it(tmp_path):
    _files(tmp_path, MOST_ENTRIES_SHOWN + 50)

    result = _backend(tmp_path).glob("*.py", "/app")

    assert len(result.matches) == MOST_ENTRIES_SHOWN
    assert result.truncated is True


def test_a_small_glob_is_whole_and_not_marked_partial(tmp_path):
    _files(tmp_path, 12)

    result = _backend(tmp_path).glob("*.py", "/app")

    assert len(result.matches) == 12
    assert not result.truncated


def test_a_search_past_the_cap_is_marked_partial_unless_the_agent_asked_for_a_count(tmp_path):
    _files(tmp_path, MOST_ENTRIES_SHOWN + 50)
    backend = _backend(tmp_path)

    capped = backend.grep("needle", "/app")
    asked = backend.grep("needle", "/app", max_count=MOST_ENTRIES_SHOWN + 100)

    assert len(capped.matches) == MOST_ENTRIES_SHOWN and capped.truncated is True
    assert len(asked.matches) == MOST_ENTRIES_SHOWN + 50


def test_the_note_avoids_the_banned_words():
    assert not re.search(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", THE_REST_NOT_LISTED, re.I)
