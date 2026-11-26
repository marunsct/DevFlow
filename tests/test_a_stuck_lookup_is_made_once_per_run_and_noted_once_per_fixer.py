"""A stuck fixer's error is looked up once per run, its note reused, and its ledger record written once per fixer
(LF.1505, LF.1506).

Measured on a live run: one fixer's stage, resumed after each gated tool call, sent the same query
(`sqlite3.ProgrammingError: SQLite objects created in a thread can only ...`) ten times in eleven minutes, and the
ledger had ten `lookup gate` records for that one fixer. The shared lookup store - the queue's Redis, 307 of its 512 MB
used by the queue's own records - was past the share lookups may write to, so the run's once-only record went to the
machine's files, and was then looked for in the store alone, where it never was.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
import the_fix_stage

from app.observability import lookup_notes, transcript
from app.tools import lookup_service, lookup_store, lookups

#: The defect's text as the fixer was given it (captured from the run's transcript).
ACTUAL = (
    "`POST /signup` answered 500 - it said: Internal Server Error.\n\n"
    "What the server printed while the smoke ran:\n"
    "sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in that same thread. The object "
    "was created in thread id 139816733951680 and this is thread id 139816772317312. (File "
    "\"/workspace/tasks-api/tasks_api/database.py\", line 174, in create_account)\n\n"
    "The errors it stated:\n"
    "ERROR: Exception in ASGI application\n")
DESCRIPTION = (
    "The product's foundation does not hold, so the acceptance tests built on it cannot pass. The harness's smoke of it "
    "failed where a fresh account is made: `POST /signup` answered 500 - it said: Internal Server Error. Before it: the "
    "product answers a request.")
#: The query the run sent each time.
QUERY = "sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in that same thread."
ADVICE = "Pass check_same_thread=False to sqlite3.connect, or open one connection per request."
RESUMES = 9


@pytest.fixture
def full_store(monkeypatch, tmp_path):
    """The shared store answers, but is past the share of its memory lookups may write to, as it was on the run."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(lookup_store, "_ROOM", {})
    monkeypatch.setattr(lookup_store, "memory", lambda: {"used": 307 * 2**20, "most": 512 * 2**20,
                                                          "policy": "noeviction"})


@pytest.fixture
def stuck_lookups(monkeypatch, full_store):
    """Stuck lookups on, the sources stubbed at the network's edge; yields the queries sent and the run's gate
    records."""
    monkeypatch.setenv("WEB_LOOKUP_WHEN_STUCK", "on")
    monkeypatch.delenv("LOOKUP_AT_FIRST_SIGHT", raising=False)
    monkeypatch.setattr(transcript, "_run_id_from_config", lambda: "run-resumed")
    monkeypatch.setattr("app.models.model_pin.current_run_id", lambda: "run-resumed")
    monkeypatch.setattr(lookups, "_get", lambda *a, **k: (404, "", {}))
    sent: list[str] = []

    def look_up(error, stack_words="", private_words=(), **_k):
        sent.append(error)
        return {"query": QUERY, "asked": ["stack exchange"], "found": [{
            "source": "Stack Overflow, accepted answer", "title": "SQLite objects created in a thread",
            "date": "2024-03-01", "url": "https://stackoverflow.com/q/48218065", "excerpt": ADVICE}]}

    monkeypatch.setattr(lookups, "look_up", look_up)
    yield SimpleNamespace(sent=sent, records=lambda event: [
        r for r in transcript.read_transcript("run-resumed") if r.get("kind") == "defect" and r.get("event") == event])


def _the_stuck_defect():
    return the_fix_stage.a_defect(DESCRIPTION, actual_behavior=ACTUAL, source="foundation smoke",
                                  attempts=[{"stage": "defect_fix_1_0", "outcome": "left open"}])


def _the_fixer_and_its_resumes(root, defect) -> list[str]:
    """The fixer's stage as it ran: shown once, then built again on each resume after a gated tool call."""
    workspace = root / "workspace"
    (workspace / ".harness").mkdir(parents=True, exist_ok=True)
    _, first = the_fix_stage.run(workspace, the_fix_stage.a_state(workspace, defect))
    requests = list(first.requests)
    for _ in range(RESUMES):
        _, resumed = the_fix_stage.run(workspace, the_fix_stage.a_state(
            workspace, defect, pending_inner_thread_id="inner-1", fix_base_commit="base"))
        requests += resumed.requests
    return requests


def test_a_fixer_resumed_after_each_gated_call_looks_its_error_up_once(tmp_path, stuck_lookups):
    requests = _the_fixer_and_its_resumes(tmp_path, _the_stuck_defect())

    assert len(requests) == 1 + RESUMES
    assert len(stuck_lookups.sent) == 1, "one lookup for the run's one distinct error, not one per resume"
    assert all(ADVICE in request for request in requests), "every resume is shown the note the first lookup found"


def test_a_fixer_resumed_after_each_gated_call_has_one_lookup_gate_record(tmp_path, stuck_lookups):
    _the_fixer_and_its_resumes(tmp_path, _the_stuck_defect())

    assert [r["gate"] for r in stuck_lookups.records(lookup_notes.GATE)] == ["looked up"]
    assert len(stuck_lookups.records(lookup_notes.SHOWN)) == 1
    assert stuck_lookups.records(lookup_notes.SHOWN_AGAIN) == []


def test_a_later_fixer_of_the_error_is_shown_the_note_and_says_so_once(tmp_path, stuck_lookups):
    """Another defect stating the same error, later in the run: not looked up again, recorded as shown again."""
    _the_fixer_and_its_resumes(tmp_path, _the_stuck_defect())
    later = the_fix_stage.a_defect("Signing in answers 500", actual_behavior=ACTUAL, source="test round",
                                   attempts=[{"stage": "defect_fix_1_1", "outcome": "left open"}])

    requests = _the_fixer_and_its_resumes(tmp_path, later)

    assert len(stuck_lookups.sent) == 1 and all(ADVICE in request for request in requests)
    assert len(stuck_lookups.records(lookup_notes.SHOWN_AGAIN)) == 1
    assert len(stuck_lookups.records(lookup_notes.GATE)) == 2


def test_the_run_s_once_only_lookup_is_kept_however_full_the_store_is(tmp_path, full_store, monkeypatch):
    """The run's record lives in its workspace: a worker on another machine, whose files hold none of it, still finds
    it while the store refuses every write."""
    monkeypatch.setattr("app.models.model_pin.current_run_id", lambda: "run-resumed")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    asked: list[str] = []

    def ask():
        asked.append(QUERY)
        return ["\n" + ADVICE, QUERY, "leads"]

    lookup_service.once_per_run("stuck lookup", workspace, QUERY, ask)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "another-machine"))

    found, before = lookup_service.once_per_run("stuck lookup", workspace, QUERY, ask)

    assert asked == [QUERY] and before and ADVICE in found[0]


def test_a_new_run_in_the_same_workspace_looks_its_error_up_afresh(tmp_path, full_store, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    asked: list[str] = []

    def ask():
        asked.append(QUERY)
        return ["\n" + ADVICE, QUERY, "leads"]

    monkeypatch.setattr("app.models.model_pin.current_run_id", lambda: "run-first")
    lookup_service.once_per_run("stuck lookup", workspace, QUERY, ask)
    monkeypatch.setattr("app.models.model_pin.current_run_id", lambda: "run-second")

    lookup_service.once_per_run("stuck lookup", workspace, QUERY, ask)

    assert asked == [QUERY, QUERY]


class _Sources:
    """The lookup sources as the network shows them: Stack Exchange answers the advice; each request recorded."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    def __call__(self, url, headers, body=None):
        self.sent.append(url)
        if "search/advanced" in url:
            return 200, json.dumps({"items": [{"title": "SQLite objects created in a thread",
                                               "link": "https://stackoverflow.com/q/48218065",
                                               "accepted_answer_id": 1, "last_activity_date": 1_700_000_000}]})
        if "/answers/" in url:
            return 200, json.dumps({"items": [{"answer_id": 1, "body": f"<p>{ADVICE}</p>"}]})
        return 200, json.dumps({"items": [], "results": []})


def test_an_answer_kept_while_the_store_is_full_is_read_back_on_the_same_machine(full_store, monkeypatch):
    """Every kept value (answers, registries, pages) went to the files while the store was full, and was looked for in
    the store alone."""
    monkeypatch.setenv("WEB_SEARCH_ENABLED", "false")
    for variable in ("LOOKUP_ORDER", "LOOKUP_DAILY_CAPS", "LOOKUP_RATES", "LOOKUPS_FROZEN"):
        monkeypatch.delenv(variable, raising=False)
    lookups.look_up(QUERY, "Python FastAPI", fetch=_Sources())
    sources = _Sources()

    lookups.look_up(QUERY, "Python FastAPI", fetch=sources)

    assert sources.sent == []


def test_the_probe_says_what_fills_a_store_full_for_lookups(full_store):
    lines = lookup_service.probe_lines()

    [memory] = [line for line in lines if line.startswith("LOOKUPS store memory: ")]
    assert "FULL for lookups" in memory and "is not theirs" in memory and "read back" in memory
