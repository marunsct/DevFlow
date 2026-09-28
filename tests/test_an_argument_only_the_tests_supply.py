"""A required parameter the suite always passes and the product never does.

The signature of code that was unit-tested and never wired. A module written to
take its collaborator as an argument is testable by construction - the suite
hands it a fake and every case passes - and the application is the one caller
that has to hand it the real thing.

Found on one run of 2026-09-20. `app-logic.mjs` exported

    export function addTaskAndPersist(title, description = '', storage)

`app-logic.test.mjs` called `appLogic.addTaskAndPersist('New Task', 'desc',
storage)` with a mock and passed. `index.html` called
`addTaskAndPersist(title, description)`, so `storage` was `undefined` on every
path a user could reach: `saveTasks(tasks, undefined)` reached
`undefined.setItem` and threw. `loadPersistedTasks()` took the quieter path -
`loadTasks(undefined)` throws inside a `try` that returns `[]` - so the page
simply never restored anything.

The brief's acceptance criteria required "Tasks persist between page refreshes".
That product never wrote a byte, and its suite was green.

No reviewer caught it either. The security review and the milestone review both
dissected the import clause of the same file in the same sprint without once
mentioning `storage`, and the milestone review's acceptance evidence praised the
"mock-storage adapter pattern" and "thorough test coverage of the data layer" -
the arrangement that hid it. When the imports were later fixed,
`loadPersistedTasks(localStorage)` was corrected and all three write paths were
left as they were, so the product could read a saved list and never write one.
"""

from __future__ import annotations

import pytest

from app.analysis.integration_checks import (
    _argument_counts,
    _namespace_bindings,
    _only_the_code,
    _required_arguments_only_the_tests_supply,
    _source_files,
    _split_at_top_level,
    _without_comments,
)

MODULE = """
export function addTaskAndPersist(title, description = '', storage) {
  storage.setItem('tasks', title + description);
}
export function loadPersistedTasks(storage) {
  return storage.getItem('tasks');
}
"""

SUITE = """
import * as appLogic from './app-logic.mjs';
import { test } from 'node:test';

test('adds', () => {
  const storage = { setItem() {}, getItem() { return null; } };
  appLogic.addTaskAndPersist('New Task', 'desc', storage);
  appLogic.loadPersistedTasks(storage);
});
"""


def _problems(root):
    return _required_arguments_only_the_tests_supply(_source_files(root), root)


def _page(body: str) -> str:
    return (
        "<!doctype html><html><body>\n"
        '<script type="module">\n' + body + "\n</script>\n</body></html>\n"
    )


@pytest.fixture
def site(tmp_path):
    (tmp_path / "app-logic.mjs").write_text(MODULE)
    (tmp_path / "app-logic.test.mjs").write_text(SUITE)
    return tmp_path


def test_the_exact_product_that_shipped_without_storage(site):
    (site / "index.html").write_text(_page("""
    import { addTaskAndPersist, loadPersistedTasks } from './app-logic.mjs';
    loadPersistedTasks();
    addTaskAndPersist('a', 'b');
    """))

    problems = _problems(site)
    assert len(problems) == 2, problems
    joined = "\n".join(problems)
    assert "`storage` parameter has no default" in joined
    # The counts must be exact: they are the evidence.
    assert "calls it with 0 arguments" in joined
    assert "calls it with 2 arguments" in joined
    assert "index.html" in joined


def test_a_product_that_passes_the_argument_is_silent(site):
    (site / "index.html").write_text(_page("""
    import { addTaskAndPersist, loadPersistedTasks } from './app-logic.mjs';
    loadPersistedTasks(localStorage);
    addTaskAndPersist('a', 'b', localStorage);
    """))
    assert _problems(site) == []


def test_a_parameter_with_a_default_is_never_undefined(tmp_path):
    (tmp_path / "app-logic.mjs").write_text(
        "export function save(task, storage = localStorage) {\n"
        "  storage.setItem('t', task);\n}\n"
    )
    (tmp_path / "app-logic.test.mjs").write_text(
        "import * as appLogic from './app-logic.mjs';\n"
        "appLogic.save('x', { setItem() {} });\n"
    )
    (tmp_path / "index.html").write_text(_page(
        "import { save } from './app-logic.mjs';\nsave('x');"
    ))
    assert _problems(tmp_path) == []


def test_it_stays_quiet_when_the_suite_does_not_pass_it_either(tmp_path):
    """The narrowing that keeps this honest.

    If nobody ever supplies the argument, the parameter may simply be
    vestigial. What makes the one run case unambiguous is that the suite
    *does* supply it: the parameter is wanted, it is exercised, and only the
    product forgot it.
    """
    (tmp_path / "app-logic.mjs").write_text(
        "export function save(task, unused) { return task; }\n"
    )
    (tmp_path / "app-logic.test.mjs").write_text(
        "import * as appLogic from './app-logic.mjs';\nappLogic.save('x');\n"
    )
    (tmp_path / "index.html").write_text(_page(
        "import { save } from './app-logic.mjs';\nsave('x');"
    ))
    assert _problems(tmp_path) == []


def test_a_spread_call_concludes_nothing(site):
    """`f(...args)` has no knowable argument count, so it must not be judged."""
    (site / "index.html").write_text(_page("""
    import { addTaskAndPersist, loadPersistedTasks } from './app-logic.mjs';
    const args = ['a', 'b', localStorage];
    loadPersistedTasks(...args);
    addTaskAndPersist(...args);
    """))
    assert _problems(site) == []


def test_a_commented_out_call_is_not_a_call(site):
    (site / "index.html").write_text(_page("""
    import { addTaskAndPersist, loadPersistedTasks } from './app-logic.mjs';
    // loadPersistedTasks();
    loadPersistedTasks(localStorage);
    addTaskAndPersist('a', 'b', localStorage);
    """))
    assert _problems(site) == []


class TestCountingArguments:
    """The counter is the evidence, so it is tested on its own."""

    def _count(self, source: str, name: str) -> list[int]:
        return _argument_counts(
            _only_the_code(source), name,
            _namespace_bindings(source), _without_comments(source),
        )

    def test_blanked_string_literals_are_still_arguments(self):
        """The defect that made this check silent on the run that motivated it.

        `_only_the_code` empties string literals. Counting the pieces that are
        left read a three-argument call as one, and the comparison it exists to
        make never happened.
        """
        assert self._count("f('New Task', 'desc', storage);", "f") == [3]

    def test_a_comma_inside_a_string_does_not_split_an_argument(self):
        assert self._count("f('a, b', c);", "f") == [2]

    def test_a_bracket_inside_a_string_does_not_close_the_call(self):
        assert self._count("f('a)b', c);", "f") == [2]

    def test_an_escaped_quote_does_not_end_the_string(self):
        assert self._count(r"f('a\'b, c', d);", "f") == [2]

    def test_no_arguments_counts_as_none(self):
        assert self._count("f();", "f") == [0]

    def test_nested_calls_count_once_at_the_top_level(self):
        assert self._count("f(g(a, b), c);", "f") == [2]

    def test_an_object_literal_is_one_argument(self):
        assert self._count("f({ a: 1, b: 2 }, c);", "f") == [2]

    def test_a_member_call_needs_a_namespace_receiver(self):
        """`storage.getItem(x)` is not a call of an exported `getItem`."""
        assert self._count("storage.getItem('t');", "getItem") == []
        source = (
            "import * as appLogic from './m.mjs';\nappLogic.getItem('t', s);\n"
        )
        assert self._count(source, "getItem") == [2]

    def test_an_unclosed_call_is_skipped_rather_than_half_read(self):
        assert self._count("f(a, b", "f") == []


class TestSplitting:
    def test_a_trailing_comma_leaves_an_empty_final_piece(self):
        """Documented, not silently absorbed: it overcounts by one, and an
        overcount can only ever make this check quieter, never wrong."""
        assert len(_split_at_top_level("a, b,")) == 3

    def test_an_empty_list_has_no_pieces(self):
        assert _split_at_top_level("") == []
        assert _split_at_top_level("   ") == []
