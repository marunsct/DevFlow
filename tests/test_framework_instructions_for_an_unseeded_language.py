"""A framework the seed does not cover must still get instructions, and not cost the others.

For a stack that names a language the seed does not list - a vanilla JavaScript
page is enough - the middleware generates its instructions with a model call.
That call was a system message alone, and an OpenAI-compatible local server
answers it with 400 "At least one non-system message is required". The
exception reached the outer handler, which discarded every framework found,
counted an attempt, and after the second gave up for the run: the worker log
read "Could not resolve framework instructions after 2 attempts" and no agent in
the run received a single framework instruction, for any framework.
"""

from __future__ import annotations

import pytest

from app.plugins import middleware as plugin_middleware
from app.plugins.middleware import _extract_stack_keywords


@pytest.fixture(autouse=True)
def a_clean_cache():
    plugin_middleware._CACHE.clear()
    plugin_middleware._FAILURES.clear()
    yield
    plugin_middleware._CACHE.clear()
    plugin_middleware._FAILURES.clear()


@pytest.fixture
def a_workspace(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "technology_stack.md").write_text("# Stack\n\nJavaScript, HTML, CSS; Postgres\n")
    return tmp_path


class _Reply:
    def __init__(self, content: str) -> None:
        self.content = content


class _AServerThatRefusesSystemOnlyRequests:
    """The contract the local server enforces."""

    def __init__(self, detected: str) -> None:
        self.detected = detected
        self.requests: list[list] = []

    def invoke(self, messages):
        self.requests.append(messages)
        if all(getattr(m, "type", "") == "system" for m in messages):
            raise ValueError("400: At least one non-system message is required.")
        if len(self.requests) == 1:
            return _Reply(self.detected)
        return _Reply("- Use strict mode.\n- Validate input.")


class _Store:
    def __init__(self, known: list[str]) -> None:
        self.known = list(known)
        self.saved: dict[str, str] = {}

    def get_all_framework_names(self):
        return list(self.known)

    def update_instructions(self, name, text):
        self.saved[name] = text
        self.known.append(name)


@pytest.fixture
def store(monkeypatch):
    the_store = _Store(known=["postgres"])

    class Shared:
        @staticmethod
        def shared():
            return the_store

    monkeypatch.setattr("app.server.plugin_store.PluginStore", Shared)
    return the_store


class TestAnUnseededLanguage:
    def test_its_instructions_are_generated_and_kept(self, a_workspace, store, monkeypatch):
        model = _AServerThatRefusesSystemOnlyRequests("javascript, postgres")
        monkeypatch.setattr(plugin_middleware, "_extraction_model", lambda: model)

        keywords = _extract_stack_keywords(str(a_workspace))

        assert keywords == ["javascript", "postgres"]
        assert "javascript" in store.saved

    def test_every_request_carries_a_non_system_message(self, a_workspace, store, monkeypatch):
        model = _AServerThatRefusesSystemOnlyRequests("javascript")
        monkeypatch.setattr(plugin_middleware, "_extraction_model", lambda: model)

        _extract_stack_keywords(str(a_workspace))

        for request in model.requests:
            assert any(getattr(m, "type", "") != "system" for m in request)


class TestOneFailureCostsOnlyItself:
    def test_the_seeded_frameworks_survive_a_failed_generation(self, a_workspace, store, monkeypatch):
        class GenerationFails(_AServerThatRefusesSystemOnlyRequests):
            def invoke(self, messages):
                if self.requests:
                    self.requests.append(messages)
                    raise ConnectionError("generation failed")
                return super().invoke(messages)

        monkeypatch.setattr(plugin_middleware, "_extraction_model", lambda: GenerationFails("javascript, postgres"))

        assert _extract_stack_keywords(str(a_workspace)) == ["postgres"]

    def test_it_is_not_counted_as_a_failed_attempt(self, a_workspace, store, monkeypatch):
        """The run keeps its instructions rather than giving up after two tries."""
        class GenerationFails(_AServerThatRefusesSystemOnlyRequests):
            def invoke(self, messages):
                if self.requests:
                    raise ConnectionError("generation failed")
                return super().invoke(messages)

        monkeypatch.setattr(plugin_middleware, "_extraction_model", lambda: GenerationFails("javascript, postgres"))

        _extract_stack_keywords(str(a_workspace))

        assert not plugin_middleware._FAILURES
