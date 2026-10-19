"""A proven setup keeps every test file where its runner collects it (measured live).

One run's setup stage wrote a unit test outside the declared unit directory. The
unit runner matched nothing and wrote no report, the file was cleared at release
as a throwaway, and the product shipped with no unit test. The stage had also
written the whole product, though it was told to build nothing of it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.stacks import custom_setup

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

DECLARATION = {
    "kind": "http_api",
    "install": [["npm", "install"]],
    "unit_test": ["npx", "jest", "--config", "jest.unit.config.js"],
    "unit_report": "junit-unit.xml",
    "unit_dir": "tests/unit",
    "unit_pattern": "*.test.ts",
    "acceptance_test": ["npx", "jest", "--config", "jest.acceptance.config.js"],
    "acceptance_report": "junit-acceptance.xml",
    "acceptance_dir": "tests/acceptance",
    "acceptance_pattern": "*.test.ts",
    "kept_files": ["jest.unit.config.js"],
    "smoke_files": ["tests/unit/smoke.test.ts", "tests/acceptance/smoke.test.ts"],
}


def _project(root: Path, **changes) -> Path:
    for name in ("jest.unit.config.js", "tests/unit/smoke.test.ts", "tests/acceptance/smoke.test.ts"):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text("x\n")
    (root / custom_setup.DECLARATION_FILE).write_text(json.dumps({**DECLARATION, **changes}))
    return root


def test_a_clean_setup_is_accepted(tmp_path):
    declared, problem = custom_setup.read_declaration(_project(tmp_path))

    assert problem == "" and declared is not None


def test_a_test_file_outside_both_test_directories_is_refused(tmp_path):
    _project(tmp_path)
    (tmp_path / "tests" / "routes.test.ts").write_text("test('x', () => {})\n")

    declared, problem = custom_setup.read_declaration(tmp_path)

    assert declared is None
    assert "`tests/routes.test.ts`" in problem and "no runner ever runs" in problem
    assert not BANNED.search(problem)


def test_a_unit_smoke_test_outside_the_unit_directory_is_refused(tmp_path):
    _project(tmp_path, smoke_files=["tests/smoke.test.ts", "tests/acceptance/smoke.test.ts"])
    (tmp_path / "tests" / "smoke.test.ts").write_text("x\n")

    declared, problem = custom_setup.read_declaration(tmp_path)

    assert declared is None and "must sit in `tests/unit`" in problem


def test_dependencies_are_not_searched_for_tests(tmp_path):
    _project(tmp_path)
    (tmp_path / "node_modules" / "dep").mkdir(parents=True)
    (tmp_path / "node_modules" / "dep" / "own.test.ts").write_text("x\n")

    assert custom_setup.read_declaration(tmp_path)[1] == ""


def test_the_request_asks_for_only_the_smallest_app():
    request = custom_setup.build_setup_request("notes-api", {"language": "TypeScript"}, "http_api")
    text = request["messages"][-1]["content"]

    assert "write only the\nsmallest app the two smoke tests need" in text
    start = text.index("Build nothing of the product itself")
    assert not BANNED.search(text[start:start + 220])
