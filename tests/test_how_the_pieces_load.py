"""The one cross-cutting choice the stack does not record.

The stack decides the language, the framework, the database and the test
runner. It does not decide how a module is loaded, and nothing else does
either - the specification is silent on it in every stored run but one. So each
specialist chooses alone: the page gets a plain `<script>` tag, the application
file gets `export`, the suite gets `import`, and the three do not agree.

That disagreement is the most expensive recurring failure in this harness. Five
separate cross-file checks exist to catch its shapes, and runs 0c5aabdb,
d6297b2f, 0afef410, 7e960f06, 1ae7671d and 551640d3 each spent rounds on it.

What is stated is not a preference. Both combinations work and a stage may pick
either; what cannot work is picking differently in three files.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agents.specialists import describe_stack


def _stack(**kwargs) -> SimpleNamespace:
    base = {
        "language": "JavaScript",
        "framework": "Vanilla JS",
        "database": "localStorage",
        "testing_framework": "node --test",
        "additional_tools": [],
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_a_javascript_stack_is_told_the_choice_is_shared():
    note = describe_stack(_stack())

    assert "one choice, not three" in note
    assert "The page, the application file and the tests must share it" in note


def test_both_working_combinations_are_named():
    """Neither is prescribed - a stage may pick either, and run 1ae7671d did."""
    note = describe_stack(_stack())

    assert 'script type="module"' in note
    assert "module.exports" in note
    assert "`require` it" in note


def test_it_says_why_the_tests_will_not_catch_it():
    """Both mixtures throw on page load while the suite stays green."""
    note = describe_stack(_stack())

    assert "the tests still pass" in note
    assert "never open the page" in note


@pytest.mark.parametrize("language", ["TypeScript", "javascript", "JavaScript (ES6+)"])
def test_every_spelling_of_a_module_language_gets_it(language: str):
    assert "one choice, not three" in describe_stack(_stack(language=language))


@pytest.mark.parametrize("language", ["Python", "Go", "Ruby"])
def test_a_language_without_this_problem_is_not_told_about_it(language: str):
    assert "one choice, not three" not in describe_stack(_stack(language=language))


def test_no_stack_recorded_is_unchanged():
    assert describe_stack(None) == ""


def test_the_existing_stack_lines_survive():
    note = describe_stack(_stack())

    assert "- Language: JavaScript" in note
    assert "- Testing framework: node --test" in note
    assert "Build on exactly this" in note
