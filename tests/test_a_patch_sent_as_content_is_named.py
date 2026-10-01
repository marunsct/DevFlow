"""A `replace_lines` content written as a diff is named as one.

Measured on one run: `defect_fix_1_1` sent

    -      }));
    +      completed: Boolean(t.completed)
    +      }));

as the `content` of a `replace_lines` - a patch, which `content` is not - and
was told "Unexpected token '-'" four times in a row, the last two by the repeat
guard, without learning why. `defect_fix_1_2` then did the same.
"""

from __future__ import annotations

import shutil

import pytest

from app.tools.repository import RepositoryToolError, _written_as_a_diff, replace_approved_lines

STORAGE = """\
export function load(raw) {
  const parsed = JSON.parse(raw);
  return parsed.map(t => ({
    id: String(t.id || ''),
    title: String(t.title || ''),
  }));
}
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
def test_the_refusal_says_content_is_not_a_patch(tmp_path) -> None:
    (tmp_path / "storage.js").write_text(STORAGE, encoding="utf-8")
    patch = "    title: String(t.title || ''),\n-  }));\n+    completed: Boolean(t.completed),\n+  }));"

    with pytest.raises(RepositoryToolError) as caught:
        replace_approved_lines(tmp_path, "storage.js", 5, 6, patch)

    message = str(caught.value)
    assert "Line 2 of your `content` begins with '-'" in message
    assert "not a patch" in message
    assert (tmp_path / "storage.js").read_text(encoding="utf-8") == STORAGE


def test_one_marker_on_a_line_the_file_holds() -> None:
    assert "diff marker" in _written_as_a_diff("-    title: String(t.title || ''),", STORAGE)


def test_a_lone_list_item_is_not_a_diff() -> None:
    assert _written_as_a_diff("- buy milk\n- walk the dog", STORAGE) == ""


def test_a_decrement_is_not_a_marker() -> None:
    assert _written_as_a_diff("--count;\n++index;", "--count;\n++index;") == ""


def test_both_markers_together_are_a_diff_wherever_the_text_is() -> None:
    assert "diff marker" in _written_as_a_diff("-a new line\n+another new line", STORAGE)
