"""A `replace_lines` edit refused as unparseable shows what its range held.

One run's `specialist_documentation_3`, in parallel mode, sent lines 127-130
from a read that another stage's edit had since moved. The range now ended on
the first line of `filterTasks`, so the header went and the body stayed. The
refusal said "Illegal return statement" and quoted the result - never the text
the edit would remove, which is what shows the range was stale.
"""

from __future__ import annotations

import shutil

import pytest

from app.tools.repository import RepositoryToolError, replace_approved_lines

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs node")

APP = """\
// module state
let currentFilter = 'all';

export function filterTasks(tasks, status) {
  if (status === 'all') return tasks;
  return tasks.filter((t) => (status === 'active' ? !t.completed : t.completed));
}
"""


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "app.js").write_text(APP, encoding="utf-8")
    return tmp_path


def _refusal(workspace, **extra) -> str:
    with pytest.raises(RepositoryToolError) as caught:
        # Meant to replace the two state lines; the range reaches the header.
        replace_approved_lines(
            workspace, "app.js", 1, 4, "// module state\nlet currentFilter = 'all';\n", **extra
        )
    return str(caught.value)


def test_the_refusal_quotes_the_lines_it_would_have_removed(workspace) -> None:
    message = _refusal(workspace)

    assert "would have replaced, 1-4" in message
    assert "export function filterTasks(tasks, status) {" in message


def test_it_names_the_way_to_pin_the_range(workspace) -> None:
    assert "`expect_start` and `expect_end`" in _refusal(workspace)


def test_nothing_was_written(workspace) -> None:
    _refusal(workspace)

    assert (workspace / "app.js").read_text(encoding="utf-8") == APP
