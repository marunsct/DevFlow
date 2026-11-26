"""An edit's error names `replace_lines` only where the stage is offered it.

Measured on one run: an acceptance author's ambiguous edit was answered "or - simpler - call `replace_lines` with the
line numbers of the one you meant", and `LINE_EDITS` was off, so no stage had that tool. Prompts were already cleaned
of the name; tool results were not. With it off, each way out an edit or write error gives must be one the stage can
take: a `find` that matches one copy only, or `edit_artifact`.
"""
from __future__ import annotations

import re

import pytest

from app.agents import stage_memory
from app.tools import repository
from app.tools.repository import RepositoryToolError, edit_approved_artifact, write_approved_artifact

BANNED = re.compile(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("LINE_EDITS", raising=False)
    stage_memory.forget_everything()
    repository._LOSSES_OUTSIDE_A_RUN.clear()
    repository._LAST_CHANGE.clear()
    yield
    stage_memory.forget_everything()
    repository._LOSSES_OUTSIDE_A_RUN.clear()
    repository._LAST_CHANGE.clear()


def _refused(call, *args) -> str:
    with pytest.raises(RepositoryToolError) as raised:
        call(*args)
    return str(raised.value)


def _copies_on_separate_lines(root) -> str:
    write_approved_artifact(str(root), "p/a.mjs",
                            "run(() => {\n  load();\n  check(ok);\n});\nrun(() => {\n  load();\n  check(ok);\n});\n")
    return _refused(edit_approved_artifact, str(root), "p/a.mjs", "  check(ok);\n", "  check(better);\n")


def _copies_on_one_line(root) -> str:
    write_approved_artifact(str(root), "p/a.js", "function a() {\n  if (p) { x(); } else { y(); }\n}\n")
    return _refused(edit_approved_artifact, str(root), "p/a.js", "}", "};")


def _an_empty_find(root) -> str:
    write_approved_artifact(str(root), "p/a.js", "const a = 1;\n")
    return _refused(edit_approved_artifact, str(root), "p/a.js", "", "const b = 2;\n")


def _a_fragment_over_the_file(root) -> str:
    write_approved_artifact(str(root), "p/app.js",
                            "".join(f"export function step{i}() {{ return {i}; }}\n" for i in range(12)))
    with stage_memory.remembering("visit-a"):
        return _refused(write_approved_artifact, str(root), "p/app.js", "export function step0() { return 0; }\n")


def _a_second_rewrite_that_drops_a_name(root) -> str:
    whole = ("export function load() { return []; }\nexport function init() {\n"
             "  const wrapper = document.createElement('span');\n  return wrapper;\n}\n")
    without = "export function load() { return []; }\nexport function init() {\n  return document.createElement('span');\n}\n"
    write_approved_artifact(str(root), "p/app.js", whole)
    with stage_memory.remembering("visit-a"):
        write_approved_artifact(str(root), "p/app.js", without)
        write_approved_artifact(str(root), "p/app.js", whole)
        return _refused(write_approved_artifact, str(root), "p/app.js", without)


ERRORS = {
    "an ambiguous passage on separate lines": _copies_on_separate_lines,
    "an ambiguous passage on one line": _copies_on_one_line,
    "an empty find": _an_empty_find,
    "a fragment written over the file": _a_fragment_over_the_file,
    "a second rewrite dropping a name": _a_second_rewrite_that_drops_a_name,
}


@pytest.mark.parametrize("make", ERRORS.values(), ids=ERRORS.keys())
def test_with_line_edits_off_no_error_names_replace_lines(tmp_path, make):
    said = make(tmp_path)

    assert "replace_lines" not in said, said


@pytest.mark.parametrize("make", ERRORS.values(), ids=ERRORS.keys())
def test_the_way_out_avoids_the_banned_words(tmp_path, make):
    assert not BANNED.search(make(tmp_path))


def test_the_ambiguous_passage_still_says_how_to_pick_one_copy(tmp_path):
    said = _copies_on_separate_lines(tmp_path)

    assert "lines 3 and 7" in said and "`find`" in said
    assert "the copy at line 3:" in said


def test_a_fragment_refusal_names_the_edit_tool_it_has(tmp_path):
    assert "`edit_artifact`" in _a_fragment_over_the_file(tmp_path)


@pytest.mark.parametrize("make", [_copies_on_separate_lines, _a_fragment_over_the_file],
                         ids=["an ambiguous passage", "a fragment written over the file"])
def test_with_line_edits_on_the_advice_names_it(tmp_path, monkeypatch, make):
    monkeypatch.setenv("LINE_EDITS", "on")

    assert "`replace_lines`" in make(tmp_path)
