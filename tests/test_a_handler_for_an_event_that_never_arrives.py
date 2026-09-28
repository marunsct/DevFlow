"""Event delegation for an event that does not bubble is dead code.

Delegation works because the event travels from the child up to the container.
`blur`, `focus`, `mouseenter` and `mouseleave` do not bubble, so a delegated
handler for one of them is never called - and nothing throws, no test fails, and
the feature is simply absent.

Measured on one run, which failed at the milestone revision limit. Its
`task-manager/app.js` line 151 held

    listContainer.addEventListener('blur', e => { ... e.target ... })

for inline editing, and the milestone reviewer found it:

    [blocking] correctness: The blur-based save for inline editing is still
    broken ... the `blur` event does not bubble in the DOM event flow. When a user
    clicks outside or tabs away from the inline edit input, the blur fires on the
    input element itself and never reaches `listContainer`, so the handler never
    executes and changes are silently lost.

Three revisions later the run stopped. The reviewer read it correctly; nothing in
the harness could.

Run against all 77 stored workspaces this finds exactly that one occurrence and
nothing else.
"""

from __future__ import annotations

import pytest

from app.analysis.integration_checks import (
    _a_delegated_handler_for_an_event_that_does_not_bubble as _delegated,
    _severity_of,
    _source_files,
)

#: One run's shape, reduced.
THE_DEAD_HANDLER = """export function init() {
  const listContainer = document.getElementById('task-list');
  listContainer.addEventListener('blur', e => {
    const li = e.target.closest('li');
    if (li) { save(li); }
  });
}
"""


@pytest.fixture
def a_project(tmp_path):
    def _build(script: str, name: str = "app.js"):
        project = tmp_path / "app"
        project.mkdir(exist_ok=True)
        (project / name).write_text(script)
        return tmp_path

    return _build


class TestTheHandlerThatCostRunF05d8d47:
    def test_it_is_reported(self, a_project):
        root = a_project(THE_DEAD_HANDLER)

        problems = _delegated(_source_files(root), root)

        assert len(problems) == 1, problems
        assert "`blur` does not bubble" in problems[0]

    def test_it_names_the_line(self, a_project):
        root = a_project(THE_DEAD_HANDLER)

        assert "line 3" in _delegated(_source_files(root), root)[0]

    def test_it_names_the_container(self, a_project):
        root = a_project(THE_DEAD_HANDLER)

        assert "`listContainer`" in _delegated(_source_files(root), root)[0]

    def test_it_offers_the_bubbling_counterpart(self, a_project):
        root = a_project(THE_DEAD_HANDLER)

        assert "Use `focusout`" in _delegated(_source_files(root), root)[0]

    def test_it_offers_the_other_fix_too(self, a_project):
        """Attaching to the input itself is equally correct and sometimes simpler."""
        root = a_project(THE_DEAD_HANDLER)

        assert "attach the `blur` handler to the element itself" in (
            _delegated(_source_files(root), root)[0]
        )

    def test_it_says_nothing_will_report_it(self, a_project):
        root = a_project(THE_DEAD_HANDLER)

        assert "nothing throws, no test fails" in _delegated(_source_files(root), root)[0]

    def test_it_blocks(self, a_project):
        """A handler that never runs is a feature that does not work."""
        from app.analysis.integration_checks import _CHECKS, _floor_of

        entry = next(e for e in _CHECKS if "do not bubble" in e[0])

        assert _floor_of(entry) == "BREAKS"


class TestEveryEventThatDoesNotBubble:
    @pytest.mark.parametrize(
        "event,instead",
        [("blur", "focusout"), ("focus", "focusin"),
         ("mouseenter", "mouseover"), ("mouseleave", "mouseout")],
    )
    def test_each_one_is_caught_with_its_replacement(self, a_project, event, instead):
        root = a_project(
            "const box = document.getElementById('box');\n"
            f"box.addEventListener('{event}', e => {{ e.target.closest('li'); }});\n"
        )

        problems = _delegated(_source_files(root), root)

        assert len(problems) == 1
        assert f"`{event}` does not bubble" in problems[0]
        assert f"Use `{instead}`" in problems[0]


class TestWhatMustStaySilent:
    def test_a_handler_that_does_not_delegate(self, a_project):
        """A `blur` on the input itself is correct and common."""
        root = a_project(
            "const input = document.createElement('input');\n"
            "input.addEventListener('blur', () => { save(input.value); });\n"
        )

        assert _delegated(_source_files(root), root) == []

    def test_a_bubbling_event_with_delegation(self, a_project):
        """`click` bubbles, so delegation is exactly right."""
        root = a_project(
            "list.addEventListener('click', e => { e.target.closest('li'); });\n"
        )

        assert _delegated(_source_files(root), root) == []

    def test_focusout_is_the_fix_and_must_not_be_reported(self, a_project):
        root = a_project(
            "list.addEventListener('focusout', e => { e.target.closest('li'); });\n"
        )

        assert _delegated(_source_files(root), root) == []

    def test_a_test_file_is_not_the_product(self, a_project):
        """A suite may dispatch a non-bubbling event deliberately."""
        root = a_project(
            "list.addEventListener('blur', e => { e.target.closest('li'); });\n",
            name="app.test.mjs",
        )

        assert _delegated(_source_files(root), root) == []

    def test_one_handler_is_not_read_as_another(self, a_project):
        """The window stops at the next listener, so a later `.target` does not
        implicate an earlier non-bubbling handler."""
        root = a_project(
            "input.addEventListener('blur', () => { save(); });\n"
            "list.addEventListener('click', e => { e.target.closest('li'); });\n"
        )

        assert _delegated(_source_files(root), root) == []

    def test_a_workspace_with_no_scripts(self, tmp_path):
        assert _delegated([], tmp_path) == []


class TestASuiteRegisteredTwice:
    """Both copies run, so the count every gate reads is inflated.

    One run's `app.test.mjs` declares `describe('editTask', ...)` at lines
    167 and 245; its reviewer found it. Sweeping the stored workspaces found a
    second nobody reported: one run's `todo-app/app.test.mjs` registers
    `filterTasks` at lines 401 and 527.
    """

    def _problems(self, tmp_path, source, name="app.test.mjs"):
        from app.analysis.integration_checks import _a_suite_registered_twice

        project = tmp_path / "app"
        project.mkdir(exist_ok=True)
        (project / name).write_text(source)
        return _a_suite_registered_twice(_source_files(tmp_path), tmp_path)

    def test_a_repeated_describe_is_reported(self, tmp_path):
        source = (
            "describe('createTask', () => { it('a', () => {}); });\n"
            "describe('editTask', () => { it('b', () => {}); });\n"
            "describe('editTask', () => { it('c', () => {}); });\n"
        )

        problems = self._problems(tmp_path, source)

        assert len(problems) == 1
        assert "`editTask` 2 times" in problems[0]

    def test_the_line_numbers_are_the_real_ones(self, tmp_path):
        """`\\s*` matched the preceding newline and every number came out low."""
        source = "\n\ndescribe('editTask', () => {});\n\ndescribe('editTask', () => {});\n"

        problems = self._problems(tmp_path, source)

        assert "lines 3, 5" in problems[0]

    def test_it_says_the_count_is_inflated(self, tmp_path):
        source = "describe('x', () => {});\ndescribe('x', () => {});\n"

        assert "case count every gate in this pipeline reads is inflated" in (
            self._problems(tmp_path, source)[0]
        )

    def test_distinct_suites_are_silent(self, tmp_path):
        source = (
            "describe('createTask', () => {});\n"
            "describe('editTask', () => {});\n"
            "describe('deleteTask', () => {});\n"
        )

        assert self._problems(tmp_path, source) == []

    def test_an_indented_suite_counts(self, tmp_path):
        source = "describe('outer', () => {\n  describe('inner', () => {});\n});\ndescribe('inner', () => {});\n"

        problems = self._problems(tmp_path, source)

        assert "`inner` 2 times" in problems[0]

    def test_playwright_test_describe_counts(self, tmp_path):
        source = (
            "test.describe('editing', () => {});\n"
            "test.describe('editing', () => {});\n"
        )

        assert "`editing` 2 times" in self._problems(tmp_path, source, "app.spec.ts")[0]

    def test_a_product_file_is_not_a_suite(self, tmp_path):
        source = "describe('x', () => {});\ndescribe('x', () => {});\n"

        assert self._problems(tmp_path, source, name="app.js") == []

    def test_three_copies_are_all_named(self, tmp_path):
        source = "describe('x', () => {});\n" * 3

        problems = self._problems(tmp_path, source)

        assert "`x` 3 times" in problems[0]
        assert "lines 1, 2, 3" in problems[0]
