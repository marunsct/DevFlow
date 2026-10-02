"""A finding that test-only packages break the brief does not send a sprint back.

Whether a product breaks a brief's rule on dependencies is decided on disk and
handed to the reviewer as a fact. One run's request said "declares no product
dependencies; `@playwright/test`, `jest` are devDependencies used for testing
only ... it is not a finding", and the reviewer returned "[blocking]
package.json declares devDependencies (jsdom, jest, @playwright/test) which
violate the brief ... Remove all devDependencies" - the runners this run's own
stack had chosen. It was the last revision allowed, and the run ended on it.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.graph.workflow import _findings_the_dependency_check_contradicts

BRIEF = "## Technical Constraints\n- No external dependencies beyond basic HTML/CSS/JS\n"

AS_THE_REVIEWER_WROTE_IT = (
    "package.json declares devDependencies (jsdom, jest, @playwright/test) which violate "
    "the brief's \"No external dependencies beyond basic HTML/CSS/JS\" requirement."
)


class _Finding(SimpleNamespace):
    def model_copy(self, update):
        return _Finding(**{**self.__dict__, **update})


class _Review(SimpleNamespace):
    def model_copy(self, update):
        return _Review(**{**self.__dict__, **update})


def _state(root: Path, manifest: dict, brief: str = BRIEF, files: dict | None = None) -> dict:
    project = root / "app"
    project.mkdir(exist_ok=True)
    (project / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    (project / "app.js").write_text("export const a = 1;\n", encoding="utf-8")
    for name, content in (files or {}).items():
        (project / name).write_text(content, encoding="utf-8")
    return {
        "document": SimpleNamespace(text=brief),
        "repository": SimpleNamespace(root_path=str(root)),
    }


TEST_ONLY = {"name": "app", "devDependencies": {"jest": "^29", "@playwright/test": "^1"}}


def _after(state, *descriptions, severity="blocking"):
    review = _Review(findings=[_Finding(severity=severity, description=d) for d in descriptions])
    return _findings_the_dependency_check_contradicts(review, state)


def test_the_finding_is_kept_and_stops_gating(tmp_path: Path) -> None:
    after = _after(_state(tmp_path, TEST_ONLY), AS_THE_REVIEWER_WROTE_IT, "Editing a task does nothing.")

    assert [finding.severity for finding in after.findings] == ["minor", "blocking"]
    assert "does not hold as written" in after.findings[0].description
    assert AS_THE_REVIEWER_WROTE_IT in after.findings[0].description


def test_a_dependency_the_product_ships_is_the_reviewer_s_to_raise(tmp_path: Path) -> None:
    shipped = {"name": "app", "dependencies": {"express": "^4"}}

    after = _after(_state(tmp_path, shipped), "package.json declares the dependency express, which violates the brief.")

    assert [finding.severity for finding in after.findings] == ["blocking"]


def test_a_test_package_the_product_imports_is_a_real_violation(tmp_path: Path) -> None:
    state = _state(tmp_path, {"name": "app", "devDependencies": {"lodash": "^4"}},
                   files={"main.js": "import _ from 'lodash';\nexport const b = _.noop;\n"})

    after = _after(state, "package.json devDependencies violate the brief's rule on dependencies.")

    assert [finding.severity for finding in after.findings] == ["blocking"]


@pytest.mark.parametrize("description", [
    "The form never calls addTask, so no task can be added.",
    "The page depends on a listener that is never attached.",
    "package.json declares devDependencies but has no test script.",
])
def test_a_finding_about_anything_else_is_left_alone(tmp_path: Path, description: str) -> None:
    after = _after(_state(tmp_path, TEST_ONLY), description)

    assert [finding.severity for finding in after.findings] == ["blocking"]
    assert after.findings[0].description == description


def test_a_finding_that_already_does_not_gate_is_not_rewritten(tmp_path: Path) -> None:
    after = _after(_state(tmp_path, TEST_ONLY), AS_THE_REVIEWER_WROTE_IT, severity="minor")

    assert after.findings[0].description == AS_THE_REVIEWER_WROTE_IT


def test_a_brief_with_no_such_rule_changes_nothing(tmp_path: Path) -> None:
    state = _state(tmp_path, TEST_ONLY, brief="Build a to-do list.")

    after = _after(state, AS_THE_REVIEWER_WROTE_IT)

    # Nothing forbids dependencies, so nothing is violated - and the finding
    # says something is. It does not hold either way.
    assert [finding.severity for finding in after.findings] == ["minor"]
