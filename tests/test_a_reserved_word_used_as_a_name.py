"""A keyword bound as a name must be named as the reason, not left as a line number.

A parser reports where it stopped. When the fault is a reserved word used as an
identifier, where it stopped is the least useful fact available: the token is
legal in most positions, so the message is indistinguishable from a misplaced
brace, and the edit that follows moves the fault to a new line.

Measured on one run's `specialist_testing_1`, eight refusals over four
minutes on `main.js`:

    08:49:06  edit_artifact   Unexpected token 'delete'  on line 57
    08:49:14  edit_artifact   Unexpected token 'delete'  on line 58
    08:49:29  edit_artifact   Unexpected token 'delete'  on line 23
    08:49:42  edit_artifact   Unexpected token 'delete'  on line 20
    08:51:04  replace_lines   Unexpected token 'delete'  on line 21

Five line numbers, one cause. Every refusal was correct - `export const delete`
cannot parse however it is laid out - and none of them said "reserved". The
specialist reached `deleteTask` on its own, which is the right answer, having
spent eight model calls getting there.

The name came from the run's own plan: "implement exported functions: add(task),
edit(id, newTask), delete(id)". The agent was doing as it was told, so the
message says that a document asking for a name does not make the name legal.
"""

from __future__ import annotations

import pytest

from app.analysis.reserved_words import (
    RESERVED,
    a_reserved_name_bound_in,
    language_of,
    why_the_name_cannot_work,
)
from app.analysis.syntax_balance import structural_problem

THE_LINE_THAT_COST_EIGHT_CALLS = """let tasks = [];
export const add = (task) => { tasks.push(task); return task; };
export const edit = (id, newTask) => { return newTask; };
export const delete = (id) => { tasks = tasks.filter(t => t.id !== id); };
export { tasks };
"""


class TestNamingTheWord:
    def test_the_name_that_cost_a_run_eight_calls(self):
        found = a_reserved_name_bound_in("main.js", THE_LINE_THAT_COST_EIGHT_CALLS)

        assert found is not None
        language, name, lines = found
        assert (language, name, lines) == ("JavaScript", "delete", [4])

    def test_the_message_leads_with_the_word_the_parser_never_says(self):
        message = why_the_name_cannot_work("main.js", THE_LINE_THAT_COST_EIGHT_CALLS)

        assert "reserved word in JavaScript" in message
        assert "`delete`" in message

    def test_the_message_says_the_line_is_not_the_problem(self):
        """Five edits went to five different lines. That is what this prevents."""
        message = why_the_name_cannot_work("main.js", THE_LINE_THAT_COST_EIGHT_CALLS)

        assert "moving the code will not help" in message

    def test_the_message_addresses_a_document_that_asked_for_the_name(self):
        """The plan said `delete(id)`, so the agent was obeying it."""
        message = why_the_name_cannot_work("main.js", THE_LINE_THAT_COST_EIGHT_CALLS)

        assert "plan or specification" in message

    @pytest.mark.parametrize("declaration", [
        "function delete(id) {}",
        "export function delete(id) {}",
        "export async function delete(id) {}",
        "const delete = 1;",
        "let delete = 1;",
        "var delete = 1;",
        "class delete {}",
        "export default function delete() {}",
    ])
    def test_every_way_of_binding_it_is_caught(self, declaration):
        assert why_the_name_cannot_work("main.js", declaration) != ""


class TestNotReportingCorrectCode:
    @pytest.mark.parametrize("legal", [
        "class Store { delete(id) {} }",
        "store.delete(id);",
        "const map = { delete: fn };",
        "const deleteTask = (id) => id;",
        "// delete the task\nconst remove = (id) => id;",
        'const x = "delete";',
    ])
    def test_a_reserved_word_that_is_not_a_declaration_is_left_alone(self, legal):
        """JavaScript allows these, and reporting them would be a false refusal.

        `obj.delete()` and a method named `delete` are both legal, so a check
        that matched a bare occurrence would name a fault in working code - which
        is worse than the vague message it replaces.
        """
        assert why_the_name_cannot_work("main.js", legal) == ""

    def test_a_name_that_merely_starts_with_a_keyword_is_not_it(self):
        assert why_the_name_cannot_work("main.js", "const deleteTask = 1;") == ""
        assert why_the_name_cannot_work("main.js", "function classify() {}") == ""

    def test_a_language_with_no_set_says_nothing(self):
        assert why_the_name_cannot_work("Main.java", "void delete() {}") == ""

    def test_a_file_with_no_extension_says_nothing(self):
        assert why_the_name_cannot_work("Makefile", "delete: clean\n") == ""

    def test_empty_content_says_nothing(self):
        assert why_the_name_cannot_work("main.js", "") == ""


class TestPerLanguage:
    def test_the_sets_do_not_agree_and_must_not(self):
        """`delete` is reserved in JavaScript and ordinary in Python."""
        assert "delete" in RESERVED["JavaScript"]
        assert "delete" not in RESERVED["Python"]
        assert "def" in RESERVED["Python"]
        assert "def" not in RESERVED["JavaScript"]

    def test_python_is_covered_by_the_same_helper(self):
        message = why_the_name_cannot_work("app.py", "def class(x):\n    pass\n")

        assert "reserved word in Python" in message

    def test_a_python_function_named_delete_is_fine(self):
        """The whole reason the sets are per language."""
        assert why_the_name_cannot_work("app.py", "def delete(id):\n    pass\n") == ""

    @pytest.mark.parametrize("path, expected", [
        ("main.js", "JavaScript"),
        ("main.mjs", "JavaScript"),
        ("app.tsx", "TypeScript"),
        ("app.py", "Python"),
        ("Main.java", None),
        ("noextension", None),
    ])
    def test_the_language_is_read_off_the_suffix(self, path, expected):
        assert language_of(path) == expected


class TestReachingTheAgent:
    def test_the_python_check_carries_the_reason(self):
        problem = structural_problem("app.py", "def class(x):\n    pass\n")

        assert problem is not None
        assert "reserved word in Python" in problem

    def test_an_ordinary_python_error_is_unchanged(self):
        """Only this one cause gets the extra sentence."""
        problem = structural_problem("app.py", "def f(:\n    pass\n")

        assert problem is not None
        assert "reserved word" not in problem

    def test_valid_python_is_still_valid(self):
        assert structural_problem("app.py", "def f(x):\n    return x\n") is None

    def test_the_javascript_refusal_prefers_it_over_the_bracket_guess(self):
        """`Unexpected token 'delete'` used to be answered with brace advice.

        Checked on the source rather than by running Node, which is not
        guaranteed on a test host. What matters is the order: the certainty
        before the inference.
        """
        import inspect

        from app.analysis import javascript_parse

        source = inspect.getsource(javascript_parse._the_other_half)
        assert source.index("why_the_name_cannot_work") < source.index(
            "_confidently_unbalanced"
        )

    @pytest.mark.parametrize("name", ["class", "function", "return", "typeof"])
    def test_other_javascript_keywords_are_caught_too(self, name):
        """Not a rule about `delete`; a rule about the language's reserved set."""
        assert why_the_name_cannot_work("main.js", f"const {name} = 1;") != ""
