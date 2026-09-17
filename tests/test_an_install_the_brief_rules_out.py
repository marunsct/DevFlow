"""Installing a package the brief rules out, at the moment it enters.

Every check that reports a forbidden dependency reports it downstream of one
command. `what_the_brief_forbids_that_is_there` finds it at a milestone
review; the module-system findings arrive a sprint later still. It enters at
`npm install <package>`.

Eight of the twenty-nine recorded install commands add a named package to a
project whose brief says "No external dependencies beyond basic HTML/CSS/JS":
jsdom four times across runs 551640d3, 740edb6b and 84e05d4b, plus
jest-environment-jsdom and text-encoding in 8d28ee3f, and jsdom then jest in
9bd3a091. The other twenty-one are a bare `npm install`, which adds nothing.

A refusal rather than a note, on the escalation the codebase has settled
twice. The testing role's own description already tells it not to introduce a
runner the stack did not choose and to "verify with what the runtime already
provides" where the stack names none. Run 9bd3a091 had that text in front of
it and ran `npm install jsdom`, then `npm install jest`.
"""

from __future__ import annotations

import pytest

from app.tools.sandbox import _refuse_an_install_the_brief_rules_out


@pytest.fixture
def forbidding(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "product_intake.md").write_text(
        "# Product intake\n\n## Constraints\n\n"
        "- No external dependencies beyond basic HTML/CSS/JS\n"
    )
    return tmp_path


@pytest.fixture
def permitting(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "product_intake.md").write_text(
        "# Product intake\n\nUse whatever libraries help.\n"
    )
    return tmp_path


@pytest.mark.parametrize(
    "command",
    [
        ["npm", "install", "jsdom"],
        ["npm", "install", "--save-dev", "jsdom"],
        ["npm", "install", "jest"],
        ["npm", "install", "--save-dev", "jest-environment-jsdom"],
        ["npm", "install", "--save-dev", "text-encoding"],
        ["yarn", "add", "jsdom"],
        ["pnpm", "add", "jsdom"],
    ],
)
def test_every_recorded_install_of_a_named_package_is_refused(forbidding, command):
    assert _refuse_an_install_the_brief_rules_out(command, str(forbidding))


@pytest.mark.parametrize(
    "command",
    [
        ["npm", "install"],
        ["npm", "ci"],
        ["npm", "test"],
        ["npm", "run", "build"],
        ["node", "--test"],
        ["node", "--check", "app.js"],
    ],
)
def test_a_command_that_adds_nothing_is_left_alone(forbidding, command):
    """A bare `npm install` installs what the manifest already declares.

    Twenty-one of the twenty-nine recorded installs are this, and refusing
    them would break every project that legitimately has a lockfile.
    """
    assert _refuse_an_install_the_brief_rules_out(command, str(forbidding)) == ""


def test_a_brief_that_permits_dependencies_permits_the_install(permitting):
    assert _refuse_an_install_the_brief_rules_out(
        ["npm", "install", "jsdom"], str(permitting)
    ) == ""


def test_no_intake_document_means_no_constraint_to_enforce(tmp_path):
    """Before the intake is written there is nothing to read, and a constraint
    that cannot be read is not enforced."""
    assert _refuse_an_install_the_brief_rules_out(
        ["npm", "install", "jsdom"], str(tmp_path)
    ) == ""


def test_the_refusal_quotes_the_brief_and_names_the_package(forbidding):
    refusal = _refuse_an_install_the_brief_rules_out(
        ["npm", "install", "jsdom"], str(forbidding)
    )
    assert "jsdom" in refusal
    assert "No external dependencies beyond basic HTML/CSS/JS" in refusal


def test_the_refusal_says_what_to_do_instead(forbidding):
    """A refusal with no way forward is how a stage burns its remaining calls."""
    refusal = _refuse_an_install_the_brief_rules_out(
        ["npm", "install", "jsdom"], str(forbidding)
    )
    assert "node:test" in refusal and "node:assert" in refusal
    assert "without a DOM" in refusal
    # And the escape hatch, so a genuinely impossible brief is reported rather
    # than worked around.
    assert "blocker in your report" in refusal


def test_the_constraint_is_also_read_from_the_stack_document(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "technology_stack.md").write_text(
        "# Stack\n\n- No external dependencies beyond basic HTML/CSS/JS\n"
    )
    assert _refuse_an_install_the_brief_rules_out(
        ["npm", "install", "jsdom"], str(tmp_path)
    )
