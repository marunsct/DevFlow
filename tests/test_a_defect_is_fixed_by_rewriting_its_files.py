"""Fast delivery fixes a defect by the harness gathering and the model rewriting one file per call.

Measured on one run: 294 model calls and 152 minutes of agent loops to fix one
sprint's defects - listing, reading, searching and running tests to find what
the harness already knew - with one tool call in ten malformed.
"""

from __future__ import annotations

import inspect
import re
from types import SimpleNamespace

from app.graph import rewritten_fixes, workflow

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


class _Model:
    def __init__(self, replies):
        self.replies, self.asked = list(replies), []

    def invoke(self, messages):
        self.asked.append(messages[-1].content)
        return SimpleNamespace(content=self.replies.pop(0))


def _workspace(tmp_path):
    src = tmp_path / "notes-api" / "src"
    src.mkdir(parents=True)
    (src / "validate.ts").write_text("export const MAX_SAFE_ID = 1;\nexport const MAX_SAFE_ID = 2;\n")
    (src / "store.ts").write_text("export const store = 1;\n")
    (tmp_path / "notes-api" / "tests").mkdir()
    (tmp_path / "notes-api" / "tests" / "locked.test.ts").write_text("// locked\n")
    return tmp_path


DEFECT = SimpleNamespace(
    description="The service does not start", expected_behavior="It starts", affected_files=["notes-api/src/store.ts"],
    actual_behavior="src/validate.ts(3,14): error TS2451: Cannot redeclare block-scoped variable 'MAX_SAFE_ID'.\n"
                    "tests/locked.test.ts:4:1 failed",
    reproduction_steps=["npm run build"],
)


def test_the_files_are_the_named_ones_and_the_ones_the_failure_points_at(tmp_path):
    root = _workspace(tmp_path)
    failure = rewritten_fixes.what_failed(DEFECT, root)

    files = rewritten_fixes.files_to_fix(DEFECT, failure, root, lambda path: "locked" not in path)

    assert files == ["notes-api/src/store.ts", "notes-api/src/validate.ts"]


def test_a_file_the_failure_names_without_a_line_is_rewritten_first(tmp_path):
    """Every failing test said what the README lacked; the stack pointed at the entry point."""
    root = _workspace(tmp_path)
    (root / "notes-api" / "README.md").write_text("# Notes\n")
    failure = (
        "- readme › AC-15 (tests/readme.test.ts): AC-15: README.md must give PORT a default value\n"
        "    at start (src/store.ts:12:5)\n"
    )
    defect = SimpleNamespace(**{**DEFECT.__dict__, "affected_files": []})

    files = rewritten_fixes.files_to_fix(defect, failure, root, lambda path: "test" not in path)

    assert files == ["notes-api/README.md", "notes-api/src/store.ts"]


def test_each_file_is_rewritten_in_one_call_and_the_compiler_is_given_back(tmp_path):
    root = _workspace(tmp_path)
    model = _Model(["```ts\nexport const store = 2;\n```", "```ts\nexport const MAX_SAFE_ID = 1;\n```",
                    "```ts\nexport const MAX_SAFE_ID = 9;\n```"])
    written = {}
    reported = [["- In `notes-api/src/validate.ts` line 1: still wrong"], []]

    output = rewritten_fixes.fix_by_rewriting(
        DEFECT, root, model, may_write=lambda path: "locked" not in path,
        write=lambda base, path, content: written.__setitem__(path, content),
        diagnose=lambda files: reported.pop(0),
    )

    assert output.changed_files == ["notes-api/src/store.ts", "notes-api/src/validate.ts"]
    assert written["notes-api/src/validate.ts"] == "export const MAX_SAFE_ID = 9;\n", "a second pass on what still failed"
    assert len(model.asked) == 3
    assert "Cannot redeclare block-scoped variable 'MAX_SAFE_ID'" in model.asked[0]
    assert "still wrong" in model.asked[2]
    assert not BANNED.search(model.asked[0].split("\n\n")[0] + model.asked[0].split("\n\n")[-1])


def test_a_defect_with_no_file_to_rewrite_goes_to_the_agent_loop(tmp_path):
    root = _workspace(tmp_path)
    vague = SimpleNamespace(description="Something is off", expected_behavior="", affected_files=[],
                            actual_behavior="it is wrong", reproduction_steps=[])

    assert rewritten_fixes.fix_by_rewriting(vague, root, _Model([])) is None


def test_the_fix_step_tries_rewriting_before_the_agent_loop():
    source = inspect.getsource(workflow)
    fix_one = source[source.index("    def _fix_one("):source.index("    def defect_remediation_node(")]
    assert fix_one.index("_fixed_by_rewriting(") < fix_one.index("create_specialist_agent(")
    helper = source[source.index("    def _fixed_by_rewriting("):source.index("    def _fix_one(")]
    assert "_fast_delivery()" in helper and "_the_run_approves_its_own_writes" in helper


class _Numbered:
    """Each call answers with the next numbered version of the file."""

    def __init__(self):
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        return SimpleNamespace(content=f"```ts\nexport const store = {self.calls};\n```")


def test_candidates_are_asked_at_once_and_the_first_its_tests_pass_is_kept(tmp_path):
    root = _workspace(tmp_path)
    store = root / "notes-api" / "src" / "store.ts"
    defect = SimpleNamespace(description="[AC-3] notes survive", expected_behavior="", affected_files=["notes-api/src/store.ts"],
                             actual_behavior="", reproduction_steps=[])
    seen = []

    def check():
        seen.append(store.read_text())
        return len(seen) == 2

    kept = rewritten_fixes.fix_by_candidates(
        defect, root, _Numbered(), check, write=lambda base, path, content: (root / path).write_text(content),
    )

    assert kept.changed_files == ["notes-api/src/store.ts"]
    assert len(seen) == 2 and store.read_text() == seen[1], "the second candidate, the one that passed, stays"
    assert seen[0] != seen[1]


def test_no_candidate_passing_puts_the_files_back_for_the_agent_loop(tmp_path):
    root = _workspace(tmp_path)
    store = root / "notes-api" / "src" / "store.ts"
    before = store.read_text()

    kept = rewritten_fixes.fix_by_candidates(
        DEFECT, root, _Numbered(), lambda: False, may_write=lambda path: "locked" not in path,
        write=lambda base, path, content: (root / path).write_text(content),
    )

    assert kept is None and store.read_text() == before


def test_the_fix_step_asks_for_candidates_after_a_failed_fix():
    source = inspect.getsource(workflow)
    helper = source[source.index("    def _fixed_by_rewriting("):source.index("    def _fix_one(")]
    assert "failed_tries >= 1" in helper and "fix_by_candidates(" in helper
    assert "_the_defect_s_tests_pass(root, defect)" in helper


def test_fix_by_rewriting_when_model_is_none_falls_back_or_returns_none(tmp_path, monkeypatch):
    root = _workspace(tmp_path)
    calls = []

    class _Fallback:
        def invoke(self, msgs):
            calls.append(msgs)
            return SimpleNamespace(content="```ts\nexport const store = 99;\n```")

    monkeypatch.setattr("app.models.build_default_chat_model", lambda *a, **k: _Fallback())
    output = rewritten_fixes.fix_by_rewriting(DEFECT, root, None, write=lambda b, p, c: None)
    assert len(calls) > 0, "fallback model was invoked when model argument is None"


def test_the_fix_step_supplies_fallback_model_when_building_model_is_none():
    source = inspect.getsource(workflow)
    helper = source[source.index("    def _fixed_by_rewriting("):source.index("    def _fix_one(")]
    assert "fix_model or model or building_model" in helper

