"""A delivered run carries the owner's rating, 1-5 and a line, into its KPI row and the bench report (plan EV.1).

Hidden tests score whether a product works, and only on benchmarks that have
them; nothing recorded whether the owner found it any good.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from app.server.runner import RunRecord

ROOT = Path(__file__).resolve().parents[1]


def _script(path: str):
    spec = importlib.util.spec_from_file_location(Path(path).stem + "_ev1", ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed(run_store, run_id: str, status: str) -> None:
    run_store.save(RunRecord(run_id=run_id, thread_id=f"t-{run_id}", document_names=[], document_paths=[],
                             status=status, owner="testuser", tenant_id="default"))


def test_a_delivered_run_is_rated_and_rated_again(client, run_store, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    _seed(run_store, "run-rated", "completed")

    assert client.get("/api/runs/run-rated/rating").json() is None
    client.put("/api/runs/run-rated/rating", json={"score": 2, "note": "works,  looks rough"})
    again = client.put("/api/runs/run-rated/rating", json={"score": 4, "note": "fine after all"}).json()

    assert again["score"] == 4 and again["rated_by"] == "testuser"
    assert client.get("/api/runs/run-rated/rating").json()["note"] == "fine after all"
    assert json.loads((tmp_path / "ratings" / "run-rated.json").read_text())["score"] == 4


def test_only_a_delivered_run_is_rated_and_only_1_to_5(client, run_store, tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    _seed(run_store, "run-live", "running")
    _seed(run_store, "run-done", "completed")

    assert client.put("/api/runs/run-live/rating", json={"score": 3}).status_code == 409
    assert client.put("/api/runs/run-done/rating", json={"score": 6}).status_code == 422
    assert client.put("/api/runs/run-done/rating", json={"score": 0}).status_code == 422


def test_the_kpi_row_and_the_bench_report_carry_it(tmp_path, capsys):
    (tmp_path / "ratings").mkdir()
    (tmp_path / "ratings" / "run-a.json").write_text(json.dumps({"score": 4, "note": "clean,\nfast"}))
    kpi = _script("scripts/loop/kpi.py")

    assert kpi.owner_rating("run-a", str(tmp_path)) == {"owner_rating": 4, "owner_note": "clean, fast"}
    assert kpi.owner_rating("run-b", str(tmp_path)) == {"owner_rating": "", "owner_note": ""}

    bench, kpis = tmp_path / "bench", tmp_path / "kpi"
    bench.mkdir(), kpis.mkdir()
    for run, score, rating in (("run-a", 1.0, 4), ("run-b", 0.5, 2), ("run-c", 0.9, None)):
        (bench / f"{run}.json").write_text(json.dumps({"benchmark": "tasks-api", "score": score, "harness": {"status": "completed"}}))
        (kpis / f"{run}.json").write_text(json.dumps({"run": run, "owner_rating": rating if rating else ""}))

    _script("scripts/bench/report.py").main(bench, kpis)

    line = next(line for line in capsys.readouterr().out.splitlines() if line.startswith("tasks-api"))
    assert line.rstrip().endswith("3.0 (2)")


def test_the_delivered_run_s_page_offers_the_rating():
    page = (ROOT / "langchain-ui" / "src" / "pages" / "RunDashboard.tsx").read_text()

    assert page.count("{run?.status === 'completed' && <OwnerRating runId={runId!} />}") == 2
