"""A failed locator is told what on the page it nearly matched.

One run spent six fix stages on locked tests waiting for
`getByLabel('Title', { exact: true })` while the page each failed on showed
`textbox "Title:"`. The call log and the page were both in every fix request;
no stage connected them. Said only when nothing matches under Playwright's own
rules and something differs only in case, punctuation or role.
"""

from __future__ import annotations

import pytest

from app.stacks import pack_named
from app.stacks.packs._javascript import near_misses

PAGE = """- main [ref=e2]:
  - heading "Notes" [level=1] [ref=e3]
  - generic [ref=e4]:
    - text: "Title:"
    - textbox "Title:" [ref=e5]
    - button "Save note" [ref=e7]
  - list"""


def _waiting_for(locator: str) -> str:
    return f"locator.fill: Timeout 3000ms exceeded.\n    Call log:\n      - waiting for {locator}\n"


def test_an_exact_label_one_colon_away_is_named() -> None:
    hint = near_misses(_waiting_for("getByLabel('Title', { exact: true })"), PAGE)
    assert 'textbox "Title:"' in hint and "getByLabel('Title', { exact: true })" in hint


@pytest.mark.parametrize("locator, shown", [
    ("getByRole('button', { name: 'Save Note', exact: true })", 'button "Save note"'),
    ("getByRole('link', { name: 'Save note' })", 'button "Save note"'),
    ("locator('li').getByRole('button', { name: 'save-note', exact: true })", 'button "Save note"'),
])
def test_a_name_in_another_case_or_role_is_named(locator, shown) -> None:
    assert shown in near_misses(_waiting_for(locator), PAGE)


@pytest.mark.parametrize("locator", [
    "getByLabel('Title')",                                   # substring, case-insensitive: it matches
    "getByLabel('Title:', { exact: true })",                 # matches exactly
    "getByRole('button', { name: 'Save' })",                 # matches: the miss is about something else
    "getByRole('checkbox', { name: 'Done' })",               # nothing close: nothing to say
    "getByTestId('x')",                                      # no name to compare
])
def test_it_is_silent_when_the_miss_is_not_a_near_one(locator) -> None:
    assert near_misses(_waiting_for(locator), PAGE) == ""


def test_the_browser_packs_attach_it_to_the_page_a_test_failed_on() -> None:
    from types import SimpleNamespace

    from app.acceptance.suite import _a_near_miss

    for name in ("browser-javascript", "browser-react", "fullstack-node"):
        assert pack_named(name).near_misses is near_misses, name
    assert "Nearly there" in _a_near_miss(pack_named("browser-javascript"), _waiting_for("getByLabel('Title', { exact: true })"), PAGE)
    assert _a_near_miss(SimpleNamespace(near_misses=None), "x", PAGE) == ""


# --- a one-off script is named as one ---------------------------------------------------


def test_code_refused_on_the_command_line_is_sent_to_a_file_the_harness_sweeps() -> None:
    """The advice was "run the file, then remove it". One run left twelve
    `tmp-*` probes, which the sweep removes, and `src/import-ui.mjs`, which it
    cannot tell from the product."""
    import re

    from app.analysis.file_kinds import is_scratch
    from app.tools.sandbox import CommandNotAllowed, validate_command

    with pytest.raises(CommandNotAllowed) as raised:
        validate_command(["node", "-e", "console.log(1)"], "testing_specialist")
    advice = str(raised.value)

    assert "`tmp-<what it checks>`" in advice and "never ships" in advice
    assert "delete_artifact" not in advice
    for name in ("tmp-check.js", "tmp-imports.py", "tmp-what-renders.mjs"):
        assert is_scratch(name), name
    assert not re.search(r"\b(?:task|todo|button|click)\b", advice, re.I)
