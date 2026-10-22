"""A run's KPIs on its page, and two runs side by side (plan UI-S6).

The KPIs every change is measured against were computed by a loop script
inside the worker and kept in the host's `data/kpi/`, where the run page could
not read them. The computation is in the application now - the script imports
it, so the numbers are the same - and the API answers them from the run's
transcript.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from app.observability import run_kpis, transcript

ROOT = Path(__file__).resolve().parents[1]


def _ledger():
    spec = importlib.util.spec_from_file_location("ledger_ui_s6", ROOT / "scripts" / "loop" / "kpi_ledger.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_script_and_the_application_compute_the_same_kpis():
    spec = importlib.util.spec_from_file_location("kpi_ui_s6", ROOT / "scripts" / "loop" / "kpi.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    assert script.kpis is run_kpis.kpis


def test_the_page_flags_a_kpi_as_the_ledger_does():
    ledger = _ledger()
    assert set(run_kpis.WORSE_WHEN_HIGHER) == set(ledger.WORSE_WHEN_HIGHER)
    assert run_kpis.FLOOR == ledger.FLOOR and run_kpis.FACTOR == ledger.FACTOR
    assert run_kpis.worse("tool_failure_rate", 0.10, 0.20) is True
    assert run_kpis.worse("tool_failure_rate", 0.10, 0.12) is False
    assert run_kpis.worse("tool_failure_rate", 0.001, 0.01) is False  # under the floor
    assert run_kpis.worse("cached_token_share", 0.2, 0.9) is False  # more is better


def test_the_route_answers_a_run_s_kpis_from_its_transcript(client, tmp_path, monkeypatch):
    brief = tmp_path / "brief.md"
    brief.write_text("A product")
    with open(brief, "rb") as handle:
        run_id = client.post("/api/runs", files=[("files", ("brief.md", handle, "text/plain"))]).json()["run_id"]
    records = [
        {"kind": "model_request", "stage": "architect", "at": "2026-10-19T10:00:00+00:00"},
        {"kind": "model_response", "stage": "architect", "at": "2026-10-19T10:00:10+00:00", "usage": {"input_tokens": 100, "output_tokens": 10}},
    ]
    monkeypatch.setattr(transcript, "read_transcript", lambda run, kinds=None: records)

    body = client.get(f"/api/runs/{run_id}/kpis").json()

    assert body["run"] == run_id and body["model_calls"] == 1 and body["input_tokens"] == 100


def test_two_runs_side_by_side_with_the_worse_marked(client, tmp_path, monkeypatch):
    ids = []
    for name in ("one", "two"):
        brief = tmp_path / f"{name}.md"
        brief.write_text("A product")
        with open(brief, "rb") as handle:
            ids.append(client.post("/api/runs", files=[("files", (brief.name, handle, "text/plain"))]).json()["run_id"])
    calm = [{"kind": "tool_call", "stage": "s", "at": "2026-10-19T10:00:00+00:00", "tool": "write_artifact", "call_id": f"c{i}"} for i in range(10)]
    calm += [{"kind": "tool_result", "stage": "s", "at": "2026-10-19T10:00:01+00:00", "tool": "write_artifact", "call_id": f"c{i}", "content": "ok"} for i in range(10)]
    rough = [dict(entry) for entry in calm]
    for entry in rough[10:15]:
        entry["content"] = '{"error": "Refusing to write"}'
    by_run = {ids[0]: calm, ids[1]: rough}
    monkeypatch.setattr(transcript, "read_transcript", lambda run, kinds=None: by_run[run])

    rows = {row["key"]: row for row in client.get(f"/api/runs/compare?a={ids[0]}&b={ids[1]}").json()["rows"]}

    assert rows["tool_failure_rate"]["a"] == 0 and rows["tool_failure_rate"]["b"] == 0.5
    assert rows["tool_failure_rate"]["worse"] is True
    assert rows["tool_calls"]["worse"] is False
