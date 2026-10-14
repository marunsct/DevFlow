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
    assert fix_one.index("_fixed_by_rewriting(state, config, defect, fix_model)") < fix_one.index("create_specialist_agent(")
    helper = source[source.index("    def _fixed_by_rewriting("):source.index("    def _fix_one(")]
    assert "_fast_delivery()" in helper and "_the_run_approves_its_own_writes" in helper
