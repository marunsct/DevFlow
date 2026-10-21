"""Real model output the readers took is kept and replayed: a reader change cannot silently alter an earlier outcome (plan RC).

Twelve-plus audit fixes were a reader misreading real output, each fixed against
the one sample that failed. The corpus holds every input with the result it had.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.observability import reader_corpus

ROOT = Path(__file__).resolve().parent.parent

RECORDS = [
    {"kind": "model_response", "stage": "principal_architect", "tool_calls": [{"name": "TechnicalSpecification", "args": {
        "interface_contract": ["AC-3 GET /api/notes -> 200", 'AC-1 page /login form textbox "Email"', "prose about it"],
        "file_plan": ["- `app/main.py` - the service", "app/store.py: the store"],
    }}]},
    {"kind": "model_response", "stage": "drafting",
     "text": "Here it is:\n```python\nx = 1  # /app/data/workspaces/default/workspace-run-x/app/main.py\n```"},
    {"kind": "model_request", "stage": "defect_fix_1_0", "tools": ["read_file", "edit_artifact"]},
    {"kind": "model_response", "stage": "defect_fix_1_0", "tool_calls": [],
     "text": '<tool_call>{"name": "read_file", "arguments": {"file_path": "app/main.py"}}</tool_call> key sk-abcdefgh12345'},
]


def test_a_run_s_reader_inputs_are_kept_with_their_results_and_redacted(tmp_path):
    added = reader_corpus.harvest(RECORDS, tmp_path)

    assert added == {"contract_line": 3, "file_plan": 1, "drafted_reply": 1, "text_tool_call": 1}
    lines = [json.loads(p.read_text()) for p in (tmp_path / "contract_line").glob("*.json")]
    by_input = {s["input"]: s["result"] for s in lines}
    assert by_input["prose about it"]["unread"] == ["prose about it"]
    assert by_input['AC-1 page /login form textbox "Email"']["checks"][0]["role"] == "textbox"
    stored = " ".join(p.read_text() for p in tmp_path.glob("*/*.json"))
    assert "/app/data/workspaces/" not in stored and "sk-abcdefgh" not in stored
    assert reader_corpus.harvest(RECORDS, tmp_path) == {k: 0 for k in reader_corpus.KINDS}


def test_a_reader_whose_result_changed_is_named_and_accepted_only_on_purpose(tmp_path):
    reader_corpus.harvest(RECORDS, tmp_path)
    sample = next((tmp_path / "file_plan").glob("*.json"))
    data = json.loads(sample.read_text())
    sample.write_text(json.dumps({**data, "result": ["something else"]}))

    assert reader_corpus.replay(tmp_path) == [f"file_plan/{sample.stem}"]
    assert reader_corpus.replay(tmp_path, accept=True) == [f"file_plan/{sample.stem}"]
    assert reader_corpus.replay(tmp_path) == []
    assert reader_corpus.sizes(tmp_path)["file_plan"] == 1


def test_the_corpus_the_runs_left_replays_unchanged():
    # The real corpus, harvested after each run (`loop.sh corpus harvest`); absent
    # on a fresh checkout. A failure names the samples a reader change altered:
    # look at each, then `loop.sh corpus accept` if the new reading is the right one.
    corpus = ROOT / "data" / "corpus"
    if not any(corpus.glob("*/*.json")):
        pytest.skip("no corpus harvested on this host yet")
    assert reader_corpus.replay(corpus) == []


def test_the_loop_harvests_after_each_run():
    script = (ROOT / "scripts" / "loop" / "loop.sh").read_text()
    assert '"$0" corpus harvest "$run"' in script and "corpus.py" in script
