"""A stack no pack covers is set up on the runner layer of a pack of its kind and language (SF.2).

Measured on the custom-stack baselines (Python, Falcon), 2026-11-07: four setup attempts failed on four mechanical
details the agent wrote by hand - smoke-only test commands, report paths outside the project, a command with no report
flag, a bare `python3` beside a project `.venv` - and one shipped a product that started nowhere but the sandbox
(hidden 0 of 9). A Python HTTP pack already holds a proven install, runners, report flags and an acceptance conftest;
only its framework's files differ. The pack names those files and what each must do.
"""
from __future__ import annotations

from app.stacks import pack_named
from app.stacks.custom_setup import runner_layer


def test_the_python_service_pack_names_its_framework_files():
    pack = pack_named("python-http-api")
    framework = dict(pack.framework_files)
    assert {"requirements.txt", "{{package}}/main.py", "start.sh", "tests/test_scaffold_smoke.py"} <= set(framework)
    assert set(framework) <= set(pack.files) | set(pack.smoke_files)
    assert all(len(what.split()) >= 6 for what in framework.values())
    assert "/health" in framework["{{package}}/main.py"] and ".venv/bin/python" in framework["start.sh"]


def test_a_python_service_on_another_framework_gets_that_layer():
    assert runner_layer("http_api", "python") is pack_named("python-http-api")


def test_a_kind_and_language_with_no_layer_gets_none():
    assert runner_layer("http_api", "elixir") is None
    assert runner_layer("", "python") is None
