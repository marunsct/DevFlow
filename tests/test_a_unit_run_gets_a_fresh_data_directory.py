"""A test run of a product that keeps data gets a fresh data directory, as the acceptance configuration already does.

Measured on one run: unit tests posting megabyte bodies to the product's default data directory on every round grew
its data file to 205 MB, the service parsed all of it per request, and the worker container was killed at its 8 GiB
limit mid-stage; the run sat "running" for 14 minutes.
"""
from __future__ import annotations

from pathlib import Path

from app.stacks import contract, pack_named
from app.tools import sandbox


def test_the_service_packs_name_their_data_directory_variable():
    assert pack_named("node-hono-native-api").data_dir_env == "DATA_DIR"
    assert pack_named("node-http-api").data_dir_env == "DATA_DIR"
    assert pack_named("browser-javascript").data_dir_env == ""


def test_a_test_run_gets_a_fresh_directory_under_test_results_and_nothing_else_does(tmp_path):
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    given = sandbox._a_fresh_data_directory(str(tmp_path), "test")
    assert set(given) == {"DATA_DIR"}
    fresh = Path(given["DATA_DIR"])
    assert fresh.is_dir() and fresh.parent == tmp_path / "notes" / "test-results"
    assert sandbox._a_fresh_data_directory(str(tmp_path), "test") != given, "fresh each run"
    assert sandbox._a_fresh_data_directory(str(tmp_path), "build") == {}


def test_a_product_without_one_and_a_caller_s_own_value_are_left(tmp_path, monkeypatch):
    contract.write(tmp_path, pack_named("browser-javascript"), "web", "Web")
    assert sandbox._a_fresh_data_directory(str(tmp_path), "test") == {}
    import inspect
    source = inspect.getsource(sandbox)
    assert "fresh_data = _a_fresh_data_directory(workspace, category)" in source
    assert "{**fresh_data, **(extra_env or {})}" in source, "the caller's value wins"
