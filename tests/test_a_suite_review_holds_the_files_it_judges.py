"""The QA lead's review of the suite is handed the suite's files in its memory, numbered (LF.1286).

Measured on one medium run (15 suite files): each review of the suite read its files about four times each (41 reads
of 10 files with 3 summaries in one review, 48 of 13 in another). The request showed the first 24,000 characters of
the suite and said the rest was in the project memory, but the memory held the plans first and named the suite's
files as not included; the reads went into the conversation, a summary dropped them, and the review read them again.
A suite whose files today's request and memory already show is reviewed exactly as before.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from app.acceptance import junit, requests, suite
from app.acceptance.criteria import number
from app.agents import project_memory
from app.agents.review_files import held_section
from app.graph import acceptance_nodes as nodes

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
BRIEF = "# Brief\n## Features\n- Add a note\n- Delete a note\n- Notes persist between page refreshes\n"
HELD = "Held whole in the project memory for this review"
CONFIG = {"configurable": {"thread_id": "t"}}
CTX = nodes.Context(model=None, judgement_model=None, checkpointer=None, repo_root=None)


def _settings(monkeypatch, window: int) -> None:
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", str(window))
    monkeypatch.setenv("PROJECT_MEMORY", "on")
    monkeypatch.setenv("CANONICAL_MEMORY", "on")


def _a_suite(root: Path, files: int, size: int, specification: int) -> list[str]:
    (root / ".project-directory").write_text("notes\n")
    (root / "notes").mkdir(exist_ok=True)
    suite.save_criteria(root, number(BRIEF))
    names = []
    for n in range(files):
        name = f"notes/acceptance/part{n:02}.spec.js"
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        body = "".join(f"test('[AC-{k}] case {n}', async () => {{}});\n" for k in (1, 2, 3))
        (root / name).write_text(f"// PART_{n:02}\n" + body + "// what this part checks\n" * (size // 24))
        names.append(name)
    (root / "docs").mkdir(exist_ok=True)
    sections = "".join(f"## Section {k}\n" + "The product keeps its records.\n" * 30
                       for k in range(specification // 960))
    (root / "docs" / "technical_specification.md").write_text("# Specification\n" + sections)
    return names


def _the_review_s_opening(monkeypatch, root: Path) -> tuple[str, str]:
    seen: list = []

    def gated(state, config, *, stage_name, agent, initial_request, output_key, next_stage):
        seen.append((stage_name, initial_request["messages"][-1]["content"]))
        return {output_key: SimpleNamespace(approved=True, findings=[]), "stage": next_stage}

    monkeypatch.setattr("app.graph.workflow._run_gated_agent", gated)
    monkeypatch.setattr("app.agents.acceptance_reviewer.create_acceptance_reviewer_agent", lambda *a, **k: object())
    failing = [name for _, name in suite.declared_tests(root)]
    monkeypatch.setattr(suite, "run", lambda r: suite.AcceptanceResult(
        ran=True, exit_code=1, command="npm run test:acceptance",
        report=junit.Report(found=True, tests=[junit.TestResult(name=n, outcome="failed", message="no")
                                               for n in failing])))
    state = {"repository": SimpleNamespace(root_path=str(root)), "document": SimpleNamespace(text=BRIEF),
             "product_intake": SimpleNamespace(product_name="Notes", success_measures=[]),
             "stack_selection": SimpleNamespace(technology_stack=SimpleNamespace(product_kind="browser_app")),
             "acceptance_round": 1}
    nodes.acceptance_review(state, CONFIG, CTX)
    ((stage, opening),) = seen
    return stage, opening


def test_a_suite_review_past_its_room_holds_the_suite_numbered(tmp_path, monkeypatch):
    _settings(monkeypatch, 65_536)
    names = _a_suite(tmp_path, 10, 3_000, specification=58_000)

    stage, opening = _the_review_s_opening(monkeypatch, tmp_path)
    memory, held = project_memory.render_for_a_stage(tmp_path, None, opening, stage)

    assert HELD in opening
    assert set(names) <= set(held)
    documents = memory.index("=== docs/technical_specification.md (outline")
    assert documents < memory.index("=== notes/acceptance/part00.spec.js"), \
        "the documents as digests, then the files held whole (LF.1288: what changes least first)"
    assert "     1\t// PART_00" in memory, "numbered, so a finding cites a line without a read"
    assert opening.count("// PART_00") == 0, "a held file is not repeated in the request"
    assert f"### notes/acceptance/part00.spec.js\n{requests.HELD_IN_THE_MEMORY}" in opening


def test_what_a_suite_review_is_told_of_its_held_files_uses_none_of_the_banned_words():
    assert not BANNED.search(requests.HELD_IN_THE_MEMORY)
    assert not BANNED.search(held_section(["notes/acceptance/part00.spec.js"], "acceptance_review_1"))


def test_a_suite_whose_files_fit_is_reviewed_as_before(tmp_path, monkeypatch):
    """Guard: a small suite's review request and memory carry nothing of this."""
    _settings(monkeypatch, 65_536)
    names = _a_suite(tmp_path, 2, 200, specification=3_000)

    stage, opening = _the_review_s_opening(monkeypatch, tmp_path)
    memory, _ = project_memory.render_for_a_stage(tmp_path, None, opening, stage)

    assert "Held whole in the project memory" not in opening and "(numbered lines" not in memory
    assert all(f"### {name}\n{(tmp_path / name).read_text()}" in opening for name in names)
