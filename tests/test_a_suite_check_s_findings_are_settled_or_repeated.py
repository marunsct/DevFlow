"""How often each suite check's finding settled - not raised again in a later round - per check (harness review Q1)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "loop" / "suite_check_settling.py"
spec = importlib.util.spec_from_file_location("suite_check_settling", SCRIPT)
settling = importlib.util.module_from_spec(spec)
spec.loader.exec_module(settling)


def _workspace(root: Path, name: str, rows: list[dict]) -> None:
    (root / name / ".harness").mkdir(parents=True)
    (root / name / ".harness" / "check-findings.jsonl").write_text("\n".join(json.dumps(r) for r in rows))


def test_a_finding_raised_again_is_repeated_and_one_not_raised_again_settled(tmp_path):
    _workspace(tmp_path, "workspace-run-a", [
        {"check": "locators_that_pick_one", "fingerprint": "f1", "round": 1},
        {"check": "locators_that_pick_one", "fingerprint": "f1", "round": 2},
        {"check": "vacuous_green", "fingerprint": "f2", "round": 1},
    ])
    found = settling.report(tmp_path)
    assert found["locators_that_pick_one"] == {"findings": 2, "repeated": 1, "settled": 1, "runs": 1}
    assert found["vacuous_green"]["settled"] == 1
