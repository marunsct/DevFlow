"""A `replace_lines` that leaves a JSON file invalid is refused as an edit.

(Unless a comma is all it lost: that is now put right as the edit is applied.
The refusals below are for an edit no comma mends.)

Measured on one run: a fix stage replaced lines 8-9 of `package.json` - the
`test` script and the `},` closing `scripts` - with two scripts and a `}`. The
comma after the brace was lost. The refusal read "Refusing to write ... Send
the file again as complete, valid JSON", naming a line of a file the stage had
never seen, and the stage sent whole-file writes and then tried to delete the
manifest.
"""

from __future__ import annotations

import pytest

from app.tools.repository import RepositoryToolError, replace_approved_lines

MANIFEST = """\
{
  "name": "the-app",
  "scripts": {
    "test": "jest"
  },
  "devDependencies": {
    "jest": "^29.7.0"
  }
}
"""

ONE_COMMA_SHORT = '    "test": "jest",\n    "test:e2e": "playwright test"\n  }'

#: The wrong bracket closing `scripts`: no comma added or taken away mends it.
THE_WRONG_BRACKET = '    "test": "jest",\n    "test:e2e": "playwright test"\n  ],'


def _refusal(tmp_path) -> str:
    (tmp_path / "package.json").write_text(MANIFEST, encoding="utf-8")
    with pytest.raises(RepositoryToolError) as caught:
        replace_approved_lines(tmp_path, "package.json", 4, 5, THE_WRONG_BRACKET)
    assert (tmp_path / "package.json").read_text(encoding="utf-8") == MANIFEST
    return str(caught.value)


def test_it_is_refused_in_the_edit_s_own_words(tmp_path) -> None:
    message = _refusal(tmp_path)

    assert message.startswith("Refusing to change 'package.json'")
    assert "Send the file again" not in message
    assert "Fix `content` and send the edit again" in message


def test_it_shows_the_lines_the_parser_stopped_at(tmp_path) -> None:
    message = _refusal(tmp_path)

    assert ">    6 |   ]," in message
    assert '     7 |   "devDependencies": {' in message


def test_it_shows_what_the_range_held(tmp_path) -> None:
    message = _refusal(tmp_path)

    assert "The lines this edit would have replaced, 4-5, hold:" in message
    assert "     5 |   }," in message


def test_a_line_edit_that_keeps_the_json_valid_is_applied(tmp_path) -> None:
    (tmp_path / "package.json").write_text(MANIFEST, encoding="utf-8")

    result = replace_approved_lines(tmp_path, "package.json", 4, 5, ONE_COMMA_SHORT + ",")

    assert result["status"] == "edited"
    assert '"test:e2e"' in (tmp_path / "package.json").read_text(encoding="utf-8")


def test_the_run_s_own_edit_is_now_applied_with_its_comma(tmp_path) -> None:
    """The edit this file was written about lost one comma and nothing else.
    It is written with the comma put back, and says so - see
    `test_a_json_edit_s_commas_are_put_right`."""
    import json

    (tmp_path / "package.json").write_text(MANIFEST, encoding="utf-8")

    result = replace_approved_lines(tmp_path, "package.json", 4, 5, ONE_COMMA_SHORT)

    written = json.loads((tmp_path / "package.json").read_text(encoding="utf-8"))
    assert written["scripts"] == {"test": "jest", "test:e2e": "playwright test"}
    assert "a comma was added at the end of line 6" in str(result)
