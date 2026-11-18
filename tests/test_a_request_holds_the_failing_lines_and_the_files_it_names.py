"""A request's project memory holds a long file's failing lines, not the whole file, and (sliced) the files it names.

Deep review 2026-11-18, item C3: a fixer's request averaged 164k characters and a builder's 269k, most of it project
memory; one fixer whose defect was a manifest that would not install was handed a 28.7k test file whole. A fixer's
long file is now held as the lines around those its failure names; one it never names is named with what it defines.
With `SLICED_MEMORY` on, a fixer's or builder's memory holds whole only the product files its request names and what
they import.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.agents.project_memory import render

BANNED = {"task", "tasks", "to-do", "todo", "button", "click", "checkbox"}


def _long_test_file(lines: int = 600) -> str:
    return "\n".join(f"def test_case_{n}():\n    assert value_{n} == {n}" for n in range(lines // 2)) + "\n"


def _workspace(root: Path) -> Path:
    (root / "app" / "tests").mkdir(parents=True)
    (root / "app" / "src").mkdir(parents=True)
    (root / "app" / "tests" / "test_store.py").write_text(_long_test_file())
    (root / "app" / "tests" / "test_other.py").write_text(_long_test_file())
    (root / "app" / "src" / "store.py").write_text("from .shape import Note\n\ndef save(note):\n    return note\n")
    (root / "app" / "src" / "shape.py").write_text("class Note:\n    pass\n")
    (root / "app" / "src" / "unrelated.py").write_text("def unrelated():\n    return 1\n")
    (root / "app" / "src" / "__init__.py").write_text("")
    return root


def _fix_request(failure: str) -> str:
    return ("--- Where things stand (written by the harness from what it measured) ---\n"
            "Finished: `app/tests/test_store.py`, `app/tests/test_other.py`, `app/src/unrelated.py`\n\n"
            "--- Defect ---\nThe unit tests fail.\n\n--- What the last failing command actually printed ---\n"
            f"{failure}\n")


def test_a_fixer_is_held_the_lines_its_failure_names_in_a_long_file_not_the_file(tmp_path):
    root = _workspace(tmp_path)

    memory, held = render(root, 240_000, _fix_request("tests/test_store.py:201: AssertionError"), for_a_fixer=True)

    assert "202:     assert value_100 == 100" in memory
    assert "value_5 ==" not in memory
    assert "read others by line" in memory
    assert "app/tests/test_store.py" not in held


def test_a_long_file_the_fixer_s_request_never_names_is_named_with_what_it_defines(tmp_path):
    root = _workspace(tmp_path)

    memory, held = render(root, 240_000, _fix_request("tests/test_store.py:201: AssertionError"), for_a_fixer=True)

    assert "app/tests/test_other.py" not in held
    assert re.search(r"Not included here[^\n]*app/tests/test_other\.py", memory)


def test_a_long_file_the_request_names_with_no_line_is_held_whole(tmp_path):
    root = _workspace(tmp_path)

    memory, held = render(root, 240_000, _fix_request("app/tests/test_store.py failed to collect"), for_a_fixer=True)

    assert "app/tests/test_store.py" in held


def test_a_sliced_memory_holds_the_named_files_and_what_they_import(tmp_path):
    root = _workspace(tmp_path)

    memory, held = render(root, 240_000, _fix_request("app/src/store.py:3: TypeError"), for_a_fixer=True, sliced=True)

    assert {"app/src/store.py", "app/src/shape.py"} <= set(held)
    assert "app/src/unrelated.py" not in held
    assert "the files this request names and the files they import" in memory


def test_a_sliced_memory_holds_everything_when_the_request_names_no_file(tmp_path):
    root = _workspace(tmp_path)

    _, held = render(root, 240_000, "--- Defect ---\nThe service does not start.\n", sliced=True)

    assert {"app/src/store.py", "app/src/shape.py", "app/src/unrelated.py"} <= set(held)


def test_the_new_memory_text_avoids_the_banned_words():
    from app.agents.memory_slices import SAID, windowed_block

    text = SAID + windowed_block("a/b.py", "x\n" * 50, [10])
    assert not set(re.findall(r"[\w-]+", text.lower())) & BANNED
