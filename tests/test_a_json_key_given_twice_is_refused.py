"""A JSON object that gives one key twice is refused, like one that will not parse.

Measured on one run: `package.json` ended with two identical `"jest"` blocks,
after an edit added one that was already there. A parser keeps the last and
says nothing, so the file was accepted every time it was written.
"""

from __future__ import annotations

import pytest

from app.analysis.syntax_balance import structural_problem
from app.tools.repository import RepositoryToolError, write_approved_artifact

TWICE = """{
  "name": "the-app",
  "jest": { "testPathIgnorePatterns": ["<rootDir>/e2e/"] },
  "jest": { "testPathIgnorePatterns": ["<rootDir>/e2e/"] },
  "scripts": { "test": "jest" }
}
"""


def test_it_is_named() -> None:
    problem = structural_problem("the-app/package.json", TWICE)

    assert problem and 'the key "jest" twice' in problem


def test_the_write_is_refused(tmp_path) -> None:
    with pytest.raises(RepositoryToolError) as caught:
        write_approved_artifact(tmp_path, "the-app/package.json", TWICE)

    assert 'the key "jest" twice' in str(caught.value)
    assert not (tmp_path / "the-app" / "package.json").exists()


def test_the_same_key_in_different_objects_is_fine() -> None:
    content = '{"scripts": {"test": "jest"}, "devDependencies": {"test": "^1"}, "a": [{"k": 1}, {"k": 2}]}'

    assert structural_problem("the-app/package.json", content) is None
