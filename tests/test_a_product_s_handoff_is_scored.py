"""`loop.sh score` scores whether a stranger could take the product over, from its files alone (harness review HR2.PR.10)."""
from __future__ import annotations

import importlib.util
from pathlib import Path


def _score():
    path = Path(__file__).resolve().parents[1] / "scripts" / "bench" / "score.py"
    spec = importlib.util.spec_from_file_location("bench_score_handoff", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _a_product(root: Path, readme: bool = True) -> Path:
    product = root / "notes"
    (product / "src").mkdir(parents=True)
    (product / "src" / "app.py").write_text("# Serves the notes.\nPORT = 8000\n")
    (product / "start.sh").write_text('exec python -m src.app --port "${PORT:-8000}"\n')
    (product / ".github" / "workflows").mkdir(parents=True)
    (product / ".github" / "workflows" / "ci.yml").write_text("on: push\n")
    if readme:
        (product / "README.md").write_text("# Notes\n\nRun it:\n\n```\n./start.sh\n```\n\nSet `PORT` and `DATA_DIR`. "
                                           "Run the tests with `pytest`.\n")
    return product


def test_a_product_with_everything_a_stranger_needs_scores_one(tmp_path) -> None:
    result = _score().handoff(_a_product(tmp_path))
    assert result["handoff_score"] == 1.0, result


def test_a_product_without_a_readme_scores_less(tmp_path) -> None:
    result = _score().handoff(_a_product(tmp_path, readme=False))
    assert result["handoff"]["readme"] is False
    assert result["handoff_score"] < 1.0


def test_shipped_data_and_thinking_aloud_are_found(tmp_path) -> None:
    product = _a_product(tmp_path)
    (product / "notes.db").write_text("")
    (product / "src" / "store.py").write_text("# Actually, the spec says 404 here.\n")
    result = _score().handoff(product)
    assert result["handoff"]["no_shipped_data"] is False
    assert result["handoff"]["no_thinking_aloud_in_comments"] is False


def test_the_ledger_takes_the_handoff_score(tmp_path) -> None:
    import json

    path = Path(__file__).resolve().parents[1] / "scripts" / "loop" / "kpi_ledger.py"
    spec = importlib.util.spec_from_file_location("loop_kpi_ledger_handoff", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (tmp_path / "run-x.json").write_text(json.dumps({"score": 1.0, "handoff_score": 0.75}))
    assert module.with_the_scores({"run": "run-x"}, tmp_path)["handoff_score"] == 0.75
    assert "handoff_score" in module.WORSE_WHEN_LOWER


def test_a_start_that_runs_a_program_reading_its_port_counts(tmp_path) -> None:
    """One pack's start runs `node src/main.ts`, and the program reads PORT itself: that start does read its port."""
    product = _a_product(tmp_path)
    (product / "start.sh").write_text("#!/bin/sh\nexec node src/main.ts\n")
    (product / "src" / "main.ts").write_text("const port = Number(process.env.PORT ?? 3000);\n")
    assert _score().handoff(product)["handoff"]["start_reads_its_port"] is True
    (product / "src" / "main.ts").write_text("const port = 3000;\n")
    (product / "src" / "app.py").write_text("x = 1\n")
    assert _score().handoff(product)["handoff"]["start_reads_its_port"] is False
