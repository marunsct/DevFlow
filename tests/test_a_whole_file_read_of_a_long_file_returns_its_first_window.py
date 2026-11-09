"""`read_repository_file` asked for a long file whole returns its first window and says where the rest is.

It returned the whole file, whatever its length. A file of a large codebase
runs to thousands of lines, and one read of it filled the window. `read_file`
already pages a file it is given no limit for; this tool did not. A short file
reads exactly as before.
"""

from __future__ import annotations

import re

from app.tools.agent_toolkit import FIRST_WINDOW_NOTE, MOST_LINES_READ_WHOLE, build_repository_read_tools

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _read(tmp_path, lines: int):
    (tmp_path / "big.py").write_text("".join(f"value_{n} = {n}\n" for n in range(lines)), encoding="utf-8")
    tool = next(t for t in build_repository_read_tools(str(tmp_path)) if t.name == "read_repository_file")
    return tool.invoke({"relative_path": "big.py"})


def test_a_long_file_read_whole_comes_back_as_its_first_window_with_a_note(tmp_path):
    result = _read(tmp_path, MOST_LINES_READ_WHOLE * 5)

    assert isinstance(result, dict)
    assert result["end_line"] == MOST_LINES_READ_WHOLE and result["has_more"] is True
    assert result["content"].count("\n") == MOST_LINES_READ_WHOLE - 1
    assert f"{MOST_LINES_READ_WHOLE * 5} lines" in result["note"]


def test_a_short_file_reads_exactly_as_it_did(tmp_path):
    result = _read(tmp_path, 20)

    assert result == (tmp_path / "big.py").read_text(encoding="utf-8")


def test_the_window_is_read_file_s_own():
    from app.agents.workspace_paths import DEFAULT_READ_LINES

    assert MOST_LINES_READ_WHOLE == DEFAULT_READ_LINES


def test_the_note_avoids_the_banned_words():
    assert not BANNED.search(FIRST_WINDOW_NOTE)
