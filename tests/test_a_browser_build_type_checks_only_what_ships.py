"""A browser pack's production build type-checks only the code that ships, not the unit tests.

Measured on the React pack: `tsconfig.json` took in `tests` for the editor, so a type error in a unit test failed
`npm run build`; the harness raised it as "what would be shipped does not exist" and sent it to a page fixer, and in
2 of 7 runs every build fix changed only tests or the tsconfig.
"""
import json

import pytest

from app.stacks.packs import browser_react, browser_vue


@pytest.mark.parametrize("module", [browser_react, browser_vue])
def test_the_build_checks_a_config_that_holds_only_the_source(module):
    pack = next(value for value in vars(module).values() if getattr(value, "files", None) and "package.json" in value.files)
    build = json.loads(pack.files["package.json"].replace("{{project}}", "p"))["scripts"]["build"]
    assert "-p tsconfig.build.json" in build
    shipped = json.loads(pack.files["tsconfig.build.json"])
    assert shipped["extends"] == "./tsconfig.json" and shipped["include"] == ["src"]
    assert "tests" in json.loads(pack.files["tsconfig.json"])["include"]  # the editor still checks the tests
