"""The design rule that makes a headless test suite affordable.

Several runs of the same brief paid for its absence: the app entry point touched
the DOM at module scope, so nothing in it could be imported by a test. See
`app.agents.testability` for what each run spent.

The rule is in two parts. The principles hold in every language and stay in
`TESTABILITY_RULE`, which every specialist reads. The concrete tools, globals
and file conventions of one stack live in that stack's seed row in
`app.plugins.seed`, and reach an agent only when its run's stack names them -
so an agent building a Go service is not told how to configure a browser.
"""

from __future__ import annotations

import re

import pytest

from app.agents.testability import TESTABILITY_RULE
from app.plugins.seed import SEED_INSTRUCTIONS


def _flat(text: str) -> str:
    """Prompt text wraps; wording assertions must not depend on where."""
    return " ".join(text.split())


PAGE = _flat(SEED_INSTRUCTIONS["html"])
JAVASCRIPT = _flat(SEED_INSTRUCTIONS["javascript"])
RULE = _flat(TESTABILITY_RULE)


class TestTheRuleIsStackNeutral:
    @pytest.mark.parametrize(
        "name",
        ["Playwright", "npm", "node --test", "package.json", "jsdom", "document", "window",
         "localStorage", "<script>", ".mjs", "doesNotThrow", "typeof"],
    )
    def test_it_names_no_one_stack_s_tools(self, name: str) -> None:
        """Those belong in the seed row of the stack they describe."""
        assert name not in TESTABILITY_RULE

    def test_it_points_at_where_the_stack_s_tools_are_named(self) -> None:
        assert "FRAMEWORK CAPABILITIES" in RULE


class TestThePrinciples:
    def test_it_names_the_thing_that_breaks_a_headless_test(self) -> None:
        assert "does its I/O while it is being loaded" in RULE
        assert "guarded so that importing the module does not run it" in RULE

    def test_every_specialist_that_writes_code_is_given_the_rule(self) -> None:
        """Not the one role that happened to hit it."""
        from app.agents.specialists import _ROLE_DESCRIPTIONS, _system_prompt

        missing = [
            role.value if hasattr(role, "value") else str(role)
            for role in _ROLE_DESCRIPTIONS
            if RULE not in _flat(_system_prompt(role))
        ]

        assert not missing, f"specialists without the testability rule: {missing}"

    def test_the_architect_designs_against_it_too(self) -> None:
        from app.agents.principal_architect import _SYSTEM_PROMPT

        assert RULE in _flat(_SYSTEM_PROMPT)

    def test_it_requires_exports(self) -> None:
        assert "EXPORT the pure functions" in RULE
        assert "a copy passes whatever your code does" in RULE

    def test_a_module_system_is_not_a_dependency(self) -> None:
        """A specification once ruled out modules to honour "no external
        dependencies" and then asked for a test command - a runner can only test
        what it can import, and the language's own modules install nothing."""
        assert "A MODULE SYSTEM IS NOT AN EXTERNAL DEPENDENCY" in RULE
        assert "installs nothing and adds no package" in RULE
        assert "a test runner can only test what it can import" in RULE

    def test_the_logic_must_be_in_a_file_a_test_can_open(self) -> None:
        assert "THE LOGIC MUST LIVE IN A FILE A TEST CAN OPEN" in RULE
        assert "cannot be imported by any runner" in RULE

    def test_it_answers_the_copy_that_imports_the_module_anyway(self) -> None:
        assert "CALL THE FUNCTION YOU IMPORTED" in RULE
        assert "only checks that a name exists has not tested it" in RULE
        assert "CHANGE THE FUNCTION, NOT THE TEST" in RULE

    def test_it_rejects_an_assertion_that_only_checks_it_did_not_throw(self) -> None:
        """A save function once passed a whole suite with its body replaced."""
        assert "IT DID NOT THROW" in RULE
        assert "would any test fail" in RULE

    def test_it_separates_where_it_ships_from_where_it_is_tested(self) -> None:
        assert "WHERE THE PRODUCT RUNS IS NOT WHERE THE TESTS RUN" in RULE
        assert "The runtime the tests need is the developer's" in RULE


class TestTheBrowserSpecificsLiveWithThePageStack:
    @pytest.mark.parametrize("name", ["document", "window", "localStorage"])
    def test_the_globals_that_break_an_import_are_named(self, name: str) -> None:
        assert name in PAGE

    def test_the_guarded_bootstrap(self) -> None:
        assert "typeof document !== 'undefined'" in PAGE
        assert "bare `init();` at the end of the file is the whole problem" in PAGE

    def test_logic_in_a_script_tag_is_unreachable(self) -> None:
        assert "`<script>` tag" in PAGE
        assert "no runner can import it" in PAGE

    def test_the_browser_runner_and_its_traps(self) -> None:
        assert "Playwright" in PAGE
        assert "--reporter=tap" in PAGE
        assert "file://" in PAGE and "webServer" in PAGE

    @pytest.mark.parametrize("framework", ["react", "vue", "angular", "nextjs"])
    def test_every_page_framework_carries_it(self, framework: str) -> None:
        assert "typeof document !== 'undefined'" in SEED_INSTRUCTIONS[framework]


class TestTheJavaScriptSpecificsLiveWithTheLanguage:
    def test_the_module_type_is_declared(self) -> None:
        assert "IF YOU USE `export`, DECLARE IT" in JAVASCRIPT
        assert '{"type": "module"}' in JAVASCRIPT

    def test_the_manifest_says_how_to_run_the_tests(self) -> None:
        assert "MUST SAY HOW TO RUN THE TESTS" in JAVASCRIPT
        assert "missing script: test" in JAVASCRIPT

    def test_the_weak_assertions_are_named_in_its_own_syntax(self) -> None:
        assert "doesNotThrow" in JAVASCRIPT
        assert re.search(r"typeof mod\.\w+ === 'function'", JAVASCRIPT)

    @pytest.mark.parametrize("language", ["typescript", "node"])
    def test_its_relatives_carry_it(self, language: str) -> None:
        assert "IF YOU USE `export`, DECLARE IT" in SEED_INSTRUCTIONS[language]
