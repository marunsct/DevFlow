"""A file a proven setup keeps, which the latest runs report an error in, can be fixed.

One run's setup kept a `tsconfig.json` whose `lib` was a string where the
compiler wants a list. Its smoke tests ran without compiling, so the setup was
proven; the build failed on that file from then on, and every fix that reached
for it was refused as configuration that "already works".
"""

from __future__ import annotations

import json
from pathlib import Path

from app.stacks import contract
from app.stacks.custom_setup import PROVEN_SETUP, pack_from
from app.tools.repository import _the_harness_s_own_or_the_locked_suite

BROKEN = '{\n  "compilerOptions": {\n    "lib": "ES2023"\n  }\n}\n'
SETUP = {
    "kind": "http_api", "language": "typescript", "install": [["npm", "install"]],
    "unit_test": ["node", "--test"], "acceptance_test": ["node", "--test", "tests/acceptance"],
    "unit_report": "test-results/unit.xml", "acceptance_report": "test-results/acceptance.xml",
    "unit_dir": "tests", "acceptance_dir": "tests/acceptance", "unit_pattern": "*.test.ts",
    "acceptance_pattern": "*.test.ts", "kept": {"tsconfig.json": BROKEN, "package.json": "{}\n"},
}


def _workspace(tmp_path: Path, report: str) -> Path:
    pack = pack_from({"pack": PROVEN_SETUP, "setup": SETUP})
    contract.write(tmp_path, pack, "notes-api", "Notes", extra={"setup": json.loads(json.dumps(SETUP))})
    project = tmp_path / "notes-api"
    (project / "test-results").mkdir(parents=True)
    (project / "tsconfig.json").write_text(BROKEN)
    (project / "package.json").write_text("{}\n")
    (project / "test-results" / "acceptance.xml").write_text(report)
    return tmp_path


def test_a_kept_file_the_build_reports_an_error_in_is_released_and_not_put_back(tmp_path):
    root = _workspace(tmp_path, '<failure message="tsconfig.json(6,12): error TS5024: Compiler option '
                                "'lib' requires a value of type Array.\"/>")

    refusal = _the_harness_s_own_or_the_locked_suite(root, root / "notes-api" / "tsconfig.json")

    assert refusal is None
    fixed = '{\n  "compilerOptions": {\n    "lib": ["ES2023"]\n  }\n}\n'
    (root / "notes-api" / "tsconfig.json").write_text(fixed)
    contract.enforce(root)
    assert (root / "notes-api" / "tsconfig.json").read_text() == fixed, "not put back to the broken copy"
    assert _the_harness_s_own_or_the_locked_suite(root, root / "notes-api" / "package.json") is not None


def test_a_kept_file_no_run_reports_an_error_in_stays_kept(tmp_path):
    root = _workspace(tmp_path, '<failure message="src/store.ts(17,26): error TS2554: Expected 1 arguments"/>')

    assert "harness set up and keeps" in _the_harness_s_own_or_the_locked_suite(root, root / "notes-api" / "tsconfig.json")
