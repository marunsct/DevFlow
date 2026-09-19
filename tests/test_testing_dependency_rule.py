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

import json

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


def test_the_sandbox_does_not_refuse_a_test_scoped_install(tmp_path):
    """The rule tells an agent to `npm i -D @playwright/test`; the sandbox must
    not refuse the install it asks for.

    Measured on run-519a9d8a: the refusal blocked the only suite that can
    exercise a real DOM, the model installed the package *without* the flag to
    get past it, and the milestone reviewer then filed the undeclared package
    as a blocking defect from the other direction. Refusing the test-scoped
    install made the product worse and the review wrong.
    """
    from app.tools.sandbox import _refuse_an_install_the_brief_rules_out

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "product_intake.md").write_text(
        "# Constraints\n- No external dependencies beyond basic HTML/CSS/JS\n"
    )

    refused = _refuse_an_install_the_brief_rules_out(
        ["npm", "i", "-D", "@playwright/test"], str(tmp_path)
    )
    assert refused == ""


def test_the_sandbox_still_refuses_a_production_install(tmp_path):
    """The product's dependencies are still the brief's business. A bare
    `npm install <pkg>` writes to `dependencies` and ships to the user.
    """
    from app.tools.sandbox import _refuse_an_install_the_brief_rules_out

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "product_intake.md").write_text(
        "# Constraints\n- No external dependencies beyond basic HTML/CSS/JS\n"
    )

    refused = _refuse_an_install_the_brief_rules_out(
        ["npm", "install", "express"], str(tmp_path)
    )
    assert refused.startswith("Refusing to install express")
    assert "npm i -D" in refused


def test_a_test_scoped_install_is_allowed_and_a_misfiled_one_is_caught_downstream(
    tmp_path,
):
    """`-D` is not a loophole for a package the product itself imports.

    The sandbox cannot see imports, so it allows the test-scoped install - the
    same install the rule asks for - and the manifest check downstream reports
    the package as a product dependency filed in the wrong place. Two layers,
    each doing the part it has the evidence for.
    """
    from app.agents.brief_constraints import what_the_brief_forbids_that_is_there
    from app.tools.sandbox import _refuse_an_install_the_brief_rules_out

    forbids = (
        "# Brief\n\n## Technical Constraints\n"
        "- No external dependencies beyond basic HTML/CSS/JS\n"
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "product_intake.md").write_text(
        "# Constraints\n- No external dependencies beyond basic HTML/CSS/JS\n"
    )
    project = tmp_path / "app"
    project.mkdir()
    (project / "package.json").write_text(
        json.dumps({"devDependencies": {"express": "^4"}})
    )
    (project / "index.js").write_text("const express = require('express');\n")

    assert (
        _refuse_an_install_the_brief_rules_out(
            ["npm", "install", "--save-dev", "express"], str(tmp_path)
        )
        == ""
    )
    found = what_the_brief_forbids_that_is_there(forbids, tmp_path)
    assert found and "`express`" in found[0]


def test_an_install_with_no_constraint_is_silent(tmp_path):
    """A brief that allows dependencies has nothing to refuse."""
    from app.tools.sandbox import _refuse_an_install_the_brief_rules_out

    assert _refuse_an_install_the_brief_rules_out(
        ["npm", "install", "express"], str(tmp_path)
    ) == ""
