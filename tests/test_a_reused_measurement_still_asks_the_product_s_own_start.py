"""A measurement reused because the product did not change still asks the product's own start command.

Measured on one run: the setup wrote the whole product, nothing changed after the lock, and every later measurement -
the release's included - reused the one taken just before the lock, when the own-start check does not run. `start.sh`
ran a bare `python3` without the framework; the product scored 0 of 9 hidden tests with 33 of 33 locked passing.
"""
from __future__ import annotations

from app.acceptance import suite


GREEN = ('<testsuites><testsuite name="acceptance" tests="1">'
         '<testcase classname="acceptance.test_api" name="test_ac1_lists"/></testsuite></testsuites>')


def test_the_reused_path_runs_the_own_start_check_before_it_is_judged(tmp_path, monkeypatch):
    from app.acceptance import start_output
    from app.acceptance.criteria import Criterion
    from app.stacks import contract, pack_named
    from app.tools.version_control import initialise_repository

    contract.write(tmp_path, pack_named("python-http-api"), "notes", "Notes")
    (tmp_path / "notes" / "acceptance").mkdir(parents=True)
    (tmp_path / "notes" / "acceptance" / "test_api.py").write_text("def test_ac1_lists(client):\n    assert True\n")
    contract.enforce(tmp_path)  # the harness's own test files, as the setup leaves them
    suite.save_criteria(tmp_path, [Criterion("AC-1", "Notes are listed", "brief")])
    suite.lock(tmp_path)
    initialise_repository(tmp_path)  # what the product is, as git knows it, is how "unchanged" is told
    ran = []

    def the_suite_s_runner(argv, category, where):
        ran.append(argv)
        (tmp_path / where / "test-results").mkdir(exist_ok=True)
        (tmp_path / where / "test-results" / "acceptance.xml").write_text(GREEN)
        return {"returncode": "0"}

    monkeypatch.setenv("MEASURE_ONCE", "on")
    monkeypatch.setattr(start_output, "how_it_is_used_fails", lambda root: "")
    monkeypatch.setattr(start_output, "what_it_wrote", lambda root: "")
    first = suite.run(tmp_path, runner=the_suite_s_runner)
    measured = len(ran)
    monkeypatch.setattr(start_output, "what_it_wrote", lambda root: (
        "The harness started the product itself (`sh start.sh`): it stopped by itself with exit code 1. It wrote:\n"
        "ModuleNotFoundError: No module named 'falcon'"))

    reused = suite.run(tmp_path, runner=the_suite_s_runner)

    assert first.ran and not first.problem and len(ran) == measured, "the second measurement is the first one reused"
    assert reused.problem.startswith(suite.PRODUCT_DID_NOT_START) and "falcon" in reused.problem


def test_the_check_turns_a_green_reused_result_into_a_product_that_did_not_start(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from app.acceptance import start_output

    monkeypatch.setattr(suite, "is_locked", lambda root: True)
    monkeypatch.setenv("MEASURE_ONCE", "on")
    monkeypatch.setattr(start_output, "how_it_is_used_fails", lambda root: "")
    monkeypatch.setattr(start_output, "what_it_wrote", lambda root: (
        "The harness started the product itself (`sh start.sh`): it stopped by itself with exit code 1. It wrote:\n"
        "ModuleNotFoundError: No module named 'falcon'"))
    kept = SimpleNamespace(problem="", report=SimpleNamespace(tests=[1], failed=0), server_log="")
    suite._the_product_s_own_start(tmp_path, kept)
    assert kept.problem.startswith(suite.PRODUCT_DID_NOT_START)
