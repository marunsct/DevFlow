"""Product code may not replace a method the browser already defines; a page keeps its newlines.

Measured on one run. A unit test asked `querySelector` for a selector the DOM
does not define and threw. The stage fixing it replaced `document.querySelector`
and `Element.prototype.querySelector` in the product's entry module instead of
changing the test, and the product shipped with every query on its page going
through the rewrite.

The same run's interface stage replaced a line of `index.html` with newlines
sent as the two characters backslash-n. Nothing parses a page strictly, so
nothing refused it, and the browser showed "\\n" at the top of the page.
"""

from __future__ import annotations

import re

import pytest

from app.tools.repository import (
    RepositoryToolError,
    escapes_between_tags,
    replace_approved_lines,
    write_approved_artifact,
)

BANNED = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")

REWRITE = (
    "const original = document.querySelector;\n"
    "document.querySelector = function (selector) { return original.call(this, selector); };\n"
)


class _Tools:
    def __init__(self, root) -> None:
        self.root = str(root)

    def write_artifact(self, relative_path: str, content: str) -> dict:
        return write_approved_artifact(self.root, relative_path, content)

    def replace_lines(self, relative_path: str, start: int, end: int, content: str) -> dict:
        return replace_approved_lines(self.root, relative_path, start, end, content)


@pytest.fixture
def tools(tmp_path):
    (tmp_path / "app" / "src").mkdir(parents=True)
    (tmp_path / "app" / "tests").mkdir()
    return _Tools(tmp_path)


class TestRewritingThePlatform:
    @pytest.mark.parametrize("line", [
        "document.querySelector = mine;",
        "Element.prototype.querySelector = function (s) { return null; };",
        "window.addEventListener = () => {};",
        "HTMLElement.prototype.closest = x;",
    ])
    def test_a_product_file_is_refused(self, tools, tmp_path, line) -> None:
        with pytest.raises(RepositoryToolError, match="which every browser already defines"):
            tools.write_artifact("app/src/main.js", f"{line}\n")

        assert not (tmp_path / "app" / "src" / "main.js").exists()

    @pytest.mark.parametrize("line", [
        "document.title = 'x';",
        "if (document.querySelector === mine) {}",
        "const query = document.querySelector('#x');",
        "el.onclick = handler;",
    ])
    def test_what_only_reads_or_sets_its_own_is_not(self, tools, line) -> None:
        tools.write_artifact("app/src/main.js", f"{line}\n")

    def test_a_test_may_stub_what_it_likes(self, tools) -> None:
        tools.write_artifact("app/tests/main.test.js", REWRITE)

    def test_an_edit_that_adds_one_is_refused(self, tools, tmp_path) -> None:
        (tmp_path / "app" / "src" / "main.js").write_text("const a = 1;\nconst b = 2;\n")

        with pytest.raises(RepositoryToolError, match="which every browser already defines"):
            tools.replace_lines("app/src/main.js", 2, 2, "document.querySelector = mine;")

    def test_an_edit_that_takes_one_out_is_let_through(self, tools, tmp_path) -> None:
        (tmp_path / "app" / "src" / "main.js").write_text(REWRITE + "const a = 1;\n")

        tools.replace_lines("app/src/main.js", 3, 3, "const a = 2;")

        assert "const a = 2;" in (tmp_path / "app" / "src" / "main.js").read_text()

    def test_the_refusal_names_no_product_and_no_control(self, tools) -> None:
        with pytest.raises(RepositoryToolError) as refused:
            tools.write_artifact("app/src/main.js", "document.querySelector = mine;\n")

        for word in BANNED:
            assert not re.search(rf"\b{word}\b", str(refused.value).lower()), word


PAGE = (
    "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n  <meta charset=\"UTF-8\">\n"
    "  <title>Notes</title>\n</head>\n<body>\n  <main id=\"app\"></main>\n</body>\n</html>\n"
)


class TestAPageKeepsItsNewlines:
    def test_an_edit_with_its_newlines_escaped_is_written_with_them(self, tools, tmp_path) -> None:
        page = tmp_path / "app" / "index.html"
        page.write_text(PAGE)

        tools.replace_lines(
            "app/index.html", 4, 4,
            '  <meta charset="UTF-8">\\n  <meta name="viewport" content="width=device-width, initial-scale=1.0">',
        )

        text = page.read_text()
        assert "\\n" not in text
        assert '  <meta charset="UTF-8">\n  <meta name="viewport"' in text

    def test_a_whole_page_with_its_newlines_escaped_is_written_with_them(self, tools, tmp_path) -> None:
        result = tools.write_artifact("app/index.html", PAGE.replace("\n", "\\n"))

        assert (tmp_path / "app" / "index.html").read_text().strip() == PAGE.strip()
        assert "escaped twice" in str(result)

    def test_an_escape_inside_a_script_is_the_script_s(self, tools, tmp_path) -> None:
        page = PAGE.replace("</main>", "</main>\n  <script>const s = '<b>\\n</b>';</script>")
        tools.write_artifact("app/index.html", page)

        assert (tmp_path / "app" / "index.html").read_text() == page

    @pytest.mark.parametrize("path, text, found", [
        ("a/index.html", "<p>x</p>\\n<p>y</p>", True),
        ("a/index.html", "<p>a\\nb</p>", False),
        ("a/index.html", "<pre>\\n</pre>", False),
        ("a/main.js", "'<p>x</p>\\n<p>y</p>'", False),
    ])
    def test_what_counts(self, path, text, found) -> None:
        assert escapes_between_tags(path, text) is found
