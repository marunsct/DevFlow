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


def test_the_layer_is_written_with_a_declaration_the_harness_can_prove_from(tmp_path):
    import json

    from app.stacks.custom_setup import read_declaration, write_runner_layer

    project = tmp_path / "notes-api"
    project.mkdir()
    pack = pack_named("python-http-api")
    left = write_runner_layer(project, pack, "notes-api", "Notes")

    # The neutral layer is there; none of the framework's own files is.
    assert (project / "pytest.ini").is_file() and (project / "acceptance" / "conftest.py").is_file()
    assert (project / "acceptance" / "test_scaffold_smoke.py").is_file()
    assert not (project / "requirements.txt").exists() and not (project / "start.sh").exists()
    assert not (project / "notes_api" / "main.py").exists()
    # What is left to the agent: each framework file by its filled path, with what it must do.
    assert set(left) == {"requirements.txt", "notes_api/main.py", "start.sh", "tests/test_scaffold_smoke.py"}
    assert "notes_api.main" in left["notes_api/main.py"]
    # The declaration is the pack's own, so nothing the agent writes can get a command, a report or a path wrong.
    declared = json.loads((project / "stack-setup.json").read_text())
    assert declared["unit_test"] == list(pack.commands("notes-api")["unit_test"])
    assert declared["smoke_files"] == ["tests/test_scaffold_smoke.py", "acceptance/test_scaffold_smoke.py"]
    assert "start.sh" in declared["kept_files"]
    for name in left:
        (project / name).parent.mkdir(parents=True, exist_ok=True)
        (project / name).write_text("x")
    assert read_declaration(project)[1] == ""


def _falcon():
    from types import SimpleNamespace

    return SimpleNamespace(language="Python", framework="Falcon", frontend_framework="", testing_framework="pytest",
                           database="SQLite")


def test_the_setup_on_a_layer_writes_it_once_and_names_the_framework_files(tmp_path):
    from app.stacks.custom_setup import layered_setup

    project = tmp_path / "notes-api"
    project.mkdir()
    first = layered_setup(project, _falcon(), "http_api", "notes-api", "Notes", write=True)
    assert first and "start.sh" in first and (project / "stack-setup.json").is_file()
    (project / "stack-setup.json").write_text("{}")
    again = layered_setup(project, _falcon(), "http_api", "notes-api", "Notes", write=False)
    assert again == first and (project / "stack-setup.json").read_text() == "{}"


def test_no_layer_for_a_language_with_none(tmp_path):
    from types import SimpleNamespace

    from app.stacks.custom_setup import layered_setup

    stack = SimpleNamespace(language="Elixir", framework="Phoenix", frontend_framework="", testing_framework="ExUnit",
                            database="")
    assert layered_setup(tmp_path, stack, "http_api", "notes-api", "Notes", write=True) is None


def test_the_request_on_a_layer_asks_only_for_the_framework_files():
    import re

    from app.stacks.custom_setup import build_setup_request

    files = {"start.sh": "starts the service with `.venv/bin/python`", "notes_api/main.py": "the application"}
    text = build_setup_request("notes-api", _falcon(), "http_api", layer_files=files)["messages"][0]["content"]
    assert "`notes-api/start.sh`" in text and "`notes-api/notes_api/main.py`" in text
    assert "Leave those as they are" in text and "stack-setup.json" in text
    assert "Write exactly one unit smoke test" not in text
    body = text[text.index("--- Set up"):]
    assert not re.search(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", body, re.I)
