"""A file rewritten for one defect is shown the failures of the other open defects that point at it.

Measured: files were rewritten twice in one round, once for each open defect that pointed at them, each rewrite seeing
only its own defect's failure. Behind `CO_DEFECT_FAILURES_IN_REWRITES` (off until measured): the rewrite's prompt also
carries the other open defects whose failure points at the file, so one version of the file answers all of them.
"""
from __future__ import annotations

import inspect
import re
from types import SimpleNamespace

import pytest

from app.graph import co_defect_failures, rewritten_fixes, workflow

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
HEADING = "Other open defects whose failure points at this file"


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("CO_DEFECT_FAILURES_IN_REWRITES", "on")


class _Model:
    def __init__(self):
        self.asked = []

    def invoke(self, messages, **_):
        self.asked.append(messages[-1].content)
        return SimpleNamespace(content="```ts\nexport const store = 2;\n```")


def _workspace(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "store.ts").write_text("export const store = 1;\n")
    (tmp_path / "src" / "other.ts").write_text("export const other = 1;\n")
    return tmp_path


def _defect(description, files, status="open", actual=""):
    return SimpleNamespace(description=description, expected_behavior="it works", affected_files=files, status=status,
                           actual_behavior=actual, reproduction_steps=[])


MINE = _defect("[AC-1] Creating a note fails", ["src/store.ts"], actual="TypeError: store.add is not a function")
THEIRS = _defect("[AC-2] Listing notes returns nothing", ["src/store.ts"], actual="expected 3 notes, got 0")
ELSEWHERE = _defect("[AC-3] The health check is wrong", ["src/other.ts"], actual="expected ok, got nothing")


def _rewrite(root, co_defects):
    model = _Model()
    rewritten_fixes.fix_by_rewriting(
        MINE, root, model, files=["src/store.ts"], co_defects=co_defects,
        write=lambda base, path, content: (root / path).write_text(content),
    )
    return model.asked


def test_the_prompt_of_a_file_carries_the_other_open_defects_that_point_at_it(tmp_path):
    asked = _rewrite(_workspace(tmp_path), [THEIRS, ELSEWHERE])

    assert len(asked) == 1
    assert HEADING in asked[0]
    assert "[AC-2] Listing notes returns nothing" in asked[0] and "expected 3 notes, got 0" in asked[0]
    assert "[AC-3]" not in asked[0], "a defect that points at another file is not shown"
    assert not BANNED.search(asked[0].split(HEADING, 1)[1].split("---", 1)[0])


def test_off_the_prompt_is_the_defect_s_alone(tmp_path, monkeypatch):
    monkeypatch.setenv("CO_DEFECT_FAILURES_IN_REWRITES", "off")

    asked = _rewrite(_workspace(tmp_path), [THEIRS])

    assert HEADING not in asked[0] and "[AC-2]" not in asked[0]


def test_no_other_defect_adds_nothing_to_the_prompt(tmp_path):
    assert HEADING not in _rewrite(_workspace(tmp_path), [])[0]


def test_the_candidates_prompt_carries_them_too(tmp_path):
    root = _workspace(tmp_path)
    model = _Model()

    rewritten_fixes.fix_by_candidates(
        MINE, root, model, lambda: False, files=["src/store.ts"], co_defects=[THEIRS],
        write=lambda base, path, content: (root / path).write_text(content),
    )

    assert model.asked and all(HEADING in text and "[AC-2]" in text for text in model.asked)


def test_no_more_than_the_most_are_shown_for_one_file(tmp_path):
    many = [_defect(f"[AC-{n}] failure number {n}", ["src/store.ts"]) for n in range(10, 16)]

    shown = co_defect_failures.failures_by_file(many, _workspace(tmp_path), lambda path: True)

    assert shown["src/store.ts"].count("\n- [AC-") == co_defect_failures.MOST_CO_DEFECTS


def test_the_open_defects_besides_this_one_are_the_other_open_ones():
    done = _defect("[AC-4] already fixed", ["src/store.ts"], status="fixed")
    cycle = SimpleNamespace(defects=[MINE, THEIRS, done, ELSEWHERE])

    assert co_defect_failures.open_besides(cycle, MINE) == [THEIRS, ELSEWHERE]
    assert co_defect_failures.open_besides(None, MINE) == []


def test_off_there_are_no_other_defects_to_gather(monkeypatch):
    monkeypatch.setenv("CO_DEFECT_FAILURES_IN_REWRITES", "off")

    assert co_defect_failures.open_besides(SimpleNamespace(defects=[MINE, THEIRS]), MINE) == []


def test_the_fix_step_hands_the_other_open_defects_to_both_rewrite_paths():
    source = inspect.getsource(workflow)
    helper = source[source.index("    def _fixed_by_rewriting("):source.index("    def _fix_one(")]

    assert "open_besides(state.get(\"remediation\"), defect)" in helper
    assert helper.count("co_defects=co_defects") == 2
