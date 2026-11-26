"""Past the author's room, the acceptance suite is written a file at a time, not in one reply (PA.4, always on).

Measured on the medium brief (per-agent audit 2026-11-25): the suite writer opened at 1.15-1.28 of its summary trigger
and was asked for every test file of the sprint in one conversation; one visit of 88 calls made no write in 43
minutes. On the small briefs every opening was at most 0.70 of the trigger. The inputs here are the captured medium
specification, the medium brief and its numbered criteria and contract, at the medium run's slot (91,776 tokens) and
the small runs' (182,272).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.acceptance import suite
from app.acceptance.criteria import Criterion
from app.graph import acceptance_nodes as nodes
from app.graph import suite_by_file

HERE = Path(__file__).parent
CAPTURED = HERE / "captured"
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
CONFIG = {"configurable": {"thread_id": "t"}}
CTX = nodes.Context(model=None, judgement_model=None, checkpointer=None, repo_root=None)
MEDIUM_SLOT, SMALL_SLOT = "91776", "182272"


def _medium() -> dict[str, Any]:
    return json.loads((CAPTURED / "interface_contracts_and_criteria.json").read_text(encoding="utf-8"))["medium_fastapi"]


def _state(root: Path) -> dict[str, Any]:
    medium = _medium()
    (root / ".project-directory").write_text("app\n")
    (root / "app").mkdir(exist_ok=True)
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs" / "technical_specification.md").write_text(
        (CAPTURED / "technical-specification-a-medium-brief.md").read_text(encoding="utf-8"), encoding="utf-8")
    suite.save_criteria(root, [Criterion(id=c["id"], text=c["text"], source="brief") for c in medium["criteria"]])
    return {
        "repository": SimpleNamespace(root_path=str(root)),
        "document": SimpleNamespace(text=(HERE / "brief_medium.md").read_text(encoding="utf-8")),
        "product_intake": SimpleNamespace(product_name="Dashboard", success_measures=[]),
        "stack_selection": SimpleNamespace(technology_stack=SimpleNamespace(product_kind="web_service")),
        "technical_specification": SimpleNamespace(interface_contract=list(medium["interface_contract"])),
    }


def _ids_asked(text: str) -> list[str]:
    section = text.split("--- Acceptance criteria ---")[1].split("--- This suite is written")[0].split("--- How to write")[0]
    return re.findall(r"AC-\d+", section)


class _Author:
    """A stand-in for the agent loop: writes one test file per part for the ids it was asked; the first part also
    writes the suite's shared helper."""

    def __init__(self, root: Path):
        self.root = root
        self.asked: list[tuple[str, list[str], str]] = []

    def __call__(self, state, config, *, stage_name, agent, initial_request, output_key, next_stage):
        text = initial_request["messages"][-1]["content"]
        ids = _ids_asked(text)
        self.asked.append((stage_name, ids, text))
        folder = self.root / "app" / "acceptance"
        folder.mkdir(parents=True, exist_ok=True)
        if not (folder / "helpers.py").exists():
            (folder / "helpers.py").write_text("BASE_URL = 'http://127.0.0.1:8000'\n\ndef signed_in(client):\n    return client\n")
        (folder / f"test_{stage_name}.py").write_text(
            "".join(f"def test_{i.replace('-', '_').lower()}_holds():\n    pass\n\n" for i in ids))
        return {output_key: SimpleNamespace(blockers=[]), "stage": next_stage}


@pytest.fixture
def author(tmp_path, monkeypatch):
    fake = _Author(tmp_path)
    monkeypatch.setattr("app.graph.workflow._run_gated_agent", fake)
    monkeypatch.setattr("app.agents.specialists.create_specialist_agent", lambda *a, **k: object())
    monkeypatch.setenv("BATCH_ACCEPTANCE_AUTHOR", "off")
    # Planned as one sprint: the suite is written whole, before the plan.
    monkeypatch.setenv("DELIVERY_MODE", "fast")
    monkeypatch.setattr("app.acceptance.by_sprint.decide", lambda root, fast=False: False)
    return fake


def test_a_suite_past_its_author_s_room_is_written_one_file_a_part(tmp_path, author, monkeypatch) -> None:
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", MEDIUM_SLOT)

    update = nodes.acceptance_author(_state(tmp_path), CONFIG, CTX)

    names = [name for name, _, _ in author.asked]
    assert len(names) == 4 and names[0] == "acceptance_author_0_g0"
    assert [ids for _, ids, _ in author.asked] == [[f"AC-{n}" for n in range(k, k + 4)] for k in (1, 5, 9, 13)]
    assert "in one new test file of their own" in author.asked[0][2]
    assert update["stage"] == "acceptance_review" and update["acceptance_round"] == 1


def test_each_part_holds_the_contract_lines_its_criteria_use_and_the_shared_files_whole(tmp_path, author, monkeypatch) -> None:
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", MEDIUM_SLOT)

    nodes.acceptance_author(_state(tmp_path), CONFIG, CTX)

    first, second = author.asked[0][2], author.asked[1][2]
    assert 'AC-1 page /login textbox "Email"' in first and "AC-6 POST /api/register -> 201" not in first
    assert "AC-6 POST /api/register -> 201" in second and 'AC-1 page /login textbox "Email"' not in second
    assert suite_by_file.SHARED_HEADING in second and "def signed_in(client):" in second


def test_a_suite_that_fits_its_room_is_written_in_one_request_as_before(tmp_path, author, monkeypatch) -> None:
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", SMALL_SLOT)

    nodes.acceptance_author(_state(tmp_path), CONFIG, CTX)

    assert [name for name, _, _ in author.asked] == ["acceptance_author_0"]
    assert len(author.asked[0][1]) == 16 and "This suite is written" not in author.asked[0][2]


def test_a_repair_with_the_review_s_findings_is_one_request_as_before(tmp_path, author, monkeypatch) -> None:
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", MEDIUM_SLOT)
    state = _state(tmp_path)
    state["acceptance_feedback"] = ["AC-3: the search test checks nothing"]

    nodes.acceptance_author(state, CONFIG, CTX)

    assert [name for name, _, _ in author.asked] == ["acceptance_author_0"]


def test_the_effects_report_counts_the_suites_written_a_file_at_a_time(tmp_path, author, monkeypatch) -> None:
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", MEDIUM_SLOT)
    written: list[dict] = []
    monkeypatch.setattr("app.observability.transcript.record",
                        lambda run_id, stage, kind, **fields: written.append({"kind": kind, "stage": stage, **fields}))

    nodes.acceptance_author(_state(tmp_path), CONFIG, CTX)

    assert [r["parts"] for r in written if r["kind"] == suite_by_file.RECORD_KIND] == [4]
    assert "(4 parts)" in suite_by_file.effects_lines(written)[0]


def test_what_each_part_is_told_avoids_the_banned_words(tmp_path) -> None:
    (tmp_path / ".project-directory").write_text("app\n")
    group = [SimpleNamespace(id="AC-1"), SimpleNamespace(id="AC-2")]
    for index in (0, 1, 3):
        text = suite_by_file.note(index, 4, group, ["app/acceptance/test_a.py"], tmp_path)
        assert text and not BANNED.search(text), text
    assert not BANNED.search(suite_by_file.SAID) and not BANNED.search(suite_by_file.SHARED_HEADING)
