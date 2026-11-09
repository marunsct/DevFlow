"""`loop.sh stack-misses` rebuilds each stored run's stack from its documents (scaffolding plan SF.0c)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "loop" / "stack_misses.py"
spec = importlib.util.spec_from_file_location("stack_misses", SCRIPT)
misses = importlib.util.module_from_spec(spec)
spec.loader.exec_module(misses)

DOC = """# Technology Stack

## Selected Technology Stack
- **Language:** Python
- **Framework:** Falcon
- **Frontend framework:** not stated
- **Testing framework:** pytest
- **Kind of product:** http api

## Rationale
The brief requires Falcon.
<!-- generated -->
"""


def test_the_stack_and_its_rationale_are_read_back(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "technology_stack.md").write_text(DOC)
    stack, rationale = misses.stack_of(tmp_path)
    assert (stack.language, stack.framework, stack.frontend_framework, stack.product_kind) == (
        "Python", "Falcon", "", "http_api")
    assert rationale == "The brief requires Falcon."


def test_only_a_run_whose_decision_was_no_pack_counts(tmp_path):
    (tmp_path / ".harness").mkdir()
    (tmp_path / ".harness" / "decisions.json").write_text(json.dumps(
        [{"point": "stack", "decision": "Python / Falcon - no stack pack fits; the agents set the project up"}]))
    assert misses.went_custom(tmp_path)
    (tmp_path / ".harness" / "decisions.json").write_text(json.dumps([{"point": "stack", "decision": "python-http-api"}]))
    assert not misses.went_custom(tmp_path)
