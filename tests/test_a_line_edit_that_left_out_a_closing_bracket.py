"""A `replace_lines` whose range runs over a closing bracket its content leaves out
is applied to the lines the content replaces.

Measured on one run: `package.json` lines 17-18 held the last devDependency
and the `}` that closed `devDependencies`. The content was that dependency with
a comma, and one new dependency after it - no `}`. The edit was refused for
invalid JSON, the stage was told the range closed one more bracket than its
content, and it sent the same call again, refused the same way.
"""

from __future__ import annotations

import json
import shutil

import pytest

from app.tools.repository import RepositoryToolError, replace_approved_lines

MANIFEST = """\
{
  "name": "app",
  "devDependencies": {
    "jest": "^29.7.0",
    "playwright": "^1.45.0"
  }
}
"""


def test_the_closing_bracket_is_kept(tmp_path) -> None:
    (tmp_path / "package.json").write_text(MANIFEST, encoding="utf-8")
    content = '    "playwright": "^1.45.0",\n    "http-server": "^14.1.1"\n'

    result = replace_approved_lines(
        tmp_path, "package.json", 5, 6, content, expect_start='    "playwright": "^1.45.0"'
    )

    written = json.loads((tmp_path / "package.json").read_text(encoding="utf-8"))
    assert written["devDependencies"] == {
        "jest": "^29.7.0", "playwright": "^1.45.0", "http-server": "^14.1.1",
    }
    assert "Replaced lines 5-5" in result["detail"]
    assert "Kept: }" in result["detail"]


def test_content_that_closes_the_bracket_itself_is_left_to_the_other_rules(tmp_path) -> None:
    (tmp_path / "package.json").write_text(MANIFEST, encoding="utf-8")
    # It closes the bracket, but drops the comma between its two entries.
    content = '    "playwright": "^1.45.0"\n    "http-server": "^14.1.1"\n  }\n'

    result = replace_approved_lines(tmp_path, "package.json", 5, 6, content)

    # The comma repair handles this one; the range is not shortened.
    written = json.loads((tmp_path / "package.json").read_text(encoding="utf-8"))
    assert written["devDependencies"]["http-server"] == "^14.1.1"
    assert "Kept:" not in result["detail"]


def test_an_edit_that_stays_broken_is_still_refused(tmp_path) -> None:
    (tmp_path / "package.json").write_text(MANIFEST, encoding="utf-8")
    content = '    "playwright": "^1.45.0",\n    "http-server": \n'

    with pytest.raises(RepositoryToolError):
        replace_approved_lines(tmp_path, "package.json", 5, 6, content)

    assert (tmp_path / "package.json").read_text(encoding="utf-8") == MANIFEST


@pytest.mark.skipif(shutil.which("node") is None, reason="needs node")
def test_the_same_in_code(tmp_path) -> None:
    source = "export function add(a, b) {\n  return a + b;\n}\n\nexport const x = 1;\n"
    (tmp_path / "math.js").write_text(source, encoding="utf-8")

    result = replace_approved_lines(
        tmp_path, "math.js", 2, 3, "  const sum = a + b;\n  return sum;\n"
    )

    assert (tmp_path / "math.js").read_text(encoding="utf-8") == (
        "export function add(a, b) {\n  const sum = a + b;\n  return sum;\n}\n\nexport const x = 1;\n"
    )
    assert "Kept: }" in result["detail"]
