"""`loop.sh effects` shows how reads were decided while reading was withheld, and how writes at the call budget went.

The tool review counted these by hand from 26 transcripts (TR.2: 85 reads refused with the read tool withheld, 51 of
them for a file the request no longer held; TR.6: 18 last writes refused at the call budget). With LF.1517 and LF.1519
built, an audit must see them fire from the run's own records: each decision is recorded as it is made, and the report
counts reads refused by class against reads run, and writes refused at the budget against writes run on a last call.
The stage is the captured fixer of `tests/captured/fixer-reads-withheld-after-two-summaries.json`.
"""
from __future__ import annotations

import runpy
from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import HumanMessage, ToolMessage

from app.agents import project_memory, stage_memory
from app.agents.settled_answer import build_settled_answer_middleware
from app.observability import transcript
from tests.test_a_withheld_read_is_decided_per_file import CAPTURED, HELD, Answer, _message, _Request
from tests.test_a_withheld_tool_notice_is_one_true_list import _after_the_refused_reads, _calls

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "loop" / "effects.py"
RUN = "run-deadbeef"


def _report() -> str:
    effects = runpy.run_path(str(SCRIPT))["effects"]
    return "\n".join(effects(transcript.read_transcript(RUN), ""))


def _through_both(memory, guard, name: str, args: dict) -> str:
    call = SimpleNamespace(tool_call={"name": name, "id": "c1", "args": args})

    def tool(request):
        return ToolMessage(content="done", tool_call_id="c1")

    return str(memory.wrap_tool_call(call, lambda request: guard.wrap_tool_call(request, tool)).content)


def _a_fixer(tmp_path, monkeypatch, calls_left: int | None):
    """The fixer's memory and guard after its captured conversation; with `calls_left`, the budget leaves that many."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PROJECT_MEMORY", "on")
    monkeypatch.setenv("STABLE_TOOLS", "on")
    monkeypatch.setenv("FIRST_REREAD_ANSWERED", "off")
    monkeypatch.setenv("FIX_STAGE_CALL_CAP", "off")
    (tmp_path / "repo" / "tasks-api" / "tasks_api").mkdir(parents=True)
    for path in HELD:
        (tmp_path / "repo" / path).write_text(f'"""{Path(path).stem}"""\n')
    memory = project_memory.build_project_memory_middleware(str(tmp_path / "repo"))
    memory.wrap_model_call(_Request(messages=[HumanMessage(content="Fix the failing unit tests")], model=None),
                           lambda request: None)
    if calls_left is None:
        messages = [HumanMessage(content="Fix the failing unit tests"), *(_message(m) for m in CAPTURED["conversation"])]
        limit = 40
    else:
        messages = _after_the_refused_reads()
        limit = _calls(messages) + calls_left
    guard = build_settled_answer_middleware(Answer, "defect_fix_2_1", limit)
    guard.wrap_model_call(_Request(messages=messages, model=None, model_settings={},
                                   tools=[SimpleNamespace(name=name) for name in CAPTURED["offered"]]),
                          lambda request: None)
    return memory, guard


def test_reads_decided_file_by_file_are_counted_by_class_against_reads_run(tmp_path, monkeypatch):
    with stage_memory.remembering("a-fixer-thread"), transcript.asked_for("defect_fix_2_1", RUN):
        memory, guard = _a_fixer(tmp_path, monkeypatch, calls_left=None)
        for path in ("tasks-api/tests/test_models.py", HELD[0], "tasks-api/tasks_api/auth.py"):
            _through_both(memory, guard, "read_file", {"file_path": path})
    stage_memory.forget_everything()

    assert ("   3  LF.1517 reads while reading was withheld: 1 ran, 2 refused (held whole 1, still in the "
            "conversation 1, document quoted whole 0, withheld whole by another rule 0, already read this stage 0)"
            ) in _report()


def test_a_read_withheld_whole_and_a_write_on_a_last_call_are_counted(tmp_path, monkeypatch):
    with stage_memory.remembering("a-fixer-thread"), transcript.asked_for("defect_fix_2_1", RUN):
        memory, guard = _a_fixer(tmp_path, monkeypatch, calls_left=2)
        _through_both(memory, guard, "read_file", {"file_path": "tasks-api/tests/test_models.py"})
        ran = _through_both(memory, guard, "write_artifact", {"relative_path": HELD[2], "content": "x = 1\n"})
    stage_memory.forget_everything()

    report = _report()
    assert ran == "done"
    assert "withheld whole by another rule 1," in report
    assert "   1  LF.1519 writes on the calls the budget keeps for the answer: 1 run on a last call, 0 refused" in report


def test_a_write_refused_at_the_call_budget_is_counted(tmp_path, monkeypatch):
    with stage_memory.remembering("a-fixer-thread"), transcript.asked_for("defect_fix_2_1", RUN):
        memory, guard = _a_fixer(tmp_path, monkeypatch, calls_left=0)
        refused = _through_both(memory, guard, "edit_artifact", {"relative_path": HELD[2], "find": "a", "replace": "b"})
    stage_memory.forget_everything()

    assert refused.startswith("Refusing")
    assert ("   1  LF.1519 writes on the calls the budget keeps for the answer: 0 run on a last call, 1 refused at the "
            "call budget") in _report()


def test_a_run_with_neither_says_not_reached(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    report = _report()

    assert "LF.1517 reads while reading was withheld: not reached" in report
    assert "LF.1519 writes on the calls the budget keeps for the answer: not reached" in report
