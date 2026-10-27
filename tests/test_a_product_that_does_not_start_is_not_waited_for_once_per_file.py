"""Once one acceptance file's run shows the product never started, the other files are not run to show it again.

Measured on one run: the product answered `/health` with a 500, and every
write a fixer made was followed by a check of its defect's tests file by file.
Each of the five files waited out the runner's 60-second wait for the server,
so each write cost five minutes, and a fixer made two writes in ten.
"""
from __future__ import annotations

from pathlib import Path

from app.acceptance import per_file

RECORD = {"project": "notes-api", "acceptance_dir": "acceptance", "acceptance_pattern": "*.spec.js",
          "acceptance_test": ["npx", "playwright", "test"]}
NEVER_STARTED = "Error: Timed out waiting 60000ms from config.webServer.\n"


def _workspace(root: Path) -> Path:
    folder = root / "notes-api" / "acceptance"
    folder.mkdir(parents=True)
    for name in ("a.spec.js", "b.spec.js", "c.spec.js"):
        (folder / name).write_text("test('[AC-1] x', async () => {});\n")
    return root


def test_the_files_after_a_start_that_failed_are_not_run(tmp_path: Path):
    root = _workspace(tmp_path)
    ran: list[list[str]] = []

    def run(argv, category, project):
        ran.append(argv)
        return {"returncode": "1", "stdout": NEVER_STARTED}

    runs = per_file.each_file(root, RECORD, run)

    assert len(ran) == 1
    assert [r["file"] for r in runs] == ["notes-api/acceptance/a.spec.js", "notes-api/acceptance/b.spec.js",
                                         "notes-api/acceptance/c.spec.js"]
    assert len({r["outcome"] for r in runs}) == 1 and runs[0]["outcome"] != "finished"
    assert "did not start" in runs[2]["output"]


def test_files_whose_product_started_are_each_run(tmp_path: Path):
    root = _workspace(tmp_path)
    ran: list[list[str]] = []

    def run(argv, category, project):
        ran.append(argv)
        return {"returncode": "1", "stdout": "1 failed"}

    per_file.each_file(root, RECORD, run)

    assert len(ran) == 3
