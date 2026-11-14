"""A fixer is told the compiler's errors in the product's own files when the last production build failed.

Measured on one run: the build named a call with one argument too many in the product's item view. Three acceptance
criteria failed on that one error; their fixers, told only what the suite saw, spent eight rounds on markup and labels.
"""
from __future__ import annotations

import json
import os
import re
from types import SimpleNamespace
from unittest import mock

from app.agents import where_things_stand
from app.stacks import production_build

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
SAID = "\n".join([
    "> app@0.1.0 build",
    "> tsc && vite build",
    "",
    "src/components/ItemRow.tsx(39,28): error TS2554: Expected 1 arguments, but got 2.",
    "tests/types.test.tsx(9,30): error TS2304: Cannot find name 'global'.",
    "src/App.spec.tsx(3,1): error TS2304: Cannot find name 'describe'.",
    "acceptance/list.spec.js:4: something",
])


def _workspace(tmp_path, failure=SAID):
    (tmp_path / ".harness").mkdir()
    (tmp_path / production_build.RECORD).write_text(
        json.dumps({"fingerprint": "f", "command": "npm run build", "failure": failure}), encoding="utf-8")
    return {"repository": SimpleNamespace(root_path=str(tmp_path)), "specialist_outputs": {}}


def test_only_the_product_s_own_lines_are_read(tmp_path):
    _workspace(tmp_path)
    assert production_build.errors_in_the_product(tmp_path) == [
        "src/components/ItemRow.tsx(39,28): error TS2554: Expected 1 arguments, but got 2."]


def test_the_block_opens_with_the_build_s_errors(tmp_path):
    state = _workspace(tmp_path)
    with mock.patch.dict(os.environ, {"WHERE_THINGS_STAND": "on"}):
        text = where_things_stand.block(state)
    first = text.splitlines()[1]
    assert first.startswith("- The product's production build failed")
    assert "ItemRow.tsx(39,28): error TS2554" in first and "types.test.tsx" not in text


def test_a_build_that_passed_or_was_never_run_says_nothing(tmp_path):
    assert production_build.errors_in_the_product(tmp_path) == []
    state = _workspace(tmp_path, failure="")
    with mock.patch.dict(os.environ, {"WHERE_THINGS_STAND": "on"}):
        assert where_things_stand.block(state) == ""


def test_its_words_ban_the_product_s_nouns(tmp_path):
    state = _workspace(tmp_path, failure="src/a.ts(1,1): error X")
    with mock.patch.dict(os.environ, {"WHERE_THINGS_STAND": "on"}):
        text = where_things_stand.block(state).replace("src/a.ts(1,1): error X", "")
    assert text and not BANNED.search(text)
