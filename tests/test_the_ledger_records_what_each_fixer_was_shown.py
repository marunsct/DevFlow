"""Each fix attempt's ledger entry says what its fixer was shown: a fingerprint, its size and its sections.

Deep review F9: the ledger recorded a defect's one-line description and outcome, not the request each fixer was
given, so "why did the second try succeed" could not be answered from data.
"""
from __future__ import annotations

from types import SimpleNamespace

import the_fix_stage

from app.observability import defect_ledger


def test_what_a_fixer_was_shown_is_fingerprinted_and_summarised(monkeypatch):
    recorded = []
    monkeypatch.setattr("app.observability.transcript.record", lambda *a, **k: recorded.append(k))
    monkeypatch.setattr("app.observability.transcript._run_id_from_config", lambda: "run-x")
    text = "Fix it.\n--- Related failures owned by your role ---\n- one\n--- The specification for the fix ---\nGET /x\n"

    defect_ledger.shown("defect_fix_1_0", SimpleNamespace(description="[AC-5] delete"), text, round_=1, index=0)
    again = dict(recorded[-1])
    defect_ledger.shown("defect_fix_2_0", SimpleNamespace(description="[AC-5] delete"), text + "more\n", round_=2, index=0)

    assert again["event"] == "shown" and len(text) and str(len(text)) in again["detail"]
    assert "Related failures owned by your role" in again["detail"] and "The specification for the fix" in again["detail"]
    assert again["detail"].split()[1] != recorded[-1]["detail"].split()[1], "a different request, a different fingerprint"


def test_the_fix_request_is_recorded_as_it_is_sent(tmp_path):
    """The entry is the request exactly as the fixer is given it, under the fixer's own stage."""
    _, seen = the_fix_stage.run(tmp_path, the_fix_stage.a_state(tmp_path, test_round=3))

    [sent] = seen.requests
    assert seen.shown == [("defect_fix_3_0", sent)]
    assert sent.startswith(the_fix_stage.BASE_REQUEST)


def test_it_is_recorded_once_a_fixer_not_on_every_resume_of_its_stage(tmp_path):
    """Measured on the run after it shipped: a stage that pauses for each gated tool call is built again on every
    resume, and the entry was written every 6 to 10 seconds for one fixer."""
    resumed = the_fix_stage.a_state(tmp_path, pending_inner_thread_id="inner-1", fix_base_commit="base")

    _, seen = the_fix_stage.run(tmp_path, resumed)

    assert len(seen.requests) == 1, "the resumed fixer is still given its request"
    assert seen.shown == [], "but it is not recorded again"
