"""Every pack that runs unit tests in a simulated page gives vitest globals, so Testing Library cleans up each render.

Measured on the React pack: vitest ran without `globals`, Testing Library registered no cleanup, and every test's
render stayed in the page for the next - 11 of 22 unit tests failed with "found multiple elements" on a right product,
and the sprint was planned again; in 3 of 7 earlier runs writers or fixers added `cleanup` by hand. With `globals: true`
the same tests went to 21 of 22.
"""
import re

import pytest

from app.stacks.packs import _fullstack, browser_react, browser_svelte, browser_vue, fullstack_next


def _configs(module):
    for value in vars(module).values():
        if isinstance(value, str) and "environment: 'jsdom'" in value:
            yield value


@pytest.mark.parametrize("module", [browser_react, browser_svelte, browser_vue, fullstack_next, _fullstack])
def test_each_simulated_page_config_turns_on_globals(module):
    configs = list(_configs(module))
    assert configs, module.__name__
    for text in configs:
        for found in re.finditer(r"environment: 'jsdom'", text):
            near = text[found.start():found.start() + 200]
            assert re.search(r"globals:\s*true", near), (module.__name__, near)
