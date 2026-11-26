"""A one-shot rewrite fix is aimed at the handler the code graph names when the defect points at no product file.

Measured on a Go notes service: its fixers used the rewrite path, which takes the files a defect names and those its
failure text mentions. A failing acceptance test mentions only its own test file and a route, so the handler was
found only when some other text happened to name it, and the graph's route-to-handler links (KG.4) never reached
these fixers - no localisation was recorded in the run (LF.1528).
"""
from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

from app.graph.rewritten_fixes import files_to_fix

CAPTURED = Path(__file__).parent / "captured"
#: The stored result of the Go product's run: the create route answered 404.
GO_FAILURE = ("api.spec.js:29:1 › [AC-1][AC-7][AC-8] POST /notes creates a note and returns 201 ─────────────────\n\n"
              "    Error: expect(received).toBe(expected) // Object.is equality\n\n    Expected: 201\n    Received: 404\n\n"
              "      36 |   });\n      37 |\n    > 38 |   expect(response.status()).toBe(201);\n"
              "         |                             ^\n"
              "        at /workspace/notes-api/acceptance/api.spec.js:38:29\n")


def _the_go_service(tmp_path: Path) -> Path:
    shutil.copytree(CAPTURED / "projects" / "go-notes-api", tmp_path / "go-notes-api")
    shutil.copytree(CAPTURED / "project-tests" / "go-notes-api", tmp_path / "go-notes-api", dirs_exist_ok=True)
    (tmp_path / ".project-directory").write_text("go-notes-api")
    return tmp_path


def _a_criterion_defect() -> SimpleNamespace:
    return SimpleNamespace(description="[AC-1] POST /notes creates a note and returns 201: the suite says it does not",
                           affected_files=[])


def test_the_handler_of_the_failing_route_is_the_file_rewritten(tmp_path):
    root = _the_go_service(tmp_path)

    chosen = files_to_fix(_a_criterion_defect(), GO_FAILURE, root, lambda path: True)

    assert "go-notes-api/server.go" in chosen
    assert not any(name.endswith("api.spec.js") for name in chosen)


def test_a_defect_that_names_its_product_file_keeps_it(tmp_path):
    root = _the_go_service(tmp_path)
    defect = _a_criterion_defect()
    defect.affected_files = ["go-notes-api/store/store.go"]

    chosen = files_to_fix(defect, GO_FAILURE, root, lambda path: True)

    assert chosen[0] == "go-notes-api/store/store.go"
