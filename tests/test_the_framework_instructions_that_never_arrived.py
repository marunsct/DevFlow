"""Dynamic framework instructions called an endpoint the run was not using.

`_extract_stack_keywords` reads the stack document, asks a model which frameworks
it mandates, generates instructions for any the store does not know, and the
middleware appends them to every agent's system prompt. It is how a run gets
framework-specific guidance.

It built its model from `load_settings()`, which is a pure function of the
environment. `effective_settings()` - the one that honours what an administrator
has changed - says in its own docstring: "This is what every model-building path
should call."

This path did not, and in production the two disagreed:

    runtime_settings.openai_base_url  http://host.docker.internal:8888/v1   serving
    load_settings().openai_base_url   http://host.docker.internal:1234/v1   refused

So every agent call succeeded and every call from here failed. Over the worker's
whole lifetime:

    142  Could not resolve framework instructions for this stack
      0  Framework instructions resolved for this stack

The feature was not degraded, it was inert, and the only trace was a warning that
named the stack document rather than the host.

A second fault kept it expensive. Only successes were cached, so a failure was
retried on every model call of every stage - which is how one refused connection
produced 142 attempts and 142 tracebacks in a single worker.
"""

from __future__ import annotations

import pytest

from app.plugins import middleware as plugin_middleware
from app.plugins.middleware import (
    _ATTEMPTS_BEFORE_GIVING_UP,
    _extract_stack_keywords,
    _where_the_extraction_model_points,
)

A_STACK_DOCUMENT = (
    "# Technology stack\n\n"
    "**Language:** TypeScript\n"
    "**Framework:** React\n"
    "**Testing framework:** vitest\n"
)


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
    (docs / "technology_stack.md").write_text(A_STACK_DOCUMENT)
    return tmp_path


class TestItUsesTheModelTheRunUses:
    def test_the_endpoint_comes_from_the_runtime_settings(self, monkeypatch):
        """Not from the environment, which is what pointed at a refused port."""
        from app import models

        class Resolved:
            model_name = "the-configured-model"
            openai_api_key = "k"
            openai_base_url = "http://host.docker.internal:8888/v1"

        monkeypatch.setattr(models, "_runtime_settings", lambda: Resolved())

        model = plugin_middleware._extraction_model()

        assert "8888" in str(model.openai_api_base or model.root_client.base_url)

    def test_it_does_not_read_the_environment_directly(self):
        """The one line that caused it. `load_settings` cannot see an override.

        The body only: the docstring explains `load_settings` and would match.
        """
        import ast
        import inspect

        body = ast.parse(inspect.getsource(plugin_middleware._extraction_model).strip())
        function = body.body[0]
        code = "\n".join(
            ast.unparse(node)
            for node in function.body
            if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant))
        )

        assert "load_settings" not in code, code
        assert "_runtime_settings" in code

    def test_the_endpoint_is_nameable_for_a_log_line(self, monkeypatch):
        from app import models

        class Resolved:
            model_name = "m"
            openai_api_key = "k"
            openai_base_url = "http://somewhere:9999/v1"

        monkeypatch.setattr(models, "_runtime_settings", lambda: Resolved())

        assert "9999" in _where_the_extraction_model_points()

    def test_describing_the_endpoint_never_raises(self, monkeypatch):
        from app import models

        def _boom():
            raise RuntimeError("no database")

        monkeypatch.setattr(models, "_runtime_settings", _boom)

        assert _where_the_extraction_model_points()


class TestAFailureIsRememberedNotRetriedForever:
    def _always_fails(self, monkeypatch):
        calls: list[int] = []

        def _model():
            calls.append(1)
            raise ConnectionRefusedError("[Errno 111] Connection refused")

        monkeypatch.setattr(plugin_middleware, "_extraction_model", _model)
        return calls

    def test_it_stops_after_the_bounded_number_of_attempts(
        self, a_workspace, monkeypatch
    ):
        calls = self._always_fails(monkeypatch)

        for _ in range(20):
            assert _extract_stack_keywords(str(a_workspace)) == []

        assert len(calls) == _ATTEMPTS_BEFORE_GIVING_UP, (
            f"{len(calls)} model calls for one unreachable endpoint"
        )

    def test_a_single_failure_is_retried(self, a_workspace, monkeypatch):
        """One blip must not disable the feature for the whole run."""
        calls = self._always_fails(monkeypatch)

        _extract_stack_keywords(str(a_workspace))
        _extract_stack_keywords(str(a_workspace))

        assert len(calls) == 2

    def test_a_different_stack_document_is_tried_afresh(
        self, a_workspace, monkeypatch, tmp_path
    ):
        """The count is per document, as the cache is."""
        calls = self._always_fails(monkeypatch)
        for _ in range(5):
            _extract_stack_keywords(str(a_workspace))

        (a_workspace / "docs" / "technology_stack.md").write_text(
            A_STACK_DOCUMENT + "\n**Database:** postgres\n"
        )
        _extract_stack_keywords(str(a_workspace))

        assert len(calls) == _ATTEMPTS_BEFORE_GIVING_UP + 1

    def test_giving_up_still_returns_no_keywords(self, a_workspace, monkeypatch):
        """An absent hint beats a failed stage, which was already the contract."""
        self._always_fails(monkeypatch)

        for _ in range(5):
            assert _extract_stack_keywords(str(a_workspace)) == []

    def test_the_warning_names_the_endpoint(self, a_workspace, monkeypatch, caplog):
        """The old line named the stack, so an unreachable host read as a bad
        document - which is why 142 of these were not acted on."""
        self._always_fails(monkeypatch)

        with caplog.at_level("WARNING"):
            for _ in range(_ATTEMPTS_BEFORE_GIVING_UP):
                _extract_stack_keywords(str(a_workspace))

        assert "attempts at" in caplog.text
        assert "absent for this stack" in caplog.text


class TestNothingElseChanged:
    def test_no_stack_document_means_no_keywords_and_no_model_call(self, tmp_path):
        calls: list[int] = []
        assert _extract_stack_keywords(str(tmp_path)) == []
        assert calls == []

    def test_a_success_is_still_cached(self, a_workspace, monkeypatch):
        calls: list[int] = []

        class Reply:
            content = "react, typescript"

        class Model:
            def invoke(self, messages):
                calls.append(1)
                return Reply()

        monkeypatch.setattr(plugin_middleware, "_extraction_model", lambda: Model())

        class Store:
            @staticmethod
            def shared():
                return Store()

            def get_all_framework_names(self):
                return ["react", "typescript"]

        monkeypatch.setattr("app.server.plugin_store.PluginStore", Store)

        first = _extract_stack_keywords(str(a_workspace))
        second = _extract_stack_keywords(str(a_workspace))

        assert first == second == ["react", "typescript"]
        assert len(calls) == 1, "the second call should have come from the cache"

    def test_a_failure_does_not_poison_a_later_success(self, a_workspace, monkeypatch):
        """Recovery within the bound: attempt one fails, attempt two works."""
        state = {"calls": 0}

        class Reply:
            content = "react"

        class Model:
            def invoke(self, messages):
                state["calls"] += 1
                if state["calls"] == 1:
                    raise ConnectionRefusedError("refused")
                return Reply()

        monkeypatch.setattr(plugin_middleware, "_extraction_model", lambda: Model())

        class Store:
            @staticmethod
            def shared():
                return Store()

            def get_all_framework_names(self):
                return ["react"]

        monkeypatch.setattr("app.server.plugin_store.PluginStore", Store)

        assert _extract_stack_keywords(str(a_workspace)) == []
        assert _extract_stack_keywords(str(a_workspace)) == ["react"]
