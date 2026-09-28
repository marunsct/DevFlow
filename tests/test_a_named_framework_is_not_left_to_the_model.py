"""A framework the chosen stack names gets its instructions, whatever the model says.

One run's stack document selected "None (Vanilla HTML/CSS/JS)" with "Playwright
for page". The extraction model, told to leave out "tools or generic terms",
returned `javascript` alone. The browser-page testing instructions are stored
under `html`, so the test round that wrote the Playwright suite never saw them.
"""

from __future__ import annotations

import pytest

from app.plugins import middleware as plugin_middleware
from app.plugins.middleware import _extract_stack_keywords, _named_in_the_selected_stack

#: The run's document, as `artifact_document` wrote it.
STACK = """# Technology Stack

## Selected Technology Stack
#### JavaScript
**Framework:**
None (Vanilla HTML/CSS/JS)

**Database:**
Browser Local Storage API

**Testing framework:**
node --test (built-in Node test runner) for logic; Playwright for page


## Rationale
Vanilla JS is the only viable choice. React, Vue and a Postgres backend were
ruled out by the brief; Vitest was passed over for `node --test`.
"""

KNOWN = {"javascript", "html", "node", "react", "vue", "postgres", "java", "go", "nextjs"}


class TestTheMatch:
    def test_the_run_s_stack_gets_its_page_instructions(self) -> None:
        assert _named_in_the_selected_stack(STACK, KNOWN) == ["html", "javascript", "node"]

    def test_what_the_rationale_turned_down_is_not_included(self) -> None:
        found = _named_in_the_selected_stack(STACK, KNOWN)

        assert "react" not in found and "vue" not in found and "postgres" not in found

    def test_java_is_not_read_out_of_javascript(self) -> None:
        assert "java" not in _named_in_the_selected_stack(STACK, KNOWN)

    def test_a_dotted_name_is_matched(self) -> None:
        doc = "## Selected Technology Stack\n**Framework:** Next.js\n## Rationale\n"

        assert _named_in_the_selected_stack(doc, KNOWN) == ["nextjs"]

    def test_a_version_number_does_not_hide_the_name(self) -> None:
        """One run's stack: "None - vanilla HTML5/CSS3/JS"."""
        doc = "## Selected Technology Stack\n**Framework:** None - vanilla HTML5/CSS3/JS\n## Rationale\n"

        assert _named_in_the_selected_stack(doc, KNOWN | {"css"}) == ["css", "html"]

    def test_a_version_does_not_make_one_name_another(self) -> None:
        """`java` still does not match `javascript`, versioned or not."""
        doc = "## Selected Technology Stack\nJavaScript ES2020, Java17\n## Rationale\n"

        assert _named_in_the_selected_stack(doc, KNOWN) == ["java", "javascript"]

    def test_a_document_without_the_section_gives_nothing(self) -> None:
        """Nothing is guessed from free text that may list rejected options."""
        assert _named_in_the_selected_stack("# Stack\n\nReact, HTML\n", KNOWN) == []


class _Reply:
    def __init__(self, content: str) -> None:
        self.content = content


class _Model:
    def invoke(self, messages):
        return _Reply("javascript")


class _Store:
    def get_all_framework_names(self):
        return sorted(KNOWN)

    def update_instructions(self, name, text):  # pragma: no cover - all are known
        raise AssertionError("nothing here needs generating")


@pytest.fixture(autouse=True)
def a_clean_cache():
    plugin_middleware._CACHE.clear()
    plugin_middleware._FAILURES.clear()
    yield
    plugin_middleware._CACHE.clear()
    plugin_middleware._FAILURES.clear()


def test_the_keywords_include_both(tmp_path, monkeypatch) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "technology_stack.md").write_text(STACK, encoding="utf-8")
    monkeypatch.setattr(plugin_middleware, "_extraction_model", lambda: _Model())

    class Shared:
        @staticmethod
        def shared():
            return _Store()

    monkeypatch.setattr("app.server.plugin_store.PluginStore", Shared)

    assert _extract_stack_keywords(str(tmp_path)) == ["javascript", "html", "node"]
