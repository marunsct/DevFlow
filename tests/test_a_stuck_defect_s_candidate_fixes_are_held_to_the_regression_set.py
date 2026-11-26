"""A stuck defect's candidate fixes are sized to the server's idle slots, each asked with its own seed, and the one kept
is the first that passes both its own tests and the regression set (plan PF.2, LF.1556, `CANDIDATE_FIXES_WHEN_STUCK`).

Measured before it: the fix rate at a third attempt of one cause was 11%, and after a failed fix the candidate kept
was the first whose own tests passed - measured against the whole suite only after, and reverted when it broke a test
that passed before, the other candidates already thrown away.

The product is a captured Go notes service (`tests/captured/projects/go-notes-api`); its stored suite's test names
are the ones measured. The model server and the sandbox that runs the suite are stood in for.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from app import ci
from app.graph import candidate_fixes_when_stuck, kept_fix_candidates
from app.models import CompatibleChatOpenAI

PROJECTS = Path(__file__).parent / "captured" / "projects"
SERVER = "go-notes-api/server.go"
#: The captured file, whose create handler refuses a title of only spaces.
FIXED = (PROJECTS / SERVER).read_text()
CHECK = 'if strings.TrimSpace(req.Title) == "" {'
#: The product as the defect found it: a title of only spaces is accepted.
BROKEN = FIXED.replace(CHECK, 'if req.Title == "" {')
#: A candidate whose own tests pass and that refuses every title, so a note can no longer be created.
REFUSES_ALL = FIXED.replace(CHECK, "if true {")
#: The stored suite's tests: the defect's own and one the candidate that refuses every title breaks.
OWN = "api.spec.js › [AC-13] POST /notes rejects whitespace-only title"
CREATES = "api.spec.js › [AC-1][AC-7][AC-8] POST /notes creates a note and returns 201"
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
#: The seed each request carried, in the order sent.
SEEDS: list[int | None] = []


class TheModelServer(CompatibleChatOpenAI):
    """The self-hosted model server: each seed samples its own rewrite; one with no seed is the first sample."""

    def invoke(self, messages, *args, **kwargs):  # type: ignore[override]
        SEEDS.append(kwargs.get("seed"))
        text = {21: FIXED}.get(kwargs.get("seed"), REFUSES_ALL)
        return AIMessage(content=f"```go\n{text}```")


def _the_file(root: Path) -> str:
    return (root / SERVER).read_text()


def _measured(root: Path):
    """The whole suite on the workspace as it is: the defect's own test and the create test."""
    def take(where, label, **kwargs):
        text = _the_file(root)
        return ci.Snapshot(label=label, acceptance={
            OWN: "passed" if CHECK in text or "if true {" in text else "failed",
            CREATES: "failed" if "if true {" in text else "passed"}, acceptance_ran=True)
    return take


def _a_stuck_workspace(tmp_path: Path) -> Path:
    shutil.copytree(PROJECTS / "go-notes-api", tmp_path / "go-notes-api")
    (tmp_path / SERVER).write_text(BROKEN)
    (tmp_path / ".project-directory").write_text("go-notes-api")
    ci.commit(tmp_path, "as the defect found it")
    ci.save(tmp_path, ci.Snapshot(label="latest", acceptance={OWN: "failed", CREATES: "passed"}, acceptance_ran=True))
    return tmp_path


@pytest.fixture(autouse=True)
def _arranged(monkeypatch, tmp_path):
    SEEDS.clear()
    monkeypatch.setenv("CANDIDATE_FIXES_WHEN_STUCK", "on")
    monkeypatch.setenv("KEPT_FIX_CANDIDATES", "on")
    monkeypatch.setenv("MODEL_CALL_GATE_DIR", str(tmp_path / "gate"))


def _fixed_when_stuck(tmp_path: Path, failed: int = 2):
    from workflow_nodes import a_defect, a_fix_stage

    root = _a_stuck_workspace(tmp_path)
    model = TheModelServer(model="local", base_url="http://127.0.0.1:9/v1", api_key="k", max_retries=0)
    stuck = a_defect("[AC-13] POST /notes accepts a title of only spaces", fix_attempts=failed,
                     affected_files=[SERVER])
    return a_fix_stage(root, [stuck], patches={
        "app.graph.workflow._the_run_approves_its_own_writes": lambda run_id: True,
        "app.graph.workflow._fast_delivery": lambda: False,
        "app.graph.workflow.concurrent_requests": lambda: 4,
        "app.graph.workflow._the_defect_s_tests_pass": lambda where, defect: CHECK in _the_file(root)
        or "if true {" in _the_file(root),
        "app.graph.localisation.localised": lambda *args, **kwargs: [SERVER],
        "app.graph.rewritten_fixes.what_failed": lambda *args, **kwargs: "Expected: 422\nReceived: 201",
        "app.graph.bounded_fixes.the_candidate_model": lambda *args: model,
        "app.ci.take": _measured(root),
    })


def test_a_stuck_defect_keeps_the_candidate_that_also_holds_the_regression_set(tmp_path):
    _, asked = _fixed_when_stuck(tmp_path)

    assert _the_file(tmp_path) == FIXED, "the candidate that broke the create test was kept"
    assert asked["gated"] == [], "a fixer was started although a candidate held"


def test_each_candidate_is_asked_with_its_own_seed_as_many_as_the_idle_slots_hold(tmp_path):
    _fixed_when_stuck(tmp_path)

    assert len(SEEDS) == 3 and len(set(SEEDS)) == 3 and None not in SEEDS


def test_a_candidate_that_passed_its_own_tests_and_broke_others_is_kept_for_the_next_attempt(tmp_path):
    _fixed_when_stuck(tmp_path)

    store = json.loads((tmp_path / kept_fix_candidates.STORE).read_text())
    kept = [patch for mine in store.values() for candidate in mine["candidates"] for patch in candidate["files"].values()]

    assert any("+\t\tif true {" in patch for patch in kept)


def test_a_defect_that_failed_once_is_not_stuck_and_no_slot_is_measured(monkeypatch):
    monkeypatch.setattr(candidate_fixes_when_stuck, "idle_slots", lambda: 4)

    assert candidate_fixes_when_stuck.width(1, [SERVER]) == 0
    assert candidate_fixes_when_stuck.width(2, [SERVER]) == 3


def test_fewer_than_two_candidates_in_the_idle_slots_asks_as_before(monkeypatch):
    assert candidate_fixes_when_stuck.width(2, [SERVER, "go-notes-api/store/store.go"], idle=3) == 0
    monkeypatch.setenv("CANDIDATE_FIXES_WHEN_STUCK", "off")
    assert candidate_fixes_when_stuck.width(5, [SERVER], idle=4) == 0


def test_a_hosted_model_is_sent_no_seed():
    assert candidate_fixes_when_stuck.seed_for(object(), 3) == {}


def test_the_record_s_words_avoid_the_product_words():
    assert not BANNED.search(candidate_fixes_when_stuck.SAID)
