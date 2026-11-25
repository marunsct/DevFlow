"""A suite writer that spends every way to answer leaves its files to the suite's own checks (LF.1365).

Measured on a medium run, seventeen hours in: a later sprint's acceptance-suite writer spent three fresh
conversations - 128 model calls - on four failing tests of its sprint, never returned its answer, and the whole run
failed, with its files on disk. A fix or build stage in that state is recorded as blocked and the run goes on; the
suite's writer now is too: its answer is built from the suite's files as they are, a blocker says it gave none and
where it stopped, and the review, dry run and lock rules judge the files. With no suite file at all, it fails as before.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.acceptance import by_sprint, suite
from app.acceptance.criteria import Criterion
from app.graph import acceptance_nodes as nodes
from app.stacks import contract, pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
PROJECT = "items"
CRITERIA = [Criterion("AC-1", "An item can be added", "brief"), Criterion("AC-2", "An item can be renamed", "brief")]
LAST_WORDS = "AC-2 still fails on the rename route; reading the handler again"
STAGE = "acceptance_author_0"


class _NeverAnswers:
    """The writer's agent loop at its edge: replies in prose, however it is asked."""

    def invoke(self, request, config=None):  # noqa: ARG002
        return {"messages": [SimpleNamespace(type="ai", content=LAST_WORDS)]}


def _workspace(root: Path, files: dict[str, str]) -> Path:
    contract.write(root, pack_named("python-http-api"), PROJECT, "Items")
    folder = root / PROJECT / "acceptance"
    folder.mkdir(parents=True, exist_ok=True)
    suite.save_criteria(root, CRITERIA)
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8")
    return root


def _out_of_retries(root: Path, monkeypatch) -> dict:
    from app.graph.workflow import _run_gated_agent

    monkeypatch.setenv("WORKFLOW_MAX_STRUCTURED_RETRIES", "0")
    return _run_gated_agent(
        {"stage": "acceptance_author", "repository": SimpleNamespace(root_path=str(root))},
        {"configurable": {"thread_id": "thread-outer"}},
        stage_name=STAGE, agent=_NeverAnswers(), initial_request={"messages": []},
        output_key="__acceptance_author__", next_stage="acceptance_review",
    )


def test_the_answer_is_built_from_the_suite_on_disk_with_a_blocker_saying_so(tmp_path, monkeypatch):
    root = _workspace(tmp_path, {"test_items.py": "def test_ac1_added():\n    assert True\n"})

    update = _out_of_retries(root, monkeypatch)

    answer = update["__acceptance_author__"]
    assert update["stage"] == "acceptance_review"
    assert answer.changed_files == [f"{PROJECT}/acceptance/test_items.py"]
    (blocker,) = answer.blockers
    assert "no structured response" in blocker and LAST_WORDS in blocker
    assert not BANNED.search(blocker)


def test_a_later_sprint_s_writer_names_only_its_own_files_and_leaves_the_earlier_ones_as_locked(tmp_path, monkeypatch):
    earlier = "def test_ac1_added():\n    assert True\n"
    root = _workspace(tmp_path, {"test_sprint_1.py": earlier})
    suite.lock(root)
    by_sprint.open_for(root, ["AC-2"], sprint=2, of=2)
    (root / PROJECT / "acceptance" / "test_sprint_2.py").write_text("def test_ac2_renamed():\n    assert False\n")

    answer = _out_of_retries(root, monkeypatch)["__acceptance_author__"]

    assert answer.changed_files == [f"{PROJECT}/acceptance/test_sprint_2.py"]
    assert (root / PROJECT / "acceptance" / "test_sprint_1.py").read_text() == earlier
    assert by_sprint.earlier_files(root) == [f"{PROJECT}/acceptance/test_sprint_1.py"]


def test_with_no_suite_file_on_disk_the_stage_still_fails(tmp_path, monkeypatch):
    from app.graph.workflow import StageGaveNoAnswer

    root = _workspace(tmp_path, {})

    with pytest.raises(StageGaveNoAnswer):
        _out_of_retries(root, monkeypatch)


def test_the_writer_goes_on_to_the_review_and_a_criterion_its_last_words_name_is_not_set_aside(tmp_path, monkeypatch):
    """Its last words are where it stopped, not a ruling that a criterion cannot be tested: one named there, with no
    test yet, stays in the release gate for the review to send back."""
    monkeypatch.setenv("DELIVERY_MODE", "fast")
    monkeypatch.setenv("WORKFLOW_MAX_STRUCTURED_RETRIES", "0")
    monkeypatch.setattr("app.agents.specialists.create_specialist_agent", lambda *a, **k: _NeverAnswers())
    root = _workspace(tmp_path, {"test_items.py": "def test_ac1_added():\n    assert True\n"})
    state = {
        "repository": SimpleNamespace(root_path=str(root)),
        "document": SimpleNamespace(text="# Items\n- An item can be added\n- An item can be renamed\n"),
        "product_intake": SimpleNamespace(product_name="Items", success_measures=[]),
        "stage": "acceptance_author",
    }
    ctx = nodes.Context(model=None, judgement_model=None, checkpointer=None, repo_root=None)

    update = nodes.acceptance_author(state, {"configurable": {"thread_id": "t"}}, ctx)

    assert update["stage"] == "acceptance_review" and update["acceptance_round"] == 1
    assert "AC-2" not in suite.deferred(root)
