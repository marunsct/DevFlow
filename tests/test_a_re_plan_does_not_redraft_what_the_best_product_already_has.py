"""A re-plan leaves the files the best product so far already has, when that product passes at least half the suite.

Measured over a day of small-model runs: a re-plan redrafted every planned file and the best-attempt undo had to put
the product back in about half the runs, each after a whole test round on the wreck. Behind `KEEP_THE_BEST_ON_A_REPLAN`.
"""
from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import pytest

from app.acceptance import suite
from app.graph import best_attempt, drafting


def _git(root, *args):
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture()
def product(tmp_path, monkeypatch):
    monkeypatch.setenv("KEEP_THE_BEST_ON_A_REPLAN", "on")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.ts").write_text("export const app = 1;\n")
    (tmp_path / "src" / "store.ts").write_text("export const store = 1;\n")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "best")
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True).stdout.strip()
    (tmp_path / ".harness").mkdir()
    (tmp_path / ".harness" / "best-attempt.json").write_text(json.dumps({"passed": 15, "commit": commit}))
    result = tmp_path / suite.RESULT_FILE
    result.parent.mkdir(parents=True, exist_ok=True)
    result.write_text(json.dumps({"ran": True, "passed": 14, "failed": 5}))
    return tmp_path


def test_files_as_the_best_attempt_had_them_are_kept_on_a_re_plan(product):
    (product / "src" / "store.ts").write_text("export const store = 2;\n")  # changed since the best

    kept = best_attempt.files_the_best_attempt_already_has(
        product, ["src/app.ts", "src/store.ts", "src/new.ts"], replans=1)

    assert kept == {"src/app.ts"}


def test_a_product_as_good_as_its_best_keeps_its_files_as_they_are_now(product):
    """Measured: at 8 of 9 tests the fixers had improved files since the best commit; only one was kept, the rest were
    redrafted, and the product fell to 2 of 10."""
    (product / "src" / "store.ts").write_text("export const store = 2;\n")
    (product / suite.RESULT_FILE).write_text(json.dumps({"ran": True, "passed": 15, "failed": 4}))

    kept = best_attempt.files_the_best_attempt_already_has(
        product, ["src/app.ts", "src/store.ts", "src/new.ts"], replans=1)

    assert kept == {"src/app.ts", "src/store.ts"}


@pytest.mark.parametrize("replans, best, failed", [(0, 15, 5), (1, 0, 5), (1, 4, 15)])
def test_no_re_plan_no_best_or_a_weak_best_redrafts_everything(product, replans, best, failed):
    record = json.loads((product / ".harness" / "best-attempt.json").read_text())
    (product / ".harness" / "best-attempt.json").write_text(json.dumps({**record, "passed": best}))
    (product / suite.RESULT_FILE).write_text(json.dumps({"ran": True, "passed": 4, "failed": failed}))

    assert best_attempt.files_the_best_attempt_already_has(product, ["src/app.ts"], replans=replans) == set()


def test_off_nothing_is_kept(product, monkeypatch):
    monkeypatch.setenv("KEEP_THE_BEST_ON_A_REPLAN", "off")
    assert best_attempt.files_the_best_attempt_already_has(product, ["src/app.ts"], replans=1) == set()


def test_a_kept_file_is_not_drafted_and_its_work_order_counts_as_done(tmp_path, monkeypatch):
    drafted_paths = []
    monkeypatch.setattr(drafting, "_draft_one", lambda model, root, path, *a, **k: drafted_paths.append(path) or "x\n")
    monkeypatch.setattr(drafting, "_promised_but_not_written", lambda task, written, root: [])
    tasks = [SimpleNamespace(files=["src/app.ts"], specialist_role="backend"),
             SimpleNamespace(files=["src/new.ts"], specialist_role="backend")]

    done = drafting.draft_work_orders(tasks, object(), None, str(tmp_path), object(),
                                      write=lambda *a: None, kept={"src/app.ts"})

    assert drafted_paths == ["src/new.ts"]
    assert set(done) == {0, 1}
    assert any("left as the best attempt" in d for d in done[0].decisions)


def test_the_re_plan_s_redraft_asks_which_files_to_keep():
    import inspect

    from app.graph import workflow

    assert "files_the_best_attempt_already_has(" in inspect.getsource(workflow)
    assert "kept=kept" in inspect.getsource(workflow)
