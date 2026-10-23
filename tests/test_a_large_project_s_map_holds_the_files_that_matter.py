"""A map of what each file defines holds, on a large project, the files that matter - and says how many it left out.

It was cut at its budget in path order. On a project of a few hundred files
the localiser's map held `api/` and `app/` and never the `src/` the failure
was in, and the memory's list of files left out named every one of them,
larger than the memory and outside its budget. A small project's map is
unchanged.
"""
from __future__ import annotations

import re

from app.agents import project_memory
from app.agents.project_memory import map_of

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _large() -> dict[str, str]:
    files = {f"api/module_{n:03}.py": f"def handler_{n}():\n    pass\nclass Model{n}:\n    pass\n" for n in range(400)}
    files["src/billing/invoice.py"] = "def total_due(invoice):\n    return 0\n"
    return files


def test_a_small_project_s_map_is_as_it_was():
    files = {"b.py": "def b():\n    pass\n", "a.py": "class A:\n    pass\n", "notes.txt": "nothing\n"}
    assert map_of(files) == "- a.py: class A\n- b.py: def b()"


def test_the_file_a_failure_names_is_in_a_large_project_s_map():
    shown = map_of(_large(), focus="AssertionError in src/billing/invoice.py: total_due returned 0",
                   most_characters=2_000)

    assert "src/billing/invoice.py" in shown
    assert len(shown) < 2_300


def test_a_file_defining_the_failure_s_words_comes_before_the_rest():
    shown = map_of(_large(), focus="total_due is wrong", most_characters=2_000)
    assert shown.splitlines()[0].startswith("- src/billing/invoice.py")


def test_the_map_counts_the_files_it_left_out():
    shown = map_of(_large(), most_characters=2_000)
    assert re.search(r"\(\d{3} more files define things not shown here", shown)
    assert not BANNED.search(shown.splitlines()[-1])


def test_the_most_imported_files_come_first_when_nothing_is_named():
    shown = map_of(_large(), most_characters=500, importance={"api/module_399.py": 40})
    assert shown.splitlines()[0].startswith("- api/module_399.py")


def test_a_large_project_s_left_out_files_are_counted_not_all_named(tmp_path):
    for n in range(300):
        (tmp_path / f"m{n:03}.py").write_text("x = 1\n" * 2_000)
    text, _ = project_memory.render(tmp_path, 20_000)

    listed = text.split("Not included here (read when needed): ", 1)[1].split("\n", 1)[0]
    assert listed.count(".py") == project_memory.MOST_NAMED_LEFT_OUT
    assert re.search(r"and \d+ more \(list a folder or search to find them\)", listed)
    assert not BANNED.search(listed)
