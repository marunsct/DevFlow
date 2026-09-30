"""The milestone reviewer checks an "every action" criterion per action.

One run's final review accepted "Keyboard accessibility - all interactive
elements have tabindex=0, aria-labels, Enter/Space handlers" while editing a
task could only be started by clicking a title that could not take focus. The
same review missed that the add form refused a description over 1000
characters and the edit path accepted one.
"""
from app.agents.milestone_reviewer import _SYSTEM_PROMPT


def test_the_reviewer_lists_each_action_for_an_every_action_criterion():
    assert "checked action by action" in _SYSTEM_PROMPT
    assert "cannot receive focus" in _SYSTEM_PROMPT


def test_the_reviewer_compares_every_path_that_changes_a_value():
    assert "must hold on\n  every path that changes the same value" in _SYSTEM_PROMPT


def test_the_rule_names_no_framework():
    rules = _SYSTEM_PROMPT[_SYSTEM_PROMPT.index("checked action by action"):
                           _SYSTEM_PROMPT.index("Treat the executed-command record")]
    for word in ("JavaScript", "React", "tabindex", "DOM", "Playwright", "HTML"):
        assert word not in rules
