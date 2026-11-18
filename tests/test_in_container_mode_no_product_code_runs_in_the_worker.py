"""In container mode the harness's own runs of product code go through a command's own container, never the worker.

Found in the deep review of 2026-11-18 (item E1a): the start probe ran the project's `start.sh` with `subprocess.Popen`
in the worker, and the pack's route listing (which imports the product's application) beside it; the suite's dry run
ran the model-written specs with the worker's `node`; and the TypeScript syntax check loaded the project's own
`node_modules/typescript` into a worker process on every write. The worker holds the run's secrets and the route to the
Docker proxy, and none of the four asked the execution mode. Now, in container mode, the first three run through the
sandbox (one `docker run` each) and the check loads only the worker's own compiler; in-container mode is unchanged
(its own tests set it).
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from app.acceptance import spec_dry_run, start_probe
from app.analysis import typescript_parse
from app.stacks import contract, pack_named

_REAL_WHICH = shutil.which


class _Done:
    def __init__(self, stdout: str = "", returncode: int = 0) -> None:
        self.stdout, self.stderr, self.returncode = stdout, "", returncode


class _Processes:
    """Every process the worker starts: a `docker` one is answered by `answer(argv)`, any other is refused."""

    def __init__(self, answer=lambda argv: _Done()) -> None:
        self.started: list[list[str]] = []
        self._answer = answer

    def run(self, argv, *args, **kwargs):
        self.started.append([str(part) for part in argv])
        if Path(str(argv[0])).name == "docker":
            return self._answer([str(part) for part in argv])
        raise OSError("a worker process was started")

    def popen(self, argv, *args, **kwargs):
        self.started.append([str(part) for part in argv])
        raise OSError("a worker process was started")

    def outside_a_container(self) -> list[list[str]]:
        return [argv for argv in self.started if Path(argv[0]).name != "docker"]

    def containers(self) -> list[list[str]]:
        return [argv for argv in self.started if Path(argv[0]).name == "docker" and argv[1:2] == ["run"]]


@pytest.fixture
def processes(monkeypatch):
    def install(answer=lambda argv: _Done()) -> _Processes:
        spy = _Processes(answer)
        monkeypatch.setenv("SANDBOX_EXECUTION_MODE", "container")
        monkeypatch.setenv("ALLOW_COMMAND_EXECUTION", "true")
        monkeypatch.setattr("shutil.which", lambda name, *a, **k: "/usr/bin/docker" if name == "docker" else _REAL_WHICH(name, *a, **k))
        monkeypatch.setattr("subprocess.run", spy.run)
        monkeypatch.setattr("subprocess.Popen", spy.popen)
        return spy
    return install


def _working_directory(docker_argv: list[str]) -> str:
    return docker_argv[docker_argv.index("-w") + 1]


def _a_service(tmp_path: Path) -> Path:
    pack = pack_named("node-hono-native-api")
    contract.write(tmp_path, pack, "notes", "Notes")
    project = tmp_path / "notes"
    project.mkdir()
    (project / "playwright.config.js").write_text(pack.render("notes", "Notes", None)["playwright.config.js"])
    (project / "start.sh").write_text('#!/bin/sh\nexec node server.cjs\n')
    return tmp_path


def test_the_start_probe_starts_the_product_in_its_own_container(tmp_path, monkeypatch, processes):
    monkeypatch.setenv("START_PROBE", "on")
    spy = processes(lambda argv: _Done(json.dumps({"answered": 503, "output": "Listening on 4100"})))

    text = start_probe.what_the_start_shows(_a_service(tmp_path))

    assert spy.outside_a_container() == []
    assert len(spy.containers()) == 1
    assert _working_directory(spy.containers()[0]) == "/workspace/notes"
    assert "`GET /health` answered 503" in text and "Listening on 4100" in text
    assert not (tmp_path / ".harness" / "start_probe.cjs").exists()


def test_the_routes_a_product_serves_are_listed_in_its_own_container(tmp_path, monkeypatch, processes):
    monkeypatch.setenv("START_PROBE", "on")
    answers = iter([_Done(json.dumps({"answered": 404, "output": ""})), _Done("GET /health/health\nPOST /notes\n")])
    spy = processes(lambda argv: next(answers))

    text = start_probe.what_the_start_shows(_a_service(tmp_path))

    assert spy.outside_a_container() == []
    assert len(spy.containers()) == 2
    assert "`GET /health/health`" in text and "`POST /notes`" in text


def test_the_suite_s_dry_run_runs_its_specs_in_their_own_container(tmp_path, monkeypatch, processes):
    monkeypatch.setenv("SPEC_DRY_RUN", "on")
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    suite_folder = tmp_path / "notes" / "acceptance"
    suite_folder.mkdir(parents=True)
    (suite_folder / "a.spec.js").write_text(
        "import { test, expect } from '@playwright/test';\n"
        "test('[AC-1] runs in its own container', async () => { expect(neverDefinedHere).toBe(1); });\n")

    def the_container_writes_its_report(argv: list[str]) -> _Done:
        place = tmp_path / os.path.relpath(_working_directory(argv), "/workspace")
        (place / "report.json").write_text(json.dumps({"files": 1, "tests": 1, "inconclusive": [], "findings": [
            {"file": "a.spec.js", "line": 2, "test": "[AC-1] runs in its own container",
             "error": "ReferenceError: neverDefinedHere is not defined"}]}))
        return _Done()

    spy = processes(the_container_writes_its_report)

    found = spec_dry_run.findings(tmp_path)

    assert spy.outside_a_container() == []
    assert len(spy.containers()) == 1
    assert len(found) == 1 and "neverDefinedHere is not defined" in found[0]
    assert not list((tmp_path / ".harness").glob("spec-dry-run/*"))


@pytest.mark.skipif(_REAL_WHICH("node") is None, reason="no Node here")
def test_a_project_s_own_typescript_package_is_never_loaded_in_the_worker(tmp_path, monkeypatch):
    monkeypatch.setenv("SANDBOX_EXECUTION_MODE", "container")
    marker = tmp_path / "loaded"
    own = tmp_path / "proj" / "node_modules" / "typescript" / "lib"
    own.mkdir(parents=True)
    (own / "typescript.js").write_text(f"require('fs').writeFileSync({json.dumps(str(marker))}, 'x');\n")
    (own.parent / "package.json").write_text('{"name": "typescript", "main": "lib/typescript.js"}')
    source = tmp_path / "proj" / "src" / "a.ts"
    source.parent.mkdir()

    typescript_parse.parse_error(source, "const x: number = ;\n")

    assert not marker.exists()
