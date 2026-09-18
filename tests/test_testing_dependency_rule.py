"""The rule that stops a brief from outlawing its own test suite.

run-2d9066e2's brief forbids external dependencies and `TESTABILITY_RULE`
mandates Playwright for browser UI. Both were read as binding, so the sprint
spent all three remediation attempts on the contradiction and the run failed
without a product defect in it. The constraint was never aimed at the test
suite; nothing said it was, and nothing said it was not.

run-551640d3 failed from the other side: it installed `jsdom` for its tests and
recorded the decision as a *risk* - "which would introduce an external
dependency" - because the constraint it was reading did not distinguish the
product's dependencies from its own.

These tests pin both the rule's presence in every prompt that can walk into the
contradiction, and the specific sentences that make it actable: an agent that
sees the rule must be unable to conclude that a dependency constraint forbids
testing, and a reviewer must be unable to accept a plan that declines to test
on that ground.
"""

from __future__ import annotations

from app.agents.testing_dependency_rule import TESTING_DEPENDENCY_RULE


def _flat(text: str) -> str:
    """Whitespace-insensitive comparison, so prompt indentation cannot hide a
    difference between the rule as written and the rule as embedded."""
    return " ".join(text.split())


def test_the_rule_forbids_accepting_a_dependency_based_refusal_to_test():
    """The one sentence the user asked for, in the rule's own voice."""
    assert "YOU MUST NOT ACCEPT" in TESTING_DEPENDENCY_RULE
    assert "forbids" in TESTING_DEPENDENCY_RULE
    assert "dependencies" in TESTING_DEPENDENCY_RULE


def test_the_rule_states_the_scope_of_a_dependency_constraint():
    """A constraint on the product is not a constraint on the tests. Without
    this sentence the rule reads as a list of exceptions rather than a scope.
    """
    assert "IS NOT A CONSTRAINT ON ITS TESTS" in TESTING_DEPENDENCY_RULE
    assert "SHIPPED" in TESTING_DEPENDENCY_RULE


def test_the_rule_honours_a_user_chosen_testing_stack():
    """The user may request a specific framework, and it is not overruled by a
    dependency constraint."""
    assert "MAY CHOOSE A TESTING STACK" in TESTING_DEPENDENCY_RULE


def test_the_rule_makes_a_refusal_to_test_a_blocking_finding_for_reviewers():
    """Reviewers get a distinct instruction: declining to test on dependency
    grounds is blocking, and so is recording a test-only install as a risk.
    """
    assert "IF YOU ARE REVIEWING" in TESTING_DEPENDENCY_RULE
    assert "BLOCKING finding" in TESTING_DEPENDENCY_RULE
    assert "not a risk" in TESTING_DEPENDENCY_RULE


def test_the_rule_tells_builders_which_scope_to_use():
    """Without the per-ecosystem scope an agent that accepts the rule still
    does not know where to put the package, and the constraint is honoured in
    the breach. Spans the stacks this harness builds in, not one of them.
    """
    for phrase in (
        "devDependencies",
        "testImplementation",
        "[dev-dependencies]",
        "require-dev",
        "group :test",
        "dependency-groups",
    ):
        assert phrase in TESTING_DEPENDENCY_RULE, phrase


def test_the_rule_does_not_prefer_one_language():
    """A rule that only names npm is a rule a Python, Go or Java run ignores."""
    for phrase in ("Python", "Java", "Rust", "PHP", "Ruby", ".NET", "Go"):
        assert phrase in TESTING_DEPENDENCY_RULE, phrase


def test_the_rule_reaches_every_agent_that_can_walk_into_the_contradiction():
    """The contradiction is reachable from any of these stages, and each one
    needs to recognise it in the work of the stages before it.
    """
    from app.agents.architecture_reviewer import _SYSTEM_PROMPT as arch
    from app.agents.milestone_reviewer import _SYSTEM_PROMPT as milestone
    from app.agents.principal_architect import _SYSTEM_PROMPT as architect
    from app.agents.specialists import _system_prompt
    from app.agents.stack_selector import _SYSTEM_PROMPT as stack

    rule = _flat(TESTING_DEPENDENCY_RULE)
    assert rule in _flat(architect)
    assert rule in _flat(stack)
    assert rule in _flat(arch)
    assert rule in _flat(milestone)
    for role in ("ui_ux", "database", "backend", "testing", "documentation",
                 "security_reliability"):
        assert rule in _flat(_system_prompt(role)), role


def test_the_rule_is_not_duplicated_in_the_testability_rule():
    """Two rules saying the same thing in different words is how an agent ends
    up following neither. This rule owns the dependency scope; the testability
    rule owns how the code is shaped to be testable.
    """
    from app.agents.testability import TESTABILITY_RULE

    assert "Testing is exempt" not in TESTABILITY_RULE
