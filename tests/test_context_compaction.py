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


def _role_agent_tool_names(tmp_path, **kwargs):
    """Build a role agent and return the tool names its model is offered."""
    from pydantic import BaseModel

    from app.agents.role_agent import create_role_agent

    class _Out(BaseModel):
        summary: str

    agent = create_role_agent(
        name="probe",
        stage="probe",
        system_prompt="probe",
        response_format=_Out,
        model="openai:gpt-4o-mini",
        repo_root=str(tmp_path),
        **kwargs,
    )
    return set(agent.nodes["tools"].bound._tools_by_name)


def test_the_agent_is_offered_no_built_in_write_tool(tmp_path):
    """`write_artifact` must be the only way an agent can change a file.

    The approval gate interrupts on `write_artifact`. Any built-in mutation tool
    reaching the model is a second write path that the gate does not cover, so
    none of them may be registered. This is asserted on the compiled agent
    rather than by reading the source, because what matters is the tool surface
    the model actually sees.
    """
    names = _role_agent_tool_names(tmp_path)

    assert "write_artifact" in names
    assert not {"write_file", "edit_file", "delete", "execute"} & names


def test_the_agent_can_edit_an_existing_file_not_only_replace_it(tmp_path):
    """Whole-file replacement was the only way to change anything.

    Correcting one sentence in a 71KB specification meant reproducing the whole
    document in a single tool call. Rather than do that, the architect wrote a
    shorter second file, the reviewer read both, and the run stopped on
    contradictions that existed only because there were two files.
    """
    names = _role_agent_tool_names(tmp_path)

    assert "edit_artifact" in names
    assert "write_artifact" in names


def test_editing_a_file_stops_at_the_same_approval_gate_as_writing(tmp_path):
    """An edit changes a file, so it cannot be the ungated way around the gate."""
    from app.tools.agent_toolkit import HUMAN_APPROVAL_TOOLS

    assert "edit_artifact" in HUMAN_APPROVAL_TOOLS


def test_an_edit_approval_shows_the_change_not_an_empty_summary(tmp_path):
    """The description read `content`, which an edit call does not carry.

    A reviewer approving an edit saw a blank summary - the one case where seeing
    what actually changes matters most.
    """
    from app.agents.role_agent import describe_artifact_write

    describe = describe_artifact_write(str(tmp_path), "principal_architect", "design")
    rendered = describe(
        {"args": {"relative_path": "docs/spec.md", "find": "soft-deleted", "replace": "hard-deleted"}},
        None,
        None,
    )

    assert "soft-deleted" in rendered
    assert "hard-deleted" in rendered
    assert "docs/spec.md" in rendered


def test_the_agent_read_tools_are_backed_by_the_real_workspace(tmp_path):
    """The read-only built-ins must work, not merely be denied.

    They used to be registered over an in-memory backend and then denied on
    every path, so the model kept calling them and kept getting `permission
    denied`. One architect stage read that denial as "I cannot write at all",
    asked the human for permission instead of answering, and failed the run for
    producing no structured response.
    """
    from deepagents.backends import FilesystemBackend

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "spec.md").write_text("# Spec\n", encoding="utf-8")

    names = _role_agent_tool_names(tmp_path)
    assert {"ls", "read_file", "glob", "grep"} <= names

    backend = FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True)
    assert [e["path"] for e in backend.ls("/docs").entries] == ["/docs/spec.md"]
    assert backend.read("/docs/spec.md").file_data["content"] == "# Spec\n"


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

    # The request must be bounded by the document budget, not by document size.
    # A 135k-char upload and a multi-megabyte one both produce a brief of roughly
    # INITIAL_DOCUMENT_BUDGET + fixed framing; assert that bound, not an absolute
    # character count (which is only as large as the configured budget).
    assert len(content) <= INITIAL_DOCUMENT_BUDGET + 1_000
    assert "trimmed to" in content
    assert INITIAL_DOCUMENT_BUDGET > 0


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------
#
# Both trees live under DATA_DIR, which is one volume shared by the API and
# every worker. Neither had any bound: the journal grows by one >50 KB file per
# truncated stream, the context store by one file per agent attempt.


def _age(path, hours):
    import os, time
    stamp = time.time() - hours * 3600
    os.utime(path, (stamp, stamp))


def test_an_expired_journal_entry_is_deleted_and_a_fresh_one_is_kept(tmp_path, monkeypatch):
    monkeypatch.setenv("CTX_JOURNAL_ROOT", str(tmp_path))
    from app.tools.journal import journal_root, prune, read_entry, write_entry

    stale = write_entry("stale", "old output")
    fresh = write_entry("fresh", "new output")
    _age(journal_root() / stale, 100)

    assert prune() == 1
    assert read_entry(stale) is None
    assert read_entry(fresh) == "new output"


def test_zero_retention_keeps_journal_entries_forever(tmp_path, monkeypatch):
    monkeypatch.setenv("CTX_JOURNAL_ROOT", str(tmp_path))
    monkeypatch.setenv("CTX_JOURNAL_RETENTION_HOURS", "0")
    from app.tools.journal import journal_root, prune, write_entry

    name = write_entry("ancient", "keep me")
    _age(journal_root() / name, 10_000)

    assert prune() == 0


def test_a_malformed_retention_value_falls_back_instead_of_raising(monkeypatch):
    """Same never-raise convention as ContextPolicy.from_environment."""
    from app.tools import journal

    monkeypatch.setenv("CTX_JOURNAL_RETENTION_HOURS", "three days")

    assert journal.retention_seconds() == journal.DEFAULT_RETENTION_HOURS * 3600.0


def test_pruning_context_leaves_the_directories_for_concurrent_runs(tmp_path, monkeypatch):
    """Two runs share a per-agent directory; removing one mid-run breaks it."""
    monkeypatch.setenv("CTX_STORE_ROOT", str(tmp_path))
    from app.agents.context_store import context_directory, prune

    directory = context_directory("principal_architect")
    history = directory / "conversation_history"
    history.mkdir(parents=True, exist_ok=True)
    (history / "session_stale.md").write_text("old")
    (history / "session_live.md").write_text("in flight")
    _age(history / "session_stale.md", 100)

    assert prune() == 1
    assert not (history / "session_stale.md").exists()
    assert (history / "session_live.md").exists()
    assert history.is_dir()


# ---------------------------------------------------------------------------
# Reading back what truncation removed
# ---------------------------------------------------------------------------


def test_journalled_output_can_be_read_back_by_the_agent(tmp_path, monkeypatch):
    """Without this the truncation pointer names a file nothing can fetch."""
    monkeypatch.setenv("CTX_JOURNAL_ROOT", str(tmp_path))
    import re

    from app.tools.agent_toolkit import build_journal_read_tool
    from app.tools.sandbox import _truncate

    output = "\n".join(f"line {i}" for i in range(20_000)) + "\nFATAL: the real error"
    pointer = _truncate(output, "build")
    reference = re.search(r"saved as ([^\]\s]+)", pointer).group(1)

    result = build_journal_read_tool().invoke({"reference": reference})

    assert "FATAL: the real error" in result


def test_a_read_back_is_bounded_so_it_cannot_reoverflow_the_window(tmp_path, monkeypatch):
    monkeypatch.setenv("CTX_JOURNAL_ROOT", str(tmp_path))
    from app.tools.agent_toolkit import JOURNAL_TOOL_MAX_CHARS, build_journal_read_tool
    from app.tools.journal import write_entry

    reference = write_entry("huge", "x" * 500_000)

    result = build_journal_read_tool().invoke({"reference": reference})

    assert len(result) < JOURNAL_TOOL_MAX_CHARS + 500


def test_an_unknown_reference_is_a_tool_result_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.setenv("CTX_JOURNAL_ROOT", str(tmp_path))
    from app.tools.agent_toolkit import build_journal_read_tool

    assert "error" in build_journal_read_tool().invoke({"reference": "nope.log"})


def test_a_read_back_cannot_escape_the_journal_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("CTX_JOURNAL_ROOT", str(tmp_path))
    from app.tools.agent_toolkit import build_journal_read_tool

    result = build_journal_read_tool().invoke({"reference": "../../../etc/passwd"})

    assert "error" in result


# ---------------------------------------------------------------------------
# The first message, which compaction cannot rescue
# ---------------------------------------------------------------------------
#
# SummarizationMiddleware compacts *between* model calls, keeping the most
# recent CTX_KEEP_MESSAGES. A single oversized first message has nothing older
# to evict, so the call overflows and the middleware never runs.


@pytest.mark.parametrize(
    "builder_path, what",
    [
        ("app.agents.architecture_reviewer.build_architecture_review_request", "review"),
        ("app.agents.scrum_master.build_sprint_planning_request", "sprint planning"),
    ],
)
def test_an_oversized_specification_is_trimmed_before_it_is_sent(builder_path, what):
    import importlib

    module_name, attribute = builder_path.rsplit(".", 1)
    build = getattr(importlib.import_module(module_name), attribute)

    body = build("S" * 400_000, "/workspace")["messages"][0]["content"]

    assert len(body) < 70_000, f"the {what} request did not bound the specification"
    assert "were trimmed to" in body, f"the {what} request trimmed silently"


def test_a_specification_inside_the_budget_is_sent_whole():
    from app.agents.scrum_master import build_sprint_planning_request

    body = build_sprint_planning_request("A short specification.", "/w")["messages"][0]["content"]

    assert "A short specification." in body
    assert "trimmed" not in body
