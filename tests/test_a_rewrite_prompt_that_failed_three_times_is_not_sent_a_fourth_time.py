"""A rewrite whose prompt is byte-identical to three that already failed is not sent again; the defect goes to the agent loop.

After a failed fix the harness asks for three candidate rewrites with one prompt; when none passes the defect's tests
the single rewrite that follows (`fix_by_rewriting`) was asked with that same prompt - a fourth sample of a request
three samples had answered wrongly. Behind `REPEATED_REWRITE_PROMPT_STOP` (off until measured).
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from app.graph import repeated_rewrite_prompts, rewritten_fixes


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("REPEATED_REWRITE_PROMPT_STOP", "on")
    repeated_rewrite_prompts.forget()
    yield
    repeated_rewrite_prompts.forget()


class _Model:
    def __init__(self):
        self.asked = []

    def invoke(self, messages, **_):
        self.asked.append(messages[-1].content)
        return SimpleNamespace(content=f"```ts\nexport const store = {len(self.asked) + 1};\n```")


def _workspace(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "store.ts").write_text("export const store = 1;\n")
    return tmp_path


def _defect(description="[AC-3] notes survive a restart"):
    return SimpleNamespace(description=description, expected_behavior="", affected_files=["src/store.ts"],
                           actual_behavior="", reproduction_steps=[])


def _write(root):
    return lambda base, path, content: (root / path).write_text(content)


def _failed_candidates_then_a_rewrite(root, model, defect=None):
    defect = defect or _defect()
    kept = rewritten_fixes.fix_by_candidates(
        defect, root, model, lambda: False, files=["src/store.ts"], write=_write(root))
    rewritten = rewritten_fixes.fix_by_rewriting(
        defect, root, model, files=["src/store.ts"], write=_write(root))
    return kept, rewritten


def test_the_rewrite_after_three_failed_candidates_with_the_same_prompt_is_not_sent(tmp_path):
    root, model = _workspace(tmp_path), _Model()

    kept, rewritten = _failed_candidates_then_a_rewrite(root, model)

    assert kept is None and rewritten is None, "the defect goes to the agent loop"
    assert len(model.asked) == rewritten_fixes.CANDIDATES == 3, "the fourth identical request is not sent"
    assert len(set(model.asked)) == 1


def test_off_the_fourth_identical_request_is_sent(tmp_path, monkeypatch):
    monkeypatch.setenv("REPEATED_REWRITE_PROMPT_STOP", "off")
    root, model = _workspace(tmp_path), _Model()

    _, rewritten = _failed_candidates_then_a_rewrite(root, model)

    assert len(model.asked) == 4 and rewritten is not None


def test_a_prompt_that_differs_is_still_sent(tmp_path):
    root, model = _workspace(tmp_path), _Model()
    rewritten_fixes.fix_by_candidates(_defect(), root, model, lambda: False, files=["src/store.ts"], write=_write(root))

    rewritten = rewritten_fixes.fix_by_rewriting(
        _defect("[AC-9] a different defect"), root, model, files=["src/store.ts"], write=_write(root))

    assert len(model.asked) == 4 and rewritten is not None


def test_candidates_one_of_which_passes_are_not_counted_as_failed(tmp_path):
    root, model = _workspace(tmp_path), _Model()
    answers = iter([False, True])

    kept = rewritten_fixes.fix_by_candidates(
        _defect(), root, model, lambda: next(answers), files=["src/store.ts"], write=_write(root))

    assert kept is not None
    assert not repeated_rewrite_prompts.exhausted(root, model.asked[0])
    assert repeated_rewrite_prompts._failures == {}


def test_a_prompt_is_exhausted_at_the_third_failure_in_its_own_workspace(tmp_path):
    other = tmp_path / "other"
    for _ in range(repeated_rewrite_prompts.MOST_IDENTICAL - 1):
        repeated_rewrite_prompts.failed(tmp_path, "the request")
    assert not repeated_rewrite_prompts.exhausted(tmp_path, "the request")

    repeated_rewrite_prompts.failed(tmp_path, "the request")

    assert repeated_rewrite_prompts.exhausted(tmp_path, "the request")
    assert not repeated_rewrite_prompts.exhausted(tmp_path, "the request, changed by one byte")
    assert not repeated_rewrite_prompts.exhausted(other, "the request")


def test_a_pass_after_the_diagnostics_is_a_different_prompt_and_is_sent(tmp_path):
    """The compiler's diagnostics change the prompt, so a second pass is not an identical request."""
    root, model = _workspace(tmp_path), _Model()

    rewritten_fixes.fix_by_rewriting(
        _defect(), root, model, files=["src/store.ts"], write=_write(root),
        diagnose=lambda files: ["- In `src/store.ts`: error TS1005"] if len(model.asked) == 1 else [])

    assert len(model.asked) == 2 and model.asked[0] != model.asked[1]


def test_it_is_in_the_source_of_both_rewrite_paths():
    for function in (rewritten_fixes.fix_by_rewriting, rewritten_fixes.fix_by_candidates):
        assert "repeated_rewrite_prompts.exhausted(root, asked)" in inspect.getsource(function)
