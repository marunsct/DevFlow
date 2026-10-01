"""A framework the selected stack turns down gets none of its instructions.

One run's selected stack read "vanilla JavaScript (ES2020, browser-native; no
TypeScript ...)" and "The brief's 'no external dependencies beyond basic
HTML/CSS/JS' rules out Vue/Svelte/React/Alpine outright". The selected section
was matched word by word, so every agent of that run was given the React, Vue
and TypeScript instructions - and, from `python3 -m http.server` under
"Additional tools", the Python ones, which open "You are working in a Python
environment".
"""

from __future__ import annotations

import pytest

from app.plugins import middleware as plugin_middleware
from app.plugins.middleware import (
    _extract_stack_keywords,
    _named_in_the_selected_stack,
    _turned_down_by_the_selected_stack,
)

#: That run's selected section, shortened, in `artifact_document`'s layout.
STACK = """# Technology Stack

## Selected Technology Stack
- **Language:** HTML + CSS + vanilla JavaScript (ES2020, browser-native; no TypeScript, no transpile, no build step)
- **Framework:** None — static single-page app driven by vanilla DOM APIs; no framework of any kind
- **Frontend framework:** None — hand-written index.html + styles.css. The brief's 'no external dependencies beyond basic HTML/CSS/JS' rules out Vue/Svelte/React/Alpine outright, so the UI is the plain HTML/CSS the platform already provides
- **Database:** None — no database. Persistence is browser localStorage
- **Testing framework:** node:test (Node's built-in runner) for the logic. PLUS Playwright (Node, installed test-only) for the page itself
- **Additional tools:** wc -l over the shipped source, python3 -m http.server — already in the runtime, no package to add

## Rationale
Vue 3 / Svelte / React (the standard choice for a reactive list UI) need a compiler.
"""

KNOWN = {
    "css", "html", "javascript", "node", "playwright", "python", "react",
    "typescript", "vanilla javascript", "vue", "postgres",
}


def test_that_run_s_stack_selects_only_what_it_chose() -> None:
    assert _named_in_the_selected_stack(STACK, KNOWN) == [
        "css", "html", "javascript", "node", "playwright", "vanilla javascript",
    ]


@pytest.mark.parametrize("name", ["react", "vue", "typescript"])
def test_a_rejected_name_is_turned_down(name: str) -> None:
    assert _turned_down_by_the_selected_stack(STACK, name)


def test_a_command_under_the_tools_is_not_the_stack_s_language() -> None:
    assert "python" not in _named_in_the_selected_stack(STACK, KNOWN)
    assert _turned_down_by_the_selected_stack(STACK, "python")


def test_a_chosen_name_is_not_turned_down() -> None:
    assert not _turned_down_by_the_selected_stack(STACK, "playwright")
    assert not _turned_down_by_the_selected_stack(STACK, "javascript")


def test_a_name_the_section_never_mentions_is_left_to_the_model() -> None:
    assert not _turned_down_by_the_selected_stack(STACK, "postgres")


@pytest.mark.parametrize(
    ("line", "chosen", "refused"),
    [
        ("**Framework:** Vue instead of React", "vue", "react"),
        ("**Framework:** Not React but Vue", "vue", "react"),
        ("**Framework:** React (no Redux)", "react", "redux"),
        ("**Language:** JavaScript. TypeScript is not used", "javascript", "typescript"),
        ("**Framework:** Django rather than Flask", "django", "flask"),
    ],
)
def test_the_rejection_follows_the_clause(line: str, chosen: str, refused: str) -> None:
    doc = f"## Selected Technology Stack\n{line}\n## Rationale\n"
    found = _named_in_the_selected_stack(doc, {chosen, refused})

    assert found == [chosen]


class _Reply:
    def __init__(self, content: str) -> None:
        self.content = content


class _Model:
    """The extraction model read the rationale too, and named what it rejected."""

    def invoke(self, messages):
        return _Reply("javascript, react, vue, typescript, python")


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


def test_what_the_model_reads_out_of_a_rejection_is_dropped(tmp_path, monkeypatch) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "technology_stack.md").write_text(STACK, encoding="utf-8")
    monkeypatch.setattr(plugin_middleware, "_extraction_model", lambda: _Model())

    class Shared:
        @staticmethod
        def shared():
            return _Store()

    monkeypatch.setattr("app.server.plugin_store.PluginStore", Shared)

    keywords = _extract_stack_keywords(str(tmp_path))

    assert not {"react", "vue", "typescript", "python"} & set(keywords)
    assert {"javascript", "html", "playwright", "node"} <= set(keywords)


# --- a version written onto a name ------------------------------------------


def test_a_versioned_name_is_read_as_the_known_one() -> None:
    """One run's extraction returned `html5` and `css3`, and generated notes
    for both - `<canvas>`, `<video>`, animations - beside the seeded ones."""
    from app.plugins.middleware import _the_known_name_for

    known = {"html", "css", "python", "vue"}

    assert [_the_known_name_for(n, known) for n in ("html5", "css3", "python3", "vue 3")] == [
        "html", "css", "python", "vue",
    ]


def test_an_unknown_or_unversioned_name_is_kept() -> None:
    from app.plugins.middleware import _the_known_name_for

    assert _the_known_name_for("es2020", {"html"}) == "es2020"
    assert _the_known_name_for("html", {"html"}) == "html"


class _VersionedModel:
    def invoke(self, messages):
        return _Reply("html5, css3, javascript")


class _StoreWithAStaleNote(_Store):
    """`html5` was generated and stored by the run before this fix."""

    def get_all_framework_names(self):
        return sorted(KNOWN | {"html5"})


def test_nothing_is_generated_for_a_versioned_name(tmp_path, monkeypatch) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "technology_stack.md").write_text(
        "## Selected Technology Stack\n- **Language:** HTML5, CSS3, JavaScript\n## Rationale\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(plugin_middleware, "_extraction_model", lambda: _VersionedModel())

    class Shared:
        @staticmethod
        def shared():
            return _StoreWithAStaleNote()

    monkeypatch.setattr("app.server.plugin_store.PluginStore", Shared)

    keywords = _extract_stack_keywords(str(tmp_path))

    assert "html5" not in keywords and "css3" not in keywords
    assert {"html", "css", "javascript"} <= set(keywords)
