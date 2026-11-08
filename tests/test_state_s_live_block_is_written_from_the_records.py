"""STATE.md's live and last-runs block is written from the records, not by hand (harness review HR2.O.2).

Hand-kept, its As-of line read 10-29 on 11-08 and its last runs were ten days old.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path


def _module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "loop" / "state_blocks.py"
    spec = importlib.util.spec_from_file_location("loop_state_blocks", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_block_names_the_live_runs_and_the_last_scored_ones(tmp_path) -> None:
    blocks = _module()
    bench = tmp_path / "bench"
    bench.mkdir()
    for n, (family, passed) in enumerate([("web-todo", 10), ("notes-api", 8)]):
        path = bench / f"run-{n}aaaaaaa.json"
        path.write_text(json.dumps({"benchmark": family, "passed": passed, "total": 10, "false_acceptance": passed < 10,
                                    "harness": {"status": "completed"}}))
        os.utime(path, (1000 + n, 1000 + n))
    ledger = tmp_path / "ledger.csv"
    ledger.write_text("run,active_minutes,mixed_versions\nrun-1aaaaaaa,42.5,False\n")

    block = blocks.render(0, "abcdef1234", "abcdef1234", [("run-live", "running", "technical_lead")],
                          blocks.recent_scores(bench, ledger))

    assert block[0] == blocks.START and block[-1] == blocks.END
    assert "abcdef12 committed; abcdef12 deployed." in block[1]
    assert "run-live running at technical_lead" in block[2]
    assert block[3].index("notes-api 8/10") < block[3].index("web-todo 10/10"), "newest first"
    assert "FALSE ACCEPTANCE" in block[3] and "42 active min" in block[3]


def test_the_block_is_replaced_whole_and_the_rest_is_kept(tmp_path) -> None:
    blocks = _module()
    state = tmp_path / "STATE.md"
    state.write_text("# State\nintro\n**As of:** 2026-10-29 stale\n## Live now\nkept\n")
    assert blocks.rewrite(state, [blocks.START, "first", blocks.END])
    assert blocks.rewrite(state, [blocks.START, "second", blocks.END])
    text = state.read_text()
    assert "stale" not in text and "first" not in text and "second" in text
    assert text.count(blocks.START) == 1 and "## Live now\nkept" in text


def test_the_repository_s_state_has_the_block() -> None:
    text = (Path(__file__).resolve().parents[1] / "docs" / "STATE.md").read_text()
    blocks = _module()
    assert blocks.START in text and blocks.END in text
