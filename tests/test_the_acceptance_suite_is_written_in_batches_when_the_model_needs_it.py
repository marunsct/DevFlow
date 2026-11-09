"""The acceptance suite, written a batch of criteria at a time for a model that finds the whole too much (WB.2).

Measured on one run: 14 replies of about 17,000 tokens for one suite, 65 minutes, where earlier runs
used 1,000-2,000 tokens a reply. A criterion is the unit; coverage says which are written.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.acceptance import suite
from app.graph import acceptance_batches as batches
from app.graph import acceptance_nodes as nodes

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
BRIEF = "# Brief\n## Features\n- Add a note\n## Acceptance Criteria\n" + "".join(f"- Criterion number {n} holds\n" for n in range(1, 11))
CONFIG = {"configurable": {"thread_id": "t"}}
CTX = nodes.Context(model=None, judgement_model=None, checkpointer=None, repo_root=None)


def _state(root: Path) -> dict[str, Any]:
    (root / ".project-directory").write_text("notes\n")
    (root / "notes").mkdir(exist_ok=True)
    return {
        "repository": SimpleNamespace(root_path=str(root)),
        "document": SimpleNamespace(text=BRIEF),
        "product_intake": SimpleNamespace(product_name="Notes", success_measures=[]),
        "stack_selection": SimpleNamespace(technology_stack=SimpleNamespace(product_kind="browser_app")),
    }


def _ids_asked(request: dict) -> list[str]:
    text = request["messages"][-1]["content"]
    section = text.split("--- Acceptance criteria ---")[1].split("--- This suite is written")[0].split("--- How to write")[0]
    return re.findall(r"AC-\d+", section)


class _Author:
    """A stand-in for the agent loop: writes one spec file per batch covering the ids it was asked for."""

    def __init__(self, root: Path, *, forget: tuple[str, ...] = (), blockers: dict[str, list[str]] | None = None):
        self.root, self.forget, self.blockers = root, forget, blockers or {}
        self.asked: list[tuple[str, list[str], str]] = []

    def __call__(self, state, config, *, stage_name, agent, initial_request, output_key, next_stage):
        ids = _ids_asked(initial_request)
        self.asked.append((stage_name, ids, initial_request["messages"][-1]["content"]))
        target = self.root / "notes" / "acceptance" / f"{stage_name}.spec.js"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("".join(f"test('[{i}] proves it', async () => {{}});\n" for i in ids if i not in self.forget))
        return {output_key: SimpleNamespace(blockers=self.blockers.get(stage_name, [])), "stage": next_stage}


@pytest.fixture
def author(tmp_path, monkeypatch):
    fake = _Author(tmp_path)
    monkeypatch.setattr("app.graph.workflow._run_gated_agent", fake)
    monkeypatch.setattr("app.agents.specialists.create_specialist_agent", lambda *a, **k: object())
    monkeypatch.setenv("BATCH_ACCEPTANCE_AUTHOR", "on")
    monkeypatch.setattr(batches, "batch_size", lambda model="": 4)
    return fake


@pytest.mark.parametrize("count", range(0, 61))
@pytest.mark.parametrize("size", [None, 3, 4, 8])
def test_the_batches_are_a_partition_in_order_and_even(count, size):
    items = [f"AC-{n}" for n in range(count)]
    out = batches.groups(items, size)
    assert [i for group in out for i in group] == items
    if len(out) > 1:
        assert all(1 <= len(group) <= size for group in out)
        assert max(map(len, out)) - min(map(len, out)) <= 1
    else:
        assert out == [items]


def test_a_strong_or_unmeasured_model_gets_one_batch_and_so_does_a_small_suite(monkeypatch):
    monkeypatch.setenv("BATCH_ACCEPTANCE_AUTHOR", "on")
    items = list(range(20))
    monkeypatch.setattr(batches, "batch_size", lambda model="": None)
    assert batches.plan(items) == [items]
    monkeypatch.setattr(batches, "batch_size", lambda model="": 8)
    assert batches.plan(list(range(5))) == [list(range(5))]
    assert len(batches.plan(items)) == 3


def test_with_the_switch_off_the_plan_is_made_and_not_followed(monkeypatch):
    monkeypatch.setenv("BATCH_ACCEPTANCE_AUTHOR", "off")
    monkeypatch.setattr(batches, "batch_size", lambda model="": 4)
    items = list(range(10))
    assert batches.plan(items) == [items]


def test_the_suite_is_written_in_parts_each_asked_only_its_criteria(tmp_path, author):
    update = nodes.acceptance_author(_state(tmp_path), CONFIG, CTX)

    assert [name for name, _, _ in author.asked] == ["acceptance_author_0_g0", "acceptance_author_0_g1", "acceptance_author_0_g2"]
    asked = [ids for _, ids, _ in author.asked]
    assert asked == [["AC-1", "AC-2", "AC-3", "AC-4"], ["AC-5", "AC-6", "AC-7", "AC-8"], ["AC-9", "AC-10", "AC-11"]]
    assert "part 1 of 3" in author.asked[0][2] and "part 2 of 3" in author.asked[1][2]
    assert "acceptance_author_0_g0.spec.js" in author.asked[1][2]
    assert update["stage"] == "acceptance_review" and update["acceptance_round"] == 1
    assert set(suite.coverage(tmp_path)) == {f"AC-{n}" for n in range(1, 12)}


def test_blockers_from_every_part_are_kept(tmp_path, monkeypatch, author):
    author.blockers = {"acceptance_author_0_g1": ["AC-6: needs a person to judge it"]}
    author.forget = ("AC-6",)

    nodes.acceptance_author(_state(tmp_path), CONFIG, CTX)

    assert suite.deferred(tmp_path) == {"AC-6": "needs a person to judge it"}
    assert not [name for name, _, _ in author.asked if name.endswith("fill")]


def test_a_criterion_left_without_a_test_is_asked_for_once_more_alone(tmp_path, author):
    author.forget = ("AC-9",)

    nodes.acceptance_author(_state(tmp_path), CONFIG, CTX)

    name, ids, text = author.asked[-1]
    assert name == "acceptance_author_0_fill" and ids == ["AC-9"]
    assert "part 4 of 4" in text and len(author.asked) == 4


def test_a_stage_resumed_goes_on_at_the_first_part_not_done(tmp_path, author):
    state = _state(tmp_path)
    suite.save_criteria(tmp_path, nodes.number(BRIEF))
    first = tmp_path / "notes" / "acceptance" / "earlier.spec.js"
    first.parent.mkdir(parents=True, exist_ok=True)
    first.write_text("".join(f"test('[AC-{n}] ok', async () => {{}});\n" for n in (1, 2, 3, 4)))

    nodes.acceptance_author(state, CONFIG, CTX)

    assert [name for name, _, _ in author.asked] == ["acceptance_author_0_g1", "acceptance_author_0_g2"]


def test_a_repair_with_feedback_is_the_whole_suite_in_one_as_before(tmp_path, author):
    state = _state(tmp_path)
    state["acceptance_feedback"] = ["a test checks nothing"]

    nodes.acceptance_author(state, CONFIG, CTX)

    assert [name for name, _, _ in author.asked] == ["acceptance_author_0"]
    assert len(author.asked[0][1]) == 11


def test_with_the_switch_off_the_request_is_the_one_it_always_was(tmp_path, author, monkeypatch):
    monkeypatch.setenv("BATCH_ACCEPTANCE_AUTHOR", "off")

    nodes.acceptance_author(_state(tmp_path), CONFIG, CTX)

    assert [name for name, _, _ in author.asked] == ["acceptance_author_0"]
    assert "This suite is written in" not in author.asked[0][2]


def test_the_notes_use_none_of_the_banned_words():
    group = [SimpleNamespace(id="AC-1"), SimpleNamespace(id="AC-2")]
    for index in (0, 1, 3):
        assert not BANNED.search(batches.note(index, 4, group, ["a.spec.js", "b.spec.js"]))
