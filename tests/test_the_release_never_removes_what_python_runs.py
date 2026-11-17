"""The release never removes a module Python runs by itself, and undoes a removal that broke the product.

Measured on one run: the release removed an untouched `__main__.py` as a template "nothing loads"; `python -m` then
failed 19 of 19 locked tests, and a product that had passed them all shipped failing every hidden test.
"""
from __future__ import annotations

from app.graph import delivery
from app.stacks import scaffold


def test_main_and_init_are_loaded_by_python_itself():
    assert scaffold._the_ways_a_file_is_named("wordstats/__main__.py") == []
    assert scaffold._the_ways_a_file_is_named("wordstats/__init__.py") == []
    assert scaffold._the_ways_a_file_is_named("wordstats/cli.py")


def test_a_removal_that_broke_the_suite_is_put_back_and_measured_again(tmp_path, monkeypatch):
    """Through the release, on a scaffolded product whose untouched template the product does need; the suite run (the
    product's own runner) is stood in for and fails while that file is missing."""
    import json
    from types import SimpleNamespace

    from app.acceptance import junit, suite
    from app.acceptance.criteria import number
    from app.stacks import contract, pack_named

    pack = pack_named("rust-cli")
    for relative, content in pack.render("notes", "Notes").items():
        (tmp_path / "notes" / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "notes" / relative).write_text(content)
    contract.write(tmp_path, pack, "notes", "Notes")
    (tmp_path / ".project-directory").write_text("notes\n")
    removable = scaffold.remove_untouched_templates_nothing_loads(tmp_path)
    assert removable, "the scaffold has a template nothing names"
    scaffold.put_back_templates(tmp_path, removable)
    suite.save_criteria(tmp_path, number("# Brief\n## Features\n- Add a note\n"))
    spec = tmp_path / "notes" / str(contract.read(tmp_path).get("acceptance_dir") or "acceptance") / "notes.spec.js"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("test('[AC-1] adds', async () => {});\n")
    suite.lock(tmp_path)
    (tmp_path / suite.RESULT_FILE).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / suite.RESULT_FILE).write_text(json.dumps({"ran": True, "fingerprint": "another product", "criteria": {
        "AC-1": {"status": "passed", "tests": [{"name": "[AC-1] adds", "outcome": "passed"}]}}}))

    def run(repo, *args, **kwargs):
        whole = all((tmp_path / path).exists() for path in removable)
        return suite.AcceptanceResult(ran=True, command="npm test", report=junit.Report(found=True, tests=[
            junit.TestResult(name="[AC-1] adds", outcome="passed" if whole else "failed", message="")]))

    monkeypatch.setattr(suite, "run", run)
    monkeypatch.setattr("app.graph.workflow._stop_if_cancelled", lambda run_id: None)

    update = delivery.release({"repository": SimpleNamespace(root_path=str(tmp_path)),
                               "product_intake": SimpleNamespace(product_name="Notes")},
                              {"configurable": {"thread_id": "t"}}, None)

    assert all((tmp_path / path).exists() for path in removable), "put back"
    assert not any(delivery.CHANGED_AT_RELEASE in str(gap) for gap in update.get("completion_gaps") or [])
