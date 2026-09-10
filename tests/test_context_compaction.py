"""Keeping an agent's conversation inside the model's window."""

import pytest

from app.agents.context_policy import ContextPolicy


# --- policy --------------------------------------------------------------

def test_defaults_are_usable_with_no_configuration():
    policy = ContextPolicy.from_environment({})
    assert policy.enabled is True
    assert policy.trigger_tokens == 60_000


def test_the_window_and_ratio_are_configurable():
    policy = ContextPolicy.from_environment(
        {"CTX_MAX_TOKENS": "32000", "CTX_SOFT_TRIGGER_RATIO": "0.75"}
    )
    assert policy.trigger_tokens == 24_000


def test_a_malformed_value_falls_back_instead_of_raising():
    """A typo in one threshold must not stop every agent from starting."""
    policy = ContextPolicy.from_environment({"CTX_MAX_TOKENS": "seventy-five-thousand"})
    assert policy.max_context_tokens == 75_000


@pytest.mark.parametrize("raw,expected", [("false", False), ("0", False), ("true", True), ("on", True)])
def test_the_master_switch_reads_the_usual_spellings(raw, expected):
    assert ContextPolicy.from_environment({"CTX_COMPACTION_ENABLED": raw}).enabled is expected


def test_an_out_of_range_ratio_is_refused():
    with pytest.raises(Exception):
        ContextPolicy(soft_trigger_ratio=1.5)


# --- context store -------------------------------------------------------

def test_context_data_lives_outside_the_run_workspace(tmp_path, monkeypatch):
    """The workspace is product output: it is listed as artifacts and archived."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("CTX_STORE_ROOT", raising=False)
    from app.agents.context_store import context_directory

    directory = context_directory("thread-1")
    assert str(directory).startswith(str(tmp_path))
    assert "workspaces" not in str(directory)


def test_a_thread_id_cannot_escape_the_context_root(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("CTX_STORE_ROOT", raising=False)
    from app.agents.context_store import context_directory, context_root

    directory = context_directory("../../etc/passwd")
    assert str(directory).startswith(str(context_root()))


def test_the_backend_satisfies_what_the_middleware_calls(tmp_path, monkeypatch):
    """A hand-written backend that misses a method fails at compaction time,
    long after construction, so assert the surface up front."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.agents.context_store import build_context_backend

    backend = build_context_backend("thread-1")
    for method in ("read", "write", "ls", "glob", "grep", "delete"):
        assert callable(getattr(backend, method, None)), method


def test_discarding_removes_the_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.agents.context_store import context_directory, discard_context

    directory = context_directory("thread-gone")
    discard_context("thread-gone")
    assert not directory.exists()


# --- middleware construction --------------------------------------------

def test_compaction_is_attached_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("CTX_COMPACTION_ENABLED", raising=False)
    from app.agents.role_agent import _compaction_middleware

    middleware = _compaction_middleware("product_manager")

    assert len(middleware) == 1
    # `SummarizationMiddleware` is a factory; the object it returns is a
    # `_DeepAgentsSummarizationMiddleware`. Assert on behaviour rather than on
    # a private class name that the package is free to rename.
    assert hasattr(middleware[0], "wrap_model_call")


def test_the_switch_removes_it_entirely(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CTX_COMPACTION_ENABLED", "false")
    from app.agents.role_agent import _compaction_middleware

    assert _compaction_middleware("product_manager") == []


def test_a_broken_summariser_degrades_to_no_compaction(tmp_path, monkeypatch):
    """No compaction is survivable. No agent is not."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    # `role_agent` does `from app.models import build_default_chat_model` at
    # module level, so the name is bound in *that* module. Patching
    # `app.models.build_default_chat_model` would never reach it.
    monkeypatch.setattr(
        "app.agents.role_agent.build_default_chat_model",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no provider")),
    )
    from app.agents.role_agent import _compaction_middleware

    assert _compaction_middleware("product_manager") == []


def test_the_agent_backend_is_not_replaced():
    """Giving the agent a real filesystem backend would re-enable the built-in
    file tools against the workspace, bypassing the approval-gated write tool."""
    import inspect

    from app.agents import role_agent

    source = inspect.getsource(role_agent.create_role_agent)
    assert "backend=" not in source


# --- overflow handling ---------------------------------------------------

@pytest.mark.parametrize("message", [
    "This model's maximum context length is 8192 tokens",
    "context_length_exceeded",
    "prompt is too long",
])
def test_overflow_is_recognised(message):
    from app.graph.workflow import _is_context_overflow

    assert _is_context_overflow(ValueError(message))


def test_an_unrelated_error_is_not_treated_as_overflow():
    from app.graph.workflow import _is_context_overflow

    assert not _is_context_overflow(ValueError("connection refused"))


def test_the_overflow_update_names_a_real_node():
    """`_route_from_stage` returns the stage verbatim and the edge map is built
    from `_NODE_NAMES`, so an unknown name is a KeyError that kills the run."""
    from app.graph.workflow import _NODE_NAMES, _context_overflow_update

    update = _context_overflow_update("principal_architect", Exception("boom"))
    assert update["stage"] in _NODE_NAMES
    assert update["stage"] == "failed"


def test_the_overflow_update_clears_the_pause_fields():
    from app.graph.workflow import _context_overflow_update

    update = _context_overflow_update("principal_architect", Exception("boom"))
    assert update["pending_approval"] is None
    assert update["pending_decision"] is None


# --- journal -------------------------------------------------------------

def test_oversized_output_keeps_head_and_tail(tmp_path, monkeypatch):
    """A build's real error is almost always in the last lines."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.tools.sandbox import MAX_OUTPUT_SIZE, _truncate

    text = "HEAD" + "x" * (MAX_OUTPUT_SIZE * 3) + "TAIL"
    out = _truncate(text, "demo")
    assert "HEAD" in out and "TAIL" in out
    assert len(out) < len(text)


def test_the_full_output_is_recoverable(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import re

    from app.tools.journal import read_entry
    from app.tools.sandbox import MAX_OUTPUT_SIZE, _truncate

    text = "y" * (MAX_OUTPUT_SIZE * 2)
    # The reference is followed by "]...", so a greedy \S+ swallows it.
    match = re.search(r"saved as ([^\]\s]+)", _truncate(text, "demo"))
    assert match
    assert read_entry(match.group(1)) == text


def test_short_output_is_untouched(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.tools.sandbox import _truncate

    assert _truncate("all good") == "all good"


def test_a_journal_failure_does_not_break_truncation(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr("app.tools.journal.write_entry", lambda *a, **k: None)
    from app.tools.sandbox import MAX_OUTPUT_SIZE, _truncate

    out = _truncate("z" * (MAX_OUTPUT_SIZE * 2), "demo")
    assert "omitted" in out


# --- request budget ------------------------------------------------------

def test_the_architect_first_request_is_bounded():
    """Measured: 7 documents = 135,821 chars made this request ~35,200 tokens,
    96% of it raw documents, sitting beside the intake that distils them."""
    from app.agents.principal_architect import INITIAL_DOCUMENT_BUDGET, build_architecture_request
    from app.documents import DocumentContent
    from app.state import RepositoryContext

    document = DocumentContent(
        source_path="x", source_type="markdown", text="D" * 135_821, truncated=False
    )
    repository = RepositoryContext(
        root_path="/w", branch="main", commit="abc", status="clean"
    )
    content = build_architecture_request("i", "t", "s", repository, document)["messages"][0]["content"]

    assert len(content) < 60_000
    assert "trimmed to" in content
    assert INITIAL_DOCUMENT_BUDGET > 0
