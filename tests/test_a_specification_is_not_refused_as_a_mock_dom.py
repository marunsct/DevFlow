"""Non-test files (such as specifications) are not warned or refused as hand-built DOMs.

Measured on one run: the technical specification in `docs/technical_specification.md`
contained an example snippet referencing `node:test` and `global.document`.
Because `a_dom_built_by_hand` did not verify that the target was an actual test file,
it counted DOM warnings against `docs/technical_specification.md`. After two warnings,
`_refuse_a_hand_built_dom_again` raised `RepositoryToolError`, causing `_record_document`
to fail to write the approved specification to disk.
"""

from __future__ import annotations

from pathlib import Path
import pytest

from app.analysis.test_discovery import a_dom_built_by_hand
from app.tools.repository import (
    RepositoryToolError,
    _refuse_a_hand_built_dom_again,
    write_approved_artifact,
)
from app.tools.seen_content import (
    MOCK_DOM_WARNINGS_BEFORE_REFUSING,
    record_mock_dom_warning,
    times_warned_about_a_mock_dom,
)

SNIPPET_WITH_TEST_IMPORT = """# Specification
## Testing Strategy
Example unit test:
```javascript
import { test } from 'node:test';
global.document = { getElementById: (id) => ({ innerHTML: '' }) };
test('renders', () => {});
```
"""


@pytest.fixture(autouse=True)
def _a_fresh_stage():
    from app.tools import seen_content

    seen_content.forget_everything()
    yield
    seen_content.forget_everything()


def test_specification_is_not_flagged_as_hand_built_dom() -> None:
    assert a_dom_built_by_hand("docs/technical_specification.md", SNIPPET_WITH_TEST_IMPORT) is None


def test_specification_is_not_refused_after_mock_dom_warnings() -> None:
    for _ in range(MOCK_DOM_WARNINGS_BEFORE_REFUSING + 2):
        record_mock_dom_warning("docs/technical_specification.md")

    # Must not raise RepositoryToolError
    _refuse_a_hand_built_dom_again("docs/technical_specification.md", SNIPPET_WITH_TEST_IMPORT)


def test_workflow_approved_artifact_is_not_refused_as_mock_dom(tmp_path: Path) -> None:
    for _ in range(MOCK_DOM_WARNINGS_BEFORE_REFUSING + 2):
        record_mock_dom_warning("docs/technical_specification.md")

    write_approved_artifact(
        tmp_path,
        "docs/technical_specification.md",
        SNIPPET_WITH_TEST_IMPORT,
        by_the_workflow=True,
    )
    written = (tmp_path / "docs" / "technical_specification.md").read_text(encoding="utf-8")
    assert "Example unit test" in written

