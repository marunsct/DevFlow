"""The milestone reviewer checks an "every action" criterion per action.

One run's final review accepted "Keyboard accessibility - all interactive
elements have tabindex=0, aria-labels, Enter/Space handlers" while editing a
task could only be started by clicking a title that could not take focus. The
same review missed that the add form refused a description over 1000
characters and the edit path accepted one.
"""
import re

from app.agents.milestone_reviewer import _SYSTEM_PROMPT


def test_the_reviewer_lists_each_capability_for_an_every_capability_criterion():
    assert "checked capability by capability" in _SYSTEM_PROMPT
    assert "evidence about some entry points is not evidence about\n  the others" in _SYSTEM_PROMPT


def test_the_reviewer_compares_every_path_that_changes_a_value():
    assert "must hold on\n  every other path that sets the same value" in _SYSTEM_PROMPT


def test_the_rules_name_no_language_framework_interface_or_product():
    """The workflow builds any product in any stack; these rules must fit all."""
    rules = _SYSTEM_PROMPT[_SYSTEM_PROMPT.index("checked capability by capability") - 400:
                           _SYSTEM_PROMPT.index("Treat the executed-command record")]
    for word in ("JavaScript", "Python", "React", "tabindex", "DOM", "Playwright",
                 "HTML", "button", "form", "keyboard", "click", "focus", "task"):
        assert not re.search(rf"\b{word}s?\b", rules, re.I), word


def test_the_test_round_rule_names_no_interface_or_product():
    import inspect

    from app.agents import specialists

    source = inspect.getsource(specialists.build_test_run_request)
    rule = source[source.index("A rule the product enforces"):source.index("is a defect.")]
    for word in ("form", "button", "click", "field", "title", "task"):
        assert not re.search(rf"\b{word}s?\b", rule, re.I), word
