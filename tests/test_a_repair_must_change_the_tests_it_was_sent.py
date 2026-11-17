"""A suite repair that leaves a test it was sent for unchanged goes back before the suite is locked again.

Measured on one run: a repair was sent for three tests a dispute ruled wrong; it changed one file and left
`test_restart.py` - two of the three - exactly as it was. The suite was locked again, the ruled-wrong test failed
the rest of the run, and the run was escalated with a product its hidden tests scored 10/10.
"""
from app.acceptance import suite

PY = '''import httpx


def test_ac7_survives_restart(base_url):
    assert False is True


def test_ac21_invalid(base_url):
    assert 422 == 401
'''


def _suite(tmp_path, monkeypatch, text=PY):
    path = tmp_path / "acceptance" / "test_api.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(text)
    monkeypatch.setattr(suite, "suite_files", lambda root: [path])
    return path


def test_a_test_sent_for_repair_and_left_as_it_was_is_named(tmp_path, monkeypatch):
    path = _suite(tmp_path, monkeypatch)
    suite.repairing(tmp_path, ["test_ac7_survives_restart", "test_ac21_invalid"])
    path.write_text(PY.replace("assert 422 == 401", "assert resp.status_code in (400, 401, 422)"))

    [left] = suite.tests_left_unrepaired(tmp_path)
    assert "test_ac7_survives_restart" in left and "test_ac21_invalid" not in left


def test_nothing_is_named_once_each_test_changed_or_after_the_lock(tmp_path, monkeypatch):
    path = _suite(tmp_path, monkeypatch)
    suite.repairing(tmp_path, ["test_ac7_survives_restart"])
    path.write_text(PY.replace("assert False is True", "assert item['done'] is False"))
    assert suite.tests_left_unrepaired(tmp_path) == []
    path.write_text(PY)
    suite.lock(tmp_path)
    assert suite.tests_left_unrepaired(tmp_path) == []


def test_the_review_of_a_repair_sends_back_a_test_it_left_as_it_was(tmp_path):
    from app.acceptance import junit
    from workflow_nodes import an_acceptance_review_measured

    def repaired(root):
        return suite.AcceptanceResult(ran=True, exit_code=1, report=junit.Report(found=True, tests=[
            junit.TestResult(name="acceptance.test_api.test_ac7_survives_restart", outcome="failed", message="assert False"),
            junit.TestResult(name="acceptance.test_api.test_ac21_invalid", outcome="passed")]))

    from app.acceptance.criteria import Criterion
    from app.stacks import contract, pack_named

    contract.write(tmp_path, pack_named("python-http-api"), "notes", "Notes")
    (tmp_path / "notes" / "acceptance").mkdir(parents=True)
    (tmp_path / "notes" / "acceptance" / "test_api.py").write_text(PY)
    suite.save_criteria(tmp_path, [Criterion("AC-7", "Notes survive a restart", "brief"),
                                   Criterion("AC-21", "An invalid note is refused", "brief")])
    suite.repairing(tmp_path, ["test_ac7_survives_restart", "test_ac21_invalid"])
    fixed_one = PY.replace("assert 422 == 401", "assert resp.status_code in (400, 401, 422)")

    update = an_acceptance_review_measured(tmp_path, repaired, pack="python-http-api", files={"test_api.py": fixed_one},
                                  state={"acceptance_round": 2})

    [left] = [problem for problem in update["acceptance_feedback"] if "has not changed" in problem]
    assert update["stage"] == "acceptance_author"
    assert "`test_ac7_survives_restart`" in left and "test_ac21_invalid" not in left


def test_a_test_qa_vouches_for_is_not_named(tmp_path, monkeypatch):
    _suite(tmp_path, monkeypatch)
    suite.repairing(tmp_path, ["test_ac7_survives_restart"])
    state = suite._state(tmp_path)
    state[suite.PRODUCT_AT_FAULT_CLAIMS] = ["PRODUCT_AT_FAULT: test_ac7_survives_restart - the product loses items"]
    suite._save_state(tmp_path, state)
    assert suite.tests_left_unrepaired(tmp_path) == []


def test_the_claims_key_is_the_one_product_at_fault_keeps():
    from app.graph import product_at_fault

    assert product_at_fault._CLAIMS == suite.PRODUCT_AT_FAULT_CLAIMS


def test_a_test_that_now_passes_is_repaired_though_its_code_is_the_same(tmp_path, monkeypatch):
    """Measured on one run: the fault was a shared fixture; the repair fixed the fixture and the three tests it was
    sent for passed - and the suite went back twice saying they had not been changed."""
    from types import SimpleNamespace

    from app.acceptance import junit

    _suite(tmp_path, monkeypatch)
    suite.repairing(tmp_path, ["test_ac7_survives_restart", "test_ac21_invalid"])
    result = SimpleNamespace(report=SimpleNamespace(tests=[
        junit.TestResult(name="acceptance/test_api.py::test_ac7_survives_restart", outcome="passed"),
        junit.TestResult(name="acceptance.test_api.test_ac21_invalid", outcome="failed", message="m"),
    ]))

    [left] = suite.tests_left_unrepaired(tmp_path, result)
    assert "test_ac21_invalid" in left and "test_ac7_survives_restart" not in left
