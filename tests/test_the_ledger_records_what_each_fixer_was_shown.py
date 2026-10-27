"""Each fix attempt's ledger entry says what its fixer was shown: a fingerprint, its size and its sections.

Deep review F9: the ledger recorded a defect's one-line description and outcome, not the request each fixer was
given, so "why did the second try succeed" could not be answered from data.
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace

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


def test_the_fix_request_is_recorded_as_it_is_sent():
    from app.graph import workflow

    source = inspect.getsource(workflow)
    body = source[source.index("def _the_fix_request("):source.index("def _fixed_by_rewriting(")]
    assert "defect_ledger.shown(" in body
