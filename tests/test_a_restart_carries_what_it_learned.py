"""A restarted stage keeps the facts its dead attempt established.

Item 9 of the hardening plan (B13, `docs/improvement-plan.md §E1`). `workflow.py` said so in its
own comment: a stage that produces no structured response restarts on a fresh
conversation, and every attempt re-read the same files and re-ran the same
commands. One run spent 170 tool calls across three attempts of one stage.

Measured again on one run: the two stages that spun cost 100 and 80 model
calls across their attempts, while the fifteen that finished averaged under ten.
The waste is not the failed attempt, it is that the next one starts blind.

Deliberately a summary and not a transcript. The conversation is cleared
because it was not working - replaying it reproduces the failure, which is what
clearing `pending_inner_thread_id` exists to prevent - so only what the attempt
*established* carries: files seen, commands run and how they exited. Facts, not
reasoning.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agents import stage_memory
from app.agents.carry_over import MAX_FILES_NAMED, carry_over_note


@pytest.fixture(autouse=True)
def clean_memory():
    stage_memory.forget_everything()
    yield
    stage_memory.forget_everything()


def _remember_reads(thread_id: str, *paths: str) -> None:
    """What `_note_if_repeated` leaves behind, in its own shape.

    Keyed on the resolved absolute path, which is what makes two spellings of
    one file the same key - and what the note must not repeat back.
    """
    stage_memory._MEMORY[(thread_id, "read_digests")] = {
        path: ("size:mtime", {"digest": 1}) for path in paths
    }


class TestWhatCarriesOver:
    def test_the_files_the_dead_attempt_read_are_named(self):
        _remember_reads("t1", "app/index.html", "app/app.js")

        note = carry_over_note("t1", None)

        assert "app/index.html" in note
        assert "app/app.js" in note
        assert "have not changed since" in note

    def test_it_tells_the_attempt_not_to_redo_them(self):
        _remember_reads("t1", "app/app.js")

        note = carry_over_note("t1", None)

        assert "will return what it returned before" in note
        assert "write your structured response" in note

    def test_a_long_list_is_truncated_and_says_so(self):
        _remember_reads("t1", *[f"app/f{n}.js" for n in range(MAX_FILES_NAMED + 5)])

        note = carry_over_note("t1", None)

        assert "... and 5 more" in note

    def test_nothing_established_means_no_note(self):
        """An empty preamble is one more thing for the next attempt to read past."""
        assert carry_over_note("never-ran", None) == ""

    def test_another_stage_s_memory_is_not_borrowed(self):
        _remember_reads("t1", "app/app.js")
        assert carry_over_note("t2", None) == ""

    def test_recall_hands_out_a_copy(self):
        """A summary must not be able to mutate the record it summarises."""
        _remember_reads("t1", "app/app.js")

        recalled = stage_memory.recall("t1", "read_digests")
        recalled["injected"] = "x"

        assert "injected" not in stage_memory.recall("t1", "read_digests")


class TestTheCommandsItRan:
    def test_commands_and_exit_codes_carry(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "app.tools.sandbox.read_execution_ledger",
            lambda root, limit=200, **kwargs: [
                {"command": ["npm", "install"], "returncode": 0},
                {"command": ["node", "--test"], "returncode": 1},
            ],
        )
        _remember_reads("t1", "app/app.js")

        note = carry_over_note("t1", str(tmp_path))

        assert "npm install  -> exit 0" in note
        assert "node --test  -> exit 1" in note

    def test_a_broken_ledger_never_fails_the_restart(self, tmp_path, monkeypatch):
        def explode(*args, **kwargs):
            raise OSError("ledger is gone")

        monkeypatch.setattr("app.tools.sandbox.read_execution_ledger", explode)
        _remember_reads("t1", "app/app.js")

        note = carry_over_note("t1", str(tmp_path))

        # The files still carry; only the commands are lost.
        assert "app/app.js" in note


class _Agent:
    """A role agent that answers at once, answers nothing, or raises."""

    def __init__(self, answer="answer", raises=None):
        self.answer, self.raises, self.calls = answer, raises, []

    def get_state(self, config):
        return SimpleNamespace(values={}, next=())

    def invoke(self, request, config=None):
        self.calls.append((request, config["configurable"]["thread_id"]))
        if self.raises is not None:
            raise self.raises
        return {"messages": [], "structured_response": self.answer}


def _run_once(agent, root, carry_over):
    from app.graph.workflow import _run_gated_agent

    return _run_gated_agent(
        {"stage": "principal_architect", "repository": SimpleNamespace(root_path=str(root)),
         "stage_carry_over": carry_over},
        {"configurable": {"thread_id": "outer"}},
        stage_name="principal_architect", agent=agent,
        initial_request={"messages": [{"role": "user", "content": "write"}]},
        output_key="out", next_stage="architecture_review",
    )


class TestTheWorkflowWiring:
    """The note is recorded on restart, read once, and then dropped."""

    def test_the_restart_records_it(self):
        from app.graph.workflow import _restart_on_a_fresh_conversation

        _remember_reads("t1", "app/app.js")
        state = {"stage_carry_over": {"other_stage": "its own note"}}

        update = _restart_on_a_fresh_conversation(state, "specialist_ui_ux_0", "t1", "why")

        assert "app/app.js" in update["stage_carry_over"]["specialist_ui_ux_0"]
        assert update["stage_carry_over"]["other_stage"] == "its own note"

    def test_a_fresh_attempt_prepends_it(self, tmp_path):
        """Prepended, so it is read before the stage's own instructions rather
        than after them."""
        agent = _Agent()

        _run_once(agent, tmp_path, {"principal_architect": "THE NOTE"})

        request, _thread = agent.calls[0]
        assert request["messages"][0] == {"role": "user", "content": "THE NOTE"}
        assert request["messages"][-1] == {"role": "user", "content": "write"}

    def test_another_stage_s_note_is_not_prepended(self, tmp_path):
        agent = _Agent()

        _run_once(agent, tmp_path, {"technical_lead": "THE NOTE"})

        request, _thread = agent.calls[0]
        assert request["messages"] == [{"role": "user", "content": "write"}]

    def test_success_drops_it(self, tmp_path):
        """A stage name recurs across sprints; a stale note would describe
        files a different task had read."""
        update = _run_once(_Agent(), tmp_path, {"principal_architect": "THE NOTE", "technical_lead": "kept"})

        assert update["out"] == "answer"
        assert update["stage_carry_over"] == {"technical_lead": "kept"}

    def test_the_state_declares_the_field(self):
        from app.graph.workflow import WorkflowGraphState

        assert "stage_carry_over" in WorkflowGraphState.__annotations__


class TestThePathsAreOnesTheToolsAccept:
    """Named relative to the workspace, as every tool here names them.

    `read_digests` is keyed on the resolved absolute path. Written straight
    into the note, that hands the next attempt
    `/app/data/workspaces/default/todo-run9-.../app.js`, which no tool accepts.
    Seen in one run, where the note fired five times and named absolute
    paths every time - and an absolute path in front of a model is how the
    invented `/project/...` prefix gets invented in the first place.
    """

    def test_an_absolute_path_inside_the_workspace_is_relativised(self, tmp_path):
        workspace = tmp_path / "todo-run9"
        (workspace / "app").mkdir(parents=True)
        target = workspace / "app" / "app.js"
        target.write_text("x")
        _remember_reads("t1", str(target))

        note = carry_over_note("t1", str(workspace))

        assert "app/app.js" in note
        assert str(workspace) not in note, "an absolute path reached the model"

    def test_a_path_outside_the_workspace_is_left_as_it_is(self, tmp_path):
        workspace = tmp_path / "todo-run9"
        workspace.mkdir()
        outside = tmp_path / "elsewhere.js"
        outside.write_text("x")
        _remember_reads("t1", str(outside))

        note = carry_over_note("t1", str(workspace))

        assert "elsewhere.js" in note

    def test_without_a_workspace_the_paths_are_unchanged(self):
        _remember_reads("t1", "/app/data/workspaces/x/app.js")
        assert "/app/data/workspaces/x/app.js" in carry_over_note("t1", None)

    def test_two_spellings_of_one_file_are_named_once(self, tmp_path):
        workspace = tmp_path / "w"
        (workspace / "a").mkdir(parents=True)
        target = workspace / "a" / "app.js"
        target.write_text("x")
        _remember_reads("t1", str(target), str(workspace / "a" / ".." / "a" / "app.js"))

        note = carry_over_note("t1", str(workspace))

        assert note.count("a/app.js") == 1


class TestTheWorkspaceReachesTheNote:
    """The parameter existed and nothing passed it.

    `_restart_on_a_fresh_conversation` gained `repo_root` so the carry-over
    could name files relative to the workspace, and every call site kept using
    the default of None. The unit test for the None case passed, the relative
    -path tests passed, and one run still received

        Files you already read, and which have not changed since:
          /app/data/workspaces/default/todo-run12-.../todo-list-app/app.js

    which no tool accepts. Only reading a live run's transcript showed it.
    """

    @pytest.mark.parametrize("how", ["spun on a fresh attempt", "spun on a resume", "gave no answer"])
    def test_every_restart_passes_the_workspace(self, tmp_path, monkeypatch, how):
        """Each of the three ways `_run_gated_agent` restarts a stage hands it the workspace."""
        from app.graph import workflow

        roots = []

        def restart(state, stage_name, inner_thread_id, why, repo_root=None):
            roots.append(repo_root)
            return {"stage": "restarted"}

        monkeypatch.setattr(workflow, "_restart_on_a_fresh_conversation", restart)
        monkeypatch.setattr(workflow, "_answer_left_in_a_spinning_stage", lambda *a, **k: None)
        state = {"stage": "principal_architect", "repository": SimpleNamespace(root_path=str(tmp_path))}
        if how == "spun on a fresh attempt":
            agent = _Agent(raises=RuntimeError("GraphRecursionError: recursion limit reached"))
        elif how == "spun on a resume":
            agent = _Agent()

            def spin(*args, **kwargs):
                raise RuntimeError("GraphRecursionError: recursion limit reached")

            monkeypatch.setattr(workflow, "resume_with_decision", spin)
            state.update(pending_decision={"type": "approve"}, pending_inner_thread_id="outer:principal_architect:1")
        else:
            agent = _Agent(answer=None)
            monkeypatch.setattr(workflow, "_answer_written_into_the_conversation", lambda *a, **k: None)
            monkeypatch.setattr(workflow, "_nudge_for_the_structured_response", lambda *a, **k: None)
            monkeypatch.setattr(workflow, "_the_answer_in_parts", lambda *a, **k: None)

        update = workflow._run_gated_agent(
            state, {"configurable": {"thread_id": "outer"}},
            stage_name="principal_architect", agent=agent,
            initial_request={"messages": [{"role": "user", "content": "write"}]},
            output_key="out", next_stage="architecture_review",
        )

        assert update == {"stage": "restarted"}
        assert roots == [str(tmp_path)], "a carry-over without the workspace names absolute paths"

    def test_the_root_is_read_defensively(self):
        """A missing repository must not turn a restart into a failure."""
        from app.graph.workflow import _repository_root

        assert _repository_root({}) is None
        assert _repository_root({"repository": None}) is None

    def test_it_returns_the_root_when_there_is_one(self):
        from app.graph.workflow import _repository_root

        class _Repo:
            root_path = "/app/data/workspaces/default/todo-run12"

        assert _repository_root({"repository": _Repo()}) == _Repo.root_path
