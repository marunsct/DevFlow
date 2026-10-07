"""Each defect says which check raised it, and the Sprint Record shows it.

One run's round queued nine defects for four bugs - the round's own, the
language service's in two files, code review's - and telling which check
raised each meant reading every description.
"""

from __future__ import annotations

import re

from app.agents.specialists import ReportedDefect, SpecialistOutput, raised_by
from app.sprint import Defect


def _reported(**extra) -> ReportedDefect:
    return ReportedDefect(
        description="x", severity="major", reproduction_steps="r", expected_behavior="e",
        actual_behavior="a", owner="backend", **extra,
    )


def test_a_model_is_never_asked_for_it() -> None:
    schema = SpecialistOutput.model_json_schema()

    assert "source" not in str(schema)


def test_each_check_marks_its_own_and_keeps_another_s() -> None:
    marked = raised_by("language service", [_reported(), _reported(source="code review")])

    assert [d.source for d in marked] == ["language service", "code review"]


def test_the_cycle_keeps_it() -> None:
    defect = Defect(description="x", severity="major", reproduction_steps="r", expected_behavior="e",
                    actual_behavior="a", owner="backend", source="page check")

    assert defect.source == "page check"


def test_the_sprint_record_shows_it_where_the_panel_still_reads_the_owner() -> None:
    from app.agents.sprint_summary import render_sprint_summary

    text = render_sprint_summary(
        sprint_number=1, total_sprints=1, goal="g", planned=["p"],
        attempts=[{"sprint_index": 0, "status": "Completed", "defects": [
            {"status": "fixed", "description": "Missing export", "owner": "backend", "source": "language service"},
        ]}],
    )

    [line] = [line for line in text.splitlines() if line.startswith("- [FIXED]")]
    assert line == "- [FIXED] Missing export - raised by language service (Owner: backend)"
    panel = re.match(r"^- \[(\w+)\] (.+?) \(Owner: (.+?)\)$", line)
    assert panel and panel.group(3) == "backend"


def test_each_event_of_a_defect_goes_to_the_transcript(monkeypatch) -> None:
    """What became of a defect was spread over the worker log, the Sprint
    Record and the fixer's transcript; the ledger puts each event in one place."""
    from app.observability import defect_ledger, transcript

    seen = []
    monkeypatch.setattr(transcript, "_run_id_from_config", lambda: "run-deadbeef")
    monkeypatch.setattr(transcript, "record", lambda run, stage, kind, **fields: seen.append((run, stage, kind, fields)))

    defect_ledger.note("fixed", "defect_fix_1_0", defect=_reported(source="code review"), round_=1, index=0,
                       sprint=2, detail="changed src/a.js")

    [(run, stage, kind, fields)] = seen
    assert (run, stage, kind) == ("run-deadbeef", "defect_fix_1_0", "defect")
    assert fields["event"] == "fixed" and fields["source"] == "code review" and fields["sprint"] == 2
