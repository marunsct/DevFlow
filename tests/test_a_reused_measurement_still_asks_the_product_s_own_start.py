"""A measurement reused because the product did not change still asks the product's own start command.

Measured on one run: the setup wrote the whole product, nothing changed after the lock, and every later measurement -
the release's included - reused the one taken just before the lock, when the own-start check does not run. `start.sh`
ran a bare `python3` without the framework; the product scored 0 of 9 hidden tests with 33 of 33 locked passing.
"""
from __future__ import annotations

import inspect

from app.acceptance import suite


def test_the_reused_path_runs_the_own_start_check_before_it_is_judged():
    source = inspect.getsource(suite.run)
    reused = source[source.index("kept = saved_run_if_unchanged"):]
    reused = reused[:reused.index("return _judged(repo_root, kept, save)")]
    assert "_the_product_s_own_start(repo_root, kept)" in reused


def test_the_check_turns_a_green_reused_result_into_a_product_that_did_not_start(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from app.acceptance import start_output

    monkeypatch.setattr(suite, "is_locked", lambda root: True)
    monkeypatch.setattr(start_output, "how_it_is_used_fails", lambda root: "")
    monkeypatch.setattr(start_output, "what_it_wrote", lambda root: (
        "The harness started the product itself (`sh start.sh`): it stopped by itself with exit code 1. It wrote:\n"
        "ModuleNotFoundError: No module named 'falcon'"))
    kept = SimpleNamespace(problem="", report=SimpleNamespace(tests=[1], failed=0), server_log="")
    suite._the_product_s_own_start(tmp_path, kept)
    assert kept.problem.startswith(suite.PRODUCT_DID_NOT_START)
