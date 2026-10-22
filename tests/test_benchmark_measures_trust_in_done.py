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
        "completion_gaps": [],
    }
    assert score.harness_verdict(tmp_path / "missing")["status"] == "unknown"


def test_a_completed_run_s_gaps_ride_the_bench_export(tmp_path) -> None:
    """The export says what the release knew it did not prove, so a false
    acceptance can be read as 'it finished and said so' or 'it finished and
    claimed verified' (Initiative J.4)."""
    verdict = score.harness_verdict(
        tmp_path / "missing", "completed", ["AC-2 ships deferred, unproven by the suite"]
    )

    assert verdict["completion_gaps"] == ["AC-2 ships deferred, unproven by the suite"]


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
    source.write_bytes(original)
    assert source.read_text() == "def f(a, b):\n    return a == b and a > 0\n"


def test_changes_are_spread_over_every_file() -> None:
    candidates = [{"file": f"f{i // 10}", "n": i} for i in range(40)]
    picked = mutate.spread(candidates, 4)
    assert [c["file"] for c in picked] == ["f0", "f1", "f2", "f3"]
    assert mutate.spread(candidates[:3], 4) == candidates[:3]


def test_a_run_scored_against_another_brief_s_suite_is_not_a_false_acceptance() -> None:
    """Three runs given a shorter brief scored 1, 1 and 5 of 10 on a suite
    written for the benchmark's own brief; the one given that brief scored 10."""
    assert score.brief_pairing("no") == {"brief": "other", "brief_mismatch": True}
    assert score.brief_pairing("yes") == {"brief": "own", "brief_mismatch": False}
    assert score.brief_pairing("") == {"brief": "unknown", "brief_mismatch": False}

    results = [
        {"benchmark": "b", "score": 0.1, "harness": {"status": "completed"}, "false_acceptance": False,
         "brief_mismatch": True},
        {"benchmark": "b", "score": 1.0, "harness": {"status": "completed"}, "false_acceptance": False},
    ]
    row = report.summarise(results)["b"]
    assert row["brief_mismatch"] == 1
    assert row["scored"] == 1 and row["finished"] == 1 and row["mean_score"] == 1.0


def test_the_loop_compares_the_brief_by_content() -> None:
    loop = (Path(__file__).resolve().parents[1] / "scripts" / "loop" / "loop.sh").read_text()
    assert "scripts/bench/brief_match.py" in loop and "benchmarks/$name/brief.md" in loop
    assert '"$gaps" "$own"' in loop


def test_a_deploy_builds_what_was_committed_not_the_working_tree() -> None:
    """Concurrent sessions share one tree; a build of it ships their unverified edits."""
    loop = (Path(__file__).resolve().parents[1] / "scripts" / "loop" / "loop.sh").read_text()
    deploy = loop[loop.index("\ndeploy)"):loop.index("\n  ;;", loop.index("\ndeploy)"))]
    assert 'worktree add -q --detach "$head_tree" "$built"' in deploy
    assert '-f "$head_tree/docker-compose.yml"' in deploy
    assert "docker compose build" not in deploy
    assert 'git -C "$ROOT" show "$built:src/app/$f"' in deploy


def test_a_deploy_waits_for_the_live_stage_to_end() -> None:
    """A resume restarts the running stage's conversation; one fix stage was restarted five times in an hour."""
    loop = (Path(__file__).resolve().parents[1] / "scripts" / "loop" / "loop.sh").read_text()
    deploy = loop[loop.index("\ndeploy)"):loop.index("\n  ;;", loop.index("\ndeploy)"))]
    assert "BOUNDARY_WAIT:-1800" in deploy
    assert deploy.index("last_stage") < deploy.index('touch $gate/hold')


def test_a_run_whose_hidden_tests_never_ran_is_unscored_not_a_false_acceptance(tmp_path, monkeypatch) -> None:
    """A runner whose install was cut off part-way had no pytest; every hidden test 'failed' with no report,
    and a run whose product passed its suite was scored 0/10 as a false acceptance and entered the ledger."""
    (tmp_path / "bench" / "hidden").mkdir(parents=True)
    (tmp_path / "bench" / "bench.json").write_text(json.dumps({"kind": "http_api", "runner": "pytest", "tests": 10}))
    (tmp_path / "product").mkdir()
    monkeypatch.setattr(score, "_python_runner", lambda: Path("/bin/false"))
    monkeypatch.setattr(score, "harness_verdict", lambda product, status, gaps=None: {"status": "completed", "completion_gaps": []})
    result = score.score(tmp_path / "product", tmp_path / "bench", tmp_path / "out.json", "completed")
    assert result["unscored"] is True and result["score"] is None and result["false_acceptance"] is False
    row = report.summarise([result])["bench"]
    assert row["scored"] == 0 and row["false_acceptances"] == 0


def test_a_runner_is_ready_only_when_pytest_imports_not_when_its_python_exists():
    import inspect

    source = inspect.getsource(score._python_runner)
    assert '"import pytest, httpx"' in source
