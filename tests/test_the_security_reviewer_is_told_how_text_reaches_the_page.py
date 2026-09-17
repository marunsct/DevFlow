"""The security reviewer gets the fact that settles a DOM-injection finding.

`how_the_page_receives_text` was built for the milestone reviewer, which
recorded a major XSS finding in run 1c9854c7 against a product whose only text
write was `textSpan.textContent = task.text`, and the run was stopped after
three revisions over a defect that did not exist.

It went to that reviewer and no further. The security reviewer is the stage
whose job this is, and it made the same mistake with no way to check: run
08acb1ee reported "renders task names using innerHTML without sanitization"
against a product that assigns `textContent` three times and `innerHTML` never.

Two stages can make this finding. The answer was computed for one of them.
"""

from __future__ import annotations

from app.agents.security_reviewer import build_security_review_request


def _brief(root) -> str:
    built = build_security_review_request(["app.js"], "no tools", str(root))
    return built["messages"][0]["content"]


def test_a_product_that_only_writes_text_says_so(tmp_path):
    (tmp_path / "app.js").write_text(
        "const li = document.createElement('li');\n"
        "li.textContent = task.title;\n"
        "list.innerHTML = '';\n"
    )
    brief = _brief(tmp_path)
    assert "only through `textContent`" in brief
    assert "would be incorrect" in brief


def test_a_product_that_assigns_markup_says_that_instead(tmp_path):
    (tmp_path / "app.js").write_text("list.innerHTML = `<li>${task.title}</li>`;\n")
    brief = _brief(tmp_path)
    assert "assign markup" in brief
    assert "worth checking" in brief


def test_clearing_a_container_is_not_markup(tmp_path):
    """`innerHTML = ""` parses nothing, and calling it an injection route is
    the mistake this exists to prevent."""
    (tmp_path / "app.js").write_text("list.innerHTML = '';\nli.textContent = t;\n")
    assert "would be incorrect" in _brief(tmp_path)


def test_a_product_with_no_dom_writes_adds_nothing(tmp_path):
    (tmp_path / "app.js").write_text("export function addTask(t) { return t; }\n")
    brief = _brief(tmp_path)
    assert "How this product writes to the page" not in brief
    # and the rest of the brief is still intact
    assert "Tool permissions context" in brief


def test_the_run_that_prompted_this(tmp_path):
    """Run 08acb1ee, reduced to the three writes its `app.js` actually made."""
    (tmp_path / "app.js").write_text(
        "list.textContent = '';\n"
        "span.textContent = `${sanitizedTitle}${sanitizedDescription}`;\n"
        "deleteBtn.textContent = 'Delete';\n"
    )
    assert "An injection finding about DOM insertion would be incorrect" in _brief(
        tmp_path
    )
