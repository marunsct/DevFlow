"""A fix stage that used all its model calls is recorded from its writes, not started over twice more (plan item AO).

Measured live: fix stages kept editing to the last call, ignored the warning
that the budget was nearly spent, and were started over on a fresh
conversation twice more - three conversations of forty calls for one defect,
with the first's edits already on disk. The harness holds the receipts of what
was written and lets the measurement after the fix decide. And a criterion the
locked suite measured green after the fix is fixed whether or not the fixer
named a regression test: the suite is its regression test.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from langchain_core.messages import AIMessage, ToolMessage

from app import ci
from app.agents.specialists import SpecialistOutput
from app.graph.workflow import _a_fix_recorded_from_its_writes, _files_the_conversation_wrote, _settle_the_fix
from app.sprint import Defect, RemediationCycle

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _result(*writes, failed=()):
    messages = []
    for number, (tool, path) in enumerate(writes):
        call_id = f"c{number}"
        messages.append(AIMessage(content="", tool_calls=[{"name": tool, "args": {"relative_path": path}, "id": call_id}]))
        ok = path not in failed
        messages.append(ToolMessage(
            content='{"path": "%s", "status": "edited"}' % path if ok else '{"error": "Refusing this write"}',
            tool_call_id=call_id,
        ))
    return {"messages": messages}


def test_the_files_a_conversation_wrote_come_from_its_successful_writes():
    result = _result(("edit_artifact", "app/a.py"), ("write_artifact", "app/b.py"), ("edit_artifact", "app/a.py"),
                     ("edit_artifact", "app/c.py"), failed=("app/c.py",))

    assert _files_the_conversation_wrote(result) == ["app/a.py", "app/b.py"]


def test_a_fix_that_wrote_files_is_recorded_from_them():
    recorded = _a_fix_recorded_from_its_writes("defect_fix_2_8", _result(("edit_artifact", "app/a.py")))

    assert isinstance(recorded, SpecialistOutput)
    assert recorded.changed_files == ["app/a.py"]
    assert not BANNED.search(" ".join(recorded.decisions))


def test_a_stage_that_wrote_nothing_or_is_not_a_fix_is_started_over_as_before():
    assert _a_fix_recorded_from_its_writes("defect_fix_2_8", _result()) is None
    assert _a_fix_recorded_from_its_writes("specialist_backend_0", _result(("edit_artifact", "app/a.py"))) is None


def test_the_no_answer_path_uses_it_only_when_the_budget_stopped_the_stage():
    import inspect

    from app.graph import workflow

    source = inspect.getsource(workflow)
    assert "if structured_response is None and was_stopped_by_the_budget(result):" in source
    assert "_a_fix_recorded_from_its_writes(stage_name, result)" in source


LABEL = "after defect_fix_1_0"


def _settled(tmp_path, description, acceptance):
    ci.save(tmp_path, ci.Snapshot(label=LABEL, acceptance=acceptance, acceptance_ran=bool(acceptance)))
    defect = Defect(
        description=description, severity="major", reproduction_steps="r", expected_behavior="e",
        actual_behavior="a", owner="backend", regression_test_required=True,
    )
    cycle = RemediationCycle(sprint_goal="g", defects=[defect])
    state = {"repository": SimpleNamespace(root_path=str(tmp_path)), "specialist_outputs": {}}
    fix = SpecialistOutput(changed_files=["src/notes.ts"])  # names no regression test
    update, _ = _settle_the_fix(state, cycle, 0, "defect_fix_1_0", fix, measured=LABEL)
    return update["remediation"].defects[0]


def test_a_criterion_measured_green_is_fixed_though_the_fixer_named_no_test(tmp_path):
    defect = _settled(tmp_path, "[AC-3] Lists a new note - the acceptance suite says this does not work yet.",
                      {"tests/ac-3.spec.ts › AC-3 lists a new note": "passed"})

    assert defect.status == "fixed"


def test_a_criterion_measured_red_stays_open(tmp_path):
    defect = _settled(tmp_path, "[AC-3] Lists a new note - the acceptance suite says this does not work yet.",
                      {"tests/ac-3.spec.ts › AC-3 lists a new note": "failed"})

    assert defect.status != "fixed"


def test_a_defect_that_is_no_criterion_still_needs_a_named_test(tmp_path):
    defect = _settled(tmp_path, "The note store loses the last note on save", {})

    assert defect.status != "fixed"
