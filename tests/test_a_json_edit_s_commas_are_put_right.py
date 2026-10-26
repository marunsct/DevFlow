"""An edit that leaves JSON invalid only for its commas is written with them put right.

A line edit to a JSON file changes which member is last: the old last one needs
a comma it did not have, or the new last one has a comma it must not have.

Measured on one run, by reading every failed call: 13 of 24 were edits to
`package.json`, by four stages, each adding one dependency or changing the test
script. It was the most expensive file in every run audited that day.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.analysis.syntax_balance import json_with_its_commas_put_right
from app.tools.repository import (
    RepositoryToolError,
    edit_approved_artifact,
    replace_approved_lines,
    write_approved_artifact,
)

MANIFEST = (
    '{\n'
    '  "name": "app",\n'
    '  "type": "module",\n'
    '  "scripts": {\n'
    '    "test": "jest"\n'
    '  },\n'
    '  "devDependencies": {\n'
    '    "jest": "^29.7.0"\n'
    '  }\n'
    '}\n'
)


def _manifest(root: Path) -> Path:
    write_approved_artifact(root, "app/package.json", MANIFEST)
    return root / "app" / "package.json"


def test_a_dependency_added_after_the_last_one_gets_the_comma_before_it(tmp_path: Path) -> None:
    """As the run's stages sent it: the new line, and nothing about the old one."""
    target = _manifest(tmp_path)

    result = replace_approved_lines(
        tmp_path, "app/package.json", 8, 8,
        '    "jest": "^29.7.0"\n    "jest-environment-jsdom": "^29.7.0"\n',
    )

    written = json.loads(target.read_text(encoding="utf-8"))
    assert written["devDependencies"] == {"jest": "^29.7.0", "jest-environment-jsdom": "^29.7.0"}
    assert "a comma was added at the end of line 8" in str(result)
    assert "every member but the last" in str(result)


def test_a_find_and_replace_edit_is_put_right_the_same_way(tmp_path: Path) -> None:
    target = _manifest(tmp_path)

    result = edit_approved_artifact(
        tmp_path, "app/package.json",
        '    "jest": "^29.7.0"\n', '    "jest": "^29.7.0",\n    "@playwright/test": "^1.48.0",\n',
    )

    written = json.loads(target.read_text(encoding="utf-8"))
    assert "@playwright/test" in written["devDependencies"]
    assert "the comma at the end of line 9 was removed" in str(result)


def test_a_whole_file_with_a_comma_missing_is_written_with_it(tmp_path: Path) -> None:
    result = write_approved_artifact(
        tmp_path, "app/package.json", MANIFEST.replace('"type": "module",', '"type": "module"'),
    )

    assert json.loads((tmp_path / "app" / "package.json").read_text(encoding="utf-8"))["type"] == "module"
    assert "a comma was added at the end of line 3" in str(result)


def test_valid_json_is_not_touched() -> None:
    assert json_with_its_commas_put_right(MANIFEST) is None


@pytest.mark.parametrize("broken", [
    # A key with no colon: not a comma's fault.
    '{"a": 1 "b" 2}',
    # Putting the comma in would give the same key twice.
    '{\n  "a": 1\n  "a": 2\n}\n',
    # An unclosed object.
    '{\n  "a": 1,\n  "b": {\n',
    # A value missing altogether.
    '{"a": }',
])
def test_anything_else_is_still_refused(tmp_path: Path, broken: str) -> None:
    assert json_with_its_commas_put_right(broken) is None
    with pytest.raises(RepositoryToolError):
        write_approved_artifact(tmp_path, "app/package.json", broken)


def test_an_edit_that_breaks_more_than_commas_changes_nothing(tmp_path: Path) -> None:
    target = _manifest(tmp_path)

    with pytest.raises(RepositoryToolError):
        replace_approved_lines(tmp_path, "app/package.json", 8, 8, '    "jest" "^29.7.0"\n')

    assert target.read_text(encoding="utf-8") == MANIFEST


def test_a_file_that_allows_comments_is_left_to_its_own_reader(tmp_path: Path) -> None:
    content = '{\n  // comments are allowed here\n  "compilerOptions": {"strict": true,}\n}\n'

    write_approved_artifact(tmp_path, "app/tsconfig.json", content)

    assert (tmp_path / "app" / "tsconfig.json").read_text(encoding="utf-8") == content


def test_a_trailing_comma_is_removed_whichever_way_the_parser_words_it():
    """Python 3.12 says "Expecting property name"; 3.13 and later "Illegal trailing comma" and point at the comma."""
    from app.analysis.syntax_balance import json_with_its_commas_put_right

    fixed = json_with_its_commas_put_right('{\n  "a": 1,\n  "b": [1, 2,],\n}\n')

    assert fixed is not None
    import json

    assert json.loads(fixed[0]) == {"a": 1, "b": [1, 2]}
