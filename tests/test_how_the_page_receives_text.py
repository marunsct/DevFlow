"""Which DOM-writing API the product uses, stated as fact.

Run 1c9854c7 was killed by a finding that was not true. After three revisions
the milestone review recorded

    [major] security: The addTask function inserts user-provided task text
    directly into the DOM without sanitization, potentially allowing XSS
    injection.

and the run stopped rather than revising further. The product at that moment
wrote task text with `textSpan.textContent = task.text;` and its only
`innerHTML` was `container.innerHTML = ""`. `textContent` does not parse HTML.
There was no injection to be had, the suite was 9 of 9 green, and a correct
product was thrown away over a defect that did not exist.

Which API a file uses is decidable, so it is stated rather than inferred.
Whether it is safe enough remains the reviewer's judgement.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.analysis.integration_checks import (
    _MARKUP_INTO_THE_PAGE,
    how_the_page_receives_text,
)

SAFE = """export function render(tasks) {
  container.innerHTML = "";
  const span = document.createElement('span');
  span.textContent = tasks[0].text;
}
"""

MARKUP = """export function render(tasks) {
  container.innerHTML = `<li>${tasks[0].text}</li>`;
}
"""


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "app").mkdir()
    return tmp_path


def test_a_textcontent_product_is_stated_as_safe(project: Path):
    (project / "app" / "app.js").write_text(SAFE, encoding="utf-8")

    note = how_the_page_receives_text(project)

    assert "textContent" in note
    assert "would be incorrect" in note


def test_a_markup_product_is_flagged_for_checking(project: Path):
    (project / "app" / "app.js").write_text(MARKUP, encoding="utf-8")

    note = how_the_page_receives_text(project)

    assert "assign markup" in note
    assert "worth checking" in note


@pytest.mark.parametrize(
    "line",
    ['el.innerHTML = "";', "el.innerHTML = '';", "el.innerHTML = ``;"],
)
def test_clearing_a_container_is_not_markup(line: str):
    """The regex once backtracked its own whitespace and matched all of these.

    With `\\s*` before the lookahead, the engine shrinks it to empty, evaluates
    the lookahead against the space, and the negative trivially succeeds - so
    `innerHTML = ""` was reported as markup, the exact opposite of what it is.
    """
    assert not _MARKUP_INTO_THE_PAGE.search(line)


@pytest.mark.parametrize(
    "line",
    [
        "el.innerHTML = task.text;",
        "el.innerHTML = `<li>${t}</li>`;",
        'el.innerHTML = "<li>x</li>";',
        'el.insertAdjacentHTML("beforeend", t);',
        "el.outerHTML = x;",
        "document.write(t);",
    ],
)
def test_real_markup_writes_are_still_caught(line: str):
    assert _MARKUP_INTO_THE_PAGE.search(line)


def test_a_product_that_never_touches_the_dom_says_nothing(project: Path):
    (project / "app" / "app.js").write_text("export const a = 1;\n", encoding="utf-8")

    assert how_the_page_receives_text(project) == ""


def test_a_test_file_does_not_decide_this(project: Path):
    """A test may build markup to assert against; the product is the question."""
    (project / "app" / "app.test.js").write_text(MARKUP, encoding="utf-8")
    (project / "app" / "app.js").write_text(SAFE, encoding="utf-8")

    assert "would be incorrect" in how_the_page_receives_text(project)


def test_the_milestone_reviewer_is_given_it(project: Path):
    from app.agents.milestone_reviewer import build_milestone_review_request

    (project / "app" / "app.js").write_text(SAFE, encoding="utf-8")

    body = build_milestone_review_request(
        "goal", ["app/app.js"], "tests pass", "no defects", str(project)
    )["messages"][0]["content"]

    assert "How this product writes to the page" in body


def test_a_commented_out_innerHTML_is_not_markup(project: Path):
    """Reading it as markup withholds the sentence this exists to provide."""
    (project / "app" / "app.js").write_text(
        "// el.innerHTML = task.text;\nspan.textContent = task.text;\n", encoding="utf-8"
    )

    assert "would be incorrect" in how_the_page_receives_text(project)


def test_a_block_comment_is_not_markup_either(project: Path):
    (project / "app" / "app.js").write_text(
        "/* el.innerHTML = t; */\nspan.textContent = t;\n", encoding="utf-8"
    )

    assert "would be incorrect" in how_the_page_receives_text(project)


@pytest.mark.parametrize("clearing", ["el.innerHTML = '';", 'el.innerHTML = "";'])
def test_clearing_survives_the_comment_stripping(project: Path, clearing: str):
    """Blanking string literals too would erase the quotes this is known by.

    `innerHTML = ""` is a clearing and ``innerHTML = `<li>${t}</li>` `` is
    markup; a stripper that blanks both leaves `innerHTML = ;` in each case and
    loses exactly the difference being asked about. So comments go and literals
    stay.
    """
    (project / "app" / "app.js").write_text(
        f"{clearing}\nspan.textContent = t;\n", encoding="utf-8"
    )

    assert "would be incorrect" in how_the_page_receives_text(project)


def test_an_interpolating_template_is_still_markup(project: Path):
    (project / "app" / "app.js").write_text(
        "el.innerHTML = `<li>${task.text}</li>`;\n", encoding="utf-8"
    )

    assert "assign markup" in how_the_page_receives_text(project)
