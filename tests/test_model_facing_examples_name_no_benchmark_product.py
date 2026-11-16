"""The examples the models are shown name no product the harness is measured on (LR.45).

Found in the launch review: the layout prompt's examples were `task-manager/` and `todo-app/`, the contract's were
`GET /api/notes` and `notes add milk`, and the model diagnosis probed `tasks-api/app.py` - the benchmarks' own
products, which bias names and structure toward them and inflate their scores.
"""
from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "app"
BENCHMARK_NOUNS = re.compile(r"task-manager|todo-app|task-dashboard|tasks-api|/api/notes|notes add milk|notes service")
FILES = ("agents/project_layout.py", "agents/principal_architect.py", "graph/workflow.py", "models/deep_diagnosis.py")


def test_the_examples_shown_to_models_name_no_benchmark_product():
    found = {name: BENCHMARK_NOUNS.findall((SRC / name).read_text(encoding="utf-8")) for name in FILES}
    assert {name: hits for name, hits in found.items() if hits} == {}
