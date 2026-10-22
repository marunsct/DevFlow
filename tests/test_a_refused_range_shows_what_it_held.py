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


SUITE_END = """\
describe('filter', () => {
  it('keeps active', () => {
    expect(1).toBe(1);
  });
});
"""


def test_content_that_drops_the_line_it_meant_to_follow_is_named(tmp_path) -> None:
    """One run meant to append blocks after a file's last `});` and replaced
    that line with them instead; the refusal quoted `});`, and the same edit
    came again before the model saw its content no longer held it."""
    (tmp_path / "app.test.js").write_text(SUITE_END, encoding="utf-8")

    with pytest.raises(RepositoryToolError) as refused:
        replace_approved_lines(
            tmp_path, "app.test.js", 5, 5, "\ndescribe('more', () => {\n  it('x', () => {});\n});"
        )

    message = " ".join(str(refused.value).split())
    assert "Those lines close 2 more brackets than your `content` does" in message
    assert "`replace_lines` has no insert mode: to add after line 5, begin `content` with that line" in message


def test_content_that_leaves_a_line_out_entirely_is_named(tmp_path) -> None:
    (tmp_path / "app.test.js").write_text(SUITE_END, encoding="utf-8")

    with pytest.raises(RepositoryToolError) as refused:
        replace_approved_lines(tmp_path, "app.test.js", 2, 4, "  it('keeps active', () => {")

    message = " ".join(str(refused.value).split())
    assert "Those lines" in message or "does not contain" in message
