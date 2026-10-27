"""An edit whose anchor differs from the file only in spacing, or that appends after the file's last line, is applied.

Deep review F7: 295 refusals in 20 runs for an anchor that matched nowhere as given or several times. Measured on
one run: QA added a test after `});` - nine refusals as ambiguous, the text appearing once per test - and another
copied `{a:1}` where the file reads `{ a: 1 }`. Each refusal cost a model turn.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.tools.repository import RepositoryToolError, edit_approved_artifact

SPEC = ("test('[AC-1] adds', async ({ request }) => {\n  expect(1).toBe(1);\n});\n\n"
        "test('[AC-2] lists', async ({ request }) => {\n  expect(2).toBe(2);\n});\n")


@pytest.fixture
def spec(tmp_path: Path) -> Path:
    (tmp_path / "app" / "acceptance").mkdir(parents=True)
    path = tmp_path / "app" / "acceptance" / "notes.spec.js"
    path.write_text(SPEC, encoding="utf-8")
    return path


def test_an_addition_after_the_last_closing_line_goes_at_the_end(tmp_path, spec):
    added = "});\n\ntest('[AC-3] deletes', async ({ request }) => {\n  expect(3).toBe(3);\n});"

    edit_approved_artifact(tmp_path, "app/acceptance/notes.spec.js", "});", added)

    text = spec.read_text(encoding="utf-8")
    assert text.count("[AC-3]") == 1 and text.index("[AC-3]") > text.index("[AC-2]")
    assert text.startswith(SPEC.split("\n\n")[0])


def test_a_change_of_one_of_several_matches_is_still_refused(tmp_path, spec):
    with pytest.raises(RepositoryToolError):
        edit_approved_artifact(tmp_path, "app/acceptance/notes.spec.js", "});", "}); // changed")


def test_an_anchor_off_only_by_spacing_inside_a_line_is_applied(tmp_path, spec):
    edit_approved_artifact(tmp_path, "app/acceptance/notes.spec.js",
                           "test('[AC-2] lists',async({request})=>{\n  expect(2).toBe(2);",
                           "test('[AC-2] lists', async ({ request }) => {\n  expect(2).toBe(22);")

    assert "toBe(22)" in spec.read_text(encoding="utf-8") and "toBe(2);" not in spec.read_text(encoding="utf-8")
