"""A suite that ran no test because the product never started is the product's defect, not the suite's.

One run's fix rewired the page; the build it served failed, the web server
never started, and the zero tests that ran were read as a suite collecting
nothing - the suite went back to QA, who cannot fix a build.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

from app.acceptance import junit, suite
from app.graph import acceptance_nodes

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
OUTPUT = """[WebServer] vite v7.1.2 building for production...
[WebServer] ✗ Build failed in 332ms
[WebServer] src/main.tsx (3:9): "App" is not exported by "src/App.tsx", imported by "src/main.tsx".
[WebServer]     at getRollupError (file:///x/node_modules/rollup/dist/es/shared/parseAst.js:337:41)
Error: Process from config.webServer was not able to start. Exit code: 1"""


def test_the_build_error_is_recorded_and_the_empty_run_is_not_called_vacuous(tmp_path):
    problem = suite.the_product_did_not_start(OUTPUT)
    assert problem.startswith(suite.PRODUCT_DID_NOT_START)
    assert '"App" is not exported by "src/App.tsx"' in problem
    assert not BANNED.search(problem.split("Its output:")[0])

    result = suite.AcceptanceResult(ran=True, exit_code=1, command="npm run test:acceptance",
                                    report=junit.Report(found=True), output=OUTPUT, problem=problem)
    assert suite.vacuous_green(tmp_path, result) == []
    plain = suite.AcceptanceResult(ran=True, exit_code=1, command="x", report=junit.Report(found=True), output="0 tests")
    assert suite.vacuous_green(tmp_path, plain) != []


def test_an_ordinary_failing_run_is_not_a_product_that_never_started():
    assert suite.the_product_did_not_start("1 failed\n  locator.fill: Timeout 3000ms exceeded.") == ""


def test_the_round_raises_one_defect_owned_by_the_page_and_no_symptoms(monkeypatch, tmp_path):
    saved = {"ran": True, "problem": suite.the_product_did_not_start(OUTPUT), "runtime_problems": []}
    monkeypatch.setattr(acceptance_nodes, "_failing_due", lambda state: ([{"id": "AC-1", "text": "Users register", "tests": []},
                                                                          {"id": "AC-2", "text": "Tasks are listed", "tests": []}], "npm run test:acceptance"))
    monkeypatch.setattr(suite, "last_result", lambda root: saved)
    monkeypatch.setattr(acceptance_nodes, "_root", lambda state: str(tmp_path))
    monkeypatch.setattr(acceptance_nodes, "_stack", lambda state: SimpleNamespace(product_kind="fullstack"))

    defects = acceptance_nodes.failing_due_defects({}, [])

    assert len(defects) == 1 and defects[0].severity == "blocking"
    assert "does not start" in defects[0].description and defects[0].owner == "ui_ux"
