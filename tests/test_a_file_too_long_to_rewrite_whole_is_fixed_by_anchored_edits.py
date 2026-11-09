"""A file too long to come back whole within a reply is fixed by edits anchored on its own text (plan SZ.2).

The fast fix handed every file over whole and took the whole file back. A
reply is capped, reasoning included, so a file of a few thousand lines could
not come back at all, and one that nearly fit came back with what it was not
asked to change shortened. Small files are still rewritten whole, exactly as
before; past the threshold the model sees the outline and the parts the
failure points at, and replies with SEARCH/REPLACE edits the harness makes the
way `edit_artifact` does.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

from app.graph import anchored_edits, rewritten_fixes

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


class _Model:
    def __init__(self, replies):
        self.replies, self.asked, self.systems = list(replies), [], []

    def invoke(self, messages, **_):
        self.systems.append(messages[0].content)
        self.asked.append(messages[-1].content)
        return SimpleNamespace(content=self.replies.pop(0))


def _long_module(functions: int = 1300) -> str:
    # Past the project memory's largest whole file too (60,000 characters), so it is shown only here.
    return "".join(f"def handler_{n}(request):\n    return {{'status': {n}}}\n\n\n" for n in range(functions))


def _workspace(tmp_path, text):
    (tmp_path / "svc").mkdir()
    (tmp_path / "svc" / "routes.py").write_text(text)
    return tmp_path


def _defect(line: int):
    return SimpleNamespace(
        description="GET /items/7 answers 200 where the specification says 404", expected_behavior="404",
        affected_files=["svc/routes.py"],
        actual_behavior=f'File "/workspace/svc/routes.py", line {line}, in handler_700\nAssertionError: 200 != 404',
        reproduction_steps=[],
    )


def _fix(root, model, written):
    return rewritten_fixes.fix_by_rewriting(
        _defect(2802), root, model, may_write=lambda _: True,
        write=lambda base, path, content: written.append((path, content)),
    )


def test_the_threshold_is_past_what_a_small_product_s_files_hold():
    assert not anchored_edits.too_long_to_rewrite("x" * anchored_edits.LARGEST_WHOLE_FILE_CHARACTERS)
    assert anchored_edits.too_long_to_rewrite("x" * (anchored_edits.LARGEST_WHOLE_FILE_CHARACTERS + 1))


def test_a_small_file_is_still_asked_for_and_taken_back_whole(tmp_path):
    small = "def handler(request):\n    return {'status': 200}\n"
    root = _workspace(tmp_path, small)
    model = _Model(["```python\ndef handler(request):\n    return {'status': 404}\n```"])
    written: list = []

    _fix(root, model, written)

    assert f"--- `svc/routes.py` as it is now ---\n{small}" in model.asked[0]
    assert "Reply with the complete corrected content of `svc/routes.py`" in model.asked[0]
    assert "SEARCH" not in model.asked[0] and "SEARCH" not in model.systems[0]
    assert written == [("svc/routes.py", "def handler(request):\n    return {'status': 404}\n")]


def test_a_long_file_is_shown_by_its_outline_and_the_lines_the_failure_names(tmp_path):
    text = _long_module()
    root = _workspace(tmp_path, text)
    model = _Model([""])

    _fix(root, model, [])

    asked = model.asked[0]
    assert len(asked) < len(text)
    assert "too long to rewrite whole" in asked
    assert "1: def handler_0(request)" in asked  # the outline, by line
    assert "[lines 2782-2841]" in asked  # around the line the failure names, through its definition
    assert "def handler_700(request):" in asked
    assert "<<<<<<< SEARCH" in asked and ">>>>>>> REPLACE" in asked
    assert "complete corrected content" not in asked
    assert model.systems[0] == anchored_edits.SYSTEM


def test_a_long_file_the_project_memory_holds_whole_is_not_shown_twice(tmp_path):
    text = _long_module(700)
    assert anchored_edits.too_long_to_rewrite(text) and len(text) < 60_000
    root = _workspace(tmp_path, text)
    model = _Model([""])

    _fix(root, model, [])

    asked = model.asked[0]
    assert asked.count("def handler_600(request):") == 1
    assert "is in the project memory above, whole" in asked
    assert "<<<<<<< SEARCH" in asked


def test_a_long_file_s_edit_is_made_and_nothing_else_changes(tmp_path):
    text = _long_module()
    root = _workspace(tmp_path, text)
    reply = (
        "<<<<<<< SEARCH\ndef handler_700(request):\n    return {'status': 700}\n=======\n"
        "def handler_700(request):\n    return {'status': 404}\n>>>>>>> REPLACE\n"
    )
    written: list = []

    output = _fix(root, _Model([reply]), written)

    assert output is not None and output.changed_files == ["svc/routes.py"]
    assert written == [("svc/routes.py", text.replace("return {'status': 700}", "return {'status': 404}"))]


def test_an_edit_copied_with_its_line_numbers_and_margin_is_still_made(tmp_path):
    """The same repairs `edit_artifact` forgives, from the same code."""
    text = _long_module()
    root = _workspace(tmp_path, text)
    reply = (
        "<<<<<<< SEARCH\n2801: def handler_700(request):\n2802:     return {'status': 700}\n=======\n"
        "def handler_700(request):\n    return {'status': 404}\n>>>>>>> REPLACE\n"
    )
    written: list = []

    _fix(root, _Model([reply]), written)

    assert written and written[0][1] == text.replace("return {'status': 700}", "return {'status': 404}")


def test_an_edit_that_matches_twice_changes_nothing_and_the_next_pass_is_told_why(tmp_path):
    text = _long_module()
    root = _workspace(tmp_path, text)
    ambiguous = "<<<<<<< SEARCH\n    return {'status': 7}\n=======\n    return {'status': 404}\n>>>>>>> REPLACE\n"
    text = text.replace("handler_7(request):\n    return {'status': 7}", "handler_7(request):\n    return {'status': 7}\n    return {'status': 7}")
    (root / "svc" / "routes.py").write_text(text)
    exact = (
        "<<<<<<< SEARCH\ndef handler_7(request):\n    return {'status': 7}\n    return {'status': 7}\n=======\n"
        "def handler_7(request):\n    return {'status': 404}\n>>>>>>> REPLACE\n"
    )
    model = _Model([ambiguous, exact])
    written: list = []

    _fix(root, model, written)

    assert len(model.asked) == 2
    assert "Edits from the last pass that were not made, and why" in model.asked[1]
    assert "appears 2 times" in model.asked[1]
    assert written == [("svc/routes.py", text.replace(
        "handler_7(request):\n    return {'status': 7}\n    return {'status': 7}",
        "handler_7(request):\n    return {'status': 404}"))]


def test_a_long_file_given_back_whole_is_not_written(tmp_path):
    text = _long_module()
    root = _workspace(tmp_path, text)
    model = _Model([f"```python\n{text[: len(text) * 3 // 4]}```", ""])
    written: list = []

    assert _fix(root, model, written) is None
    assert written == []
    assert "too long to rewrite whole" in model.asked[1]


def test_candidates_edit_a_long_file_the_same_way(tmp_path):
    text = _long_module()
    root = _workspace(tmp_path, text)
    wrong = "<<<<<<< SEARCH\n    return {'status': 700}\n=======\n    return {'status': 'gone'}\n>>>>>>> REPLACE\n"
    right = "<<<<<<< SEARCH\n    return {'status': 700}\n=======\n    return {'status': 'missing'}\n>>>>>>> REPLACE\n"
    replies = iter([wrong, right, wrong])

    class _Parallel:
        def invoke(self, messages, **_):
            assert messages[0].content == anchored_edits.SYSTEM
            return SimpleNamespace(content=next(replies))

    def write(base, path, content):
        (root / path).write_text(content)

    output = rewritten_fixes.fix_by_candidates(
        _defect(2802), root, _Parallel(), lambda: "'status': 'missing'" in (root / "svc" / "routes.py").read_text(),
        may_write=lambda _: True, write=write, candidates=3, files=["svc/routes.py"],
    )

    assert output is not None
    assert (root / "svc" / "routes.py").read_text() == text.replace("return {'status': 700}", "return {'status': 'missing'}")


def test_what_the_model_is_told_uses_none_of_the_banned_words(tmp_path):
    from app.tools.repository import RepositoryToolError

    text = _long_module()
    told = [anchored_edits.SYSTEM, anchored_edits.instruction("svc/routes.py"),
            anchored_edits.excerpt("svc/routes.py", text, "routes.py:12"), anchored_edits.in_the_memory("svc/routes.py")]
    for reply in ("<<<<<<< SEARCH\nnowhere at all\n=======\nx\n>>>>>>> REPLACE\n", f"```python\n{text}```"):
        try:
            anchored_edits.applied("svc/routes.py", text, reply)
        except RepositoryToolError as refused:
            told.append(str(refused))
    assert len(told) == 6
    for text in told:
        assert not BANNED.search(text), text
