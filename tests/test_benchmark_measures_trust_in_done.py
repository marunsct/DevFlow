"""The benchmark tooling measures how far the harness's own "done" can be trusted.

A pass rate hides the number that matters: runs the harness finished whose
product fails tests it never saw. One run's locked suite passed 8 of 9 while
its product scored 2 of 10 on the hidden tests. `score.py` now records the
harness's verdict beside the hidden score, `report.py` totals false
acceptances, and `mutate.py` measures whether the locked suite notices the
product being broken.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "scripts" / "bench"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"bench_{name}", ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


score = _load("score")
report = _load("report")
mutate = _load("mutate")


def test_the_harness_verdict_is_read_from_the_locked_suite(tmp_path) -> None:
    product = tmp_path / "app"
    product.mkdir()
    (tmp_path / ".harness").mkdir()
    (tmp_path / ".harness" / "acceptance-result.json").write_text(json.dumps({
        "passed": 8, "failed": 1,
        "criteria": {"AC-1": {"status": "passed"}, "AC-2": {"status": "deferred"}},
    }))

    verdict = score.harness_verdict(product, "completed")

    assert verdict == {
        "status": "completed", "locked_passed": 8, "locked_failed": 1,
        "criteria_passed": 1, "criteria_deferred": 1, "criteria": 2,
    }
    assert score.harness_verdict(tmp_path / "missing")["status"] == "unknown"


def test_a_finished_run_that_fails_hidden_tests_is_a_false_acceptance() -> None:
    results = [
        {"benchmark": "b", "score": 0.2, "harness": {"status": "completed"}, "false_acceptance": True},
        {"benchmark": "b", "score": 1.0, "harness": {"status": "completed"}, "false_acceptance": False},
        {"benchmark": "b", "score": 0.5, "harness": {"status": "failed"}, "false_acceptance": False},
        {"benchmark": "b", "score": 0.7},
    ]

    row = report.summarise(results)["b"]

    assert row["scored"] == 4 and row["finished"] == 2 and row["perfect"] == 1
    assert row["false_acceptances"] == 1 and row["false_acceptance_rate"] == 0.5
    assert row["unknown"] == 1 and row["mean_score"] == 0.6


def test_mutation_sites_skip_comments_strings_and_imports(tmp_path) -> None:
    source = tmp_path / "main.js"
    source.write_text(
        "import { a } from './a.js';\n"
        "// if (x === y) never mutated\n"
        "const label = 'a === b';\n"
        "if (count >= 1 && done === true) { go(); }\n"
    )

    found = mutate.sites([source], tmp_path)
    originals = {(s["line"], s["original"]) for s in found}

    assert all(line == 4 for line, _ in originals)
    assert {"===", ">=", "&&", "true"} <= {o for _, o in originals}


def test_tests_configuration_and_kept_files_are_not_the_product(tmp_path) -> None:
    for relative in ("src/main.js", "src/main.test.js", "tests/a.spec.js", "playwright.config.js",
                     "playwright.setup.mjs", "node_modules/x/index.js", "scripts/serve.mjs", "app.py"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x = 1\n")

    files = mutate.source_files(tmp_path, {"playwright.setup.mjs", "scripts/serve.mjs"})

    assert [f.relative_to(tmp_path).as_posix() for f in files] == ["app.py", "src/main.js"]


def test_a_change_is_made_where_it_was_found_and_undone_exactly(tmp_path) -> None:
    source = tmp_path / "main.py"
    source.write_text("def f(a, b):\n    return a == b and a > 0\n")
    site = next(s for s in mutate.sites([source], tmp_path) if s["original"] == "==")

    original = mutate.apply(tmp_path, site)

    assert source.read_text() == "def f(a, b):\n    return a != b and a > 0\n"
    source.write_text(original)
    assert source.read_text() == "def f(a, b):\n    return a == b and a > 0\n"


def test_changes_are_spread_over_every_file() -> None:
    candidates = [{"file": f"f{i // 10}", "n": i} for i in range(40)]
    picked = mutate.spread(candidates, 4)
    assert [c["file"] for c in picked] == ["f0", "f1", "f2", "f3"]
    assert mutate.spread(candidates[:3], 4) == candidates[:3]
