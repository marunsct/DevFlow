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


def test_the_review_of_a_repair_checks_it():
    import inspect

    from app.graph import acceptance_nodes

    assert "tests_left_unrepaired(root)" in inspect.getsource(acceptance_nodes.acceptance_review)


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
