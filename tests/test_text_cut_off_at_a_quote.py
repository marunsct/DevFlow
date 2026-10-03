"""Text that stops on a backslash was cut off by the call that carried it.

A double quote written as `\\"` in the call's JSON is a backslash and then the
quote that ends the string, so nothing after it reaches the tool. One run's two
UI stages sent `app.js` fifteen times, every copy ending
`return String(input).replace(/[&<>\\` - the model's `/[&<>"']/g` cut at its
quote - and each was refused as an invalid regular expression. That was true
of the lines that arrived and silent about the rest, so the same call came back
unchanged and the page was never written.
"""

from __future__ import annotations

import pytest

from app.tools.repository import (
    RepositoryToolError,
    edit_approved_artifact,
    replace_approved_lines,
    write_approved_artifact,
)

CUT = (
    "export function escapeHtml(input) {\n"
    "  const map = { '&': '&amp;', '<': '&lt;' };\n"
    "  return String(input).replace(/[&<>\\"
)


def test_a_write_cut_off_names_the_cause(tmp_path) -> None:
    with pytest.raises(RepositoryToolError) as refused:
        write_approved_artifact(tmp_path, "app/app.js", CUT)

    message = str(refused.value)
    assert "ends with a backslash, partway through line 3" in message
    assert "replace(/[&<>\\" in message
    assert "Nothing after that reached the tool" in message
    assert not (tmp_path / "app" / "app.js").exists()


def test_an_edit_cut_off_names_the_cause(tmp_path) -> None:
    write_approved_artifact(tmp_path, "app/app.js", "export const a = 1;\n")

    with pytest.raises(RepositoryToolError, match="ends with a backslash"):
        replace_approved_lines(tmp_path, "app/app.js", 1, 1, "export const a = '\\")
    with pytest.raises(RepositoryToolError, match="ends with a backslash"):
        edit_approved_artifact(tmp_path, "app/app.js", "export const a = 1;", "export const a = '\\")

    assert (tmp_path / "app" / "app.js").read_text(encoding="utf-8") == "export const a = 1;\n"


@pytest.mark.parametrize("content", [
    "export const pattern = /[&<>\"']/g;\n",
    "export const path = 'C:\\\\temp\\\\';\n",
    "run: \\\n  make all\n",
])
def test_complete_text_with_backslashes_is_written(tmp_path, content: str) -> None:
    write_approved_artifact(tmp_path, "app/notes.txt", content)

    assert (tmp_path / "app" / "notes.txt").read_text(encoding="utf-8") == content
