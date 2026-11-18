"""The product itself can be downloaded as one archive, with how to run it (LR.30a).

Found in the launch review: after a run of hours the only download was the handover pack (documents, decisions and
the acceptance suite) or one file at a time; the product could not be taken away.
"""
from __future__ import annotations

import io
import subprocess
import zipfile

from app.sprint import product_archive


def _workspace(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for name, text in {
        "app/server.py": "print('hi')\n", "app/start.sh": "python3 server.py\n", "app/README.md": "# App\n",
        "app/node_modules/x/index.js": "dep", "app/__pycache__/s.pyc": "c", "app/test-results/r.xml": "<r/>",
        ".harness/decisions.json": "{}", ".agent-home/.gitconfig": "", "app/tmp-inline-1a2b3c4d.py": "x",
    }.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return tmp_path


def test_the_archive_holds_the_product_and_its_history_and_nothing_of_the_harness(tmp_path):
    root = _workspace(tmp_path)
    files = product_archive.files_of(root)
    assert {"app/server.py", "app/start.sh", "app/README.md"} <= set(files)
    assert any(name.startswith(".git/") for name in files)
    assert not [name for name in files if "node_modules" in name or "__pycache__" in name or "test-results" in name
                or name.startswith((".harness/", ".agent-home/")) or "tmp-inline-" in name]


def test_the_archive_says_how_to_run_it(tmp_path, monkeypatch):
    root = _workspace(tmp_path)
    monkeypatch.setattr("app.tools.repository.pinned_project_directory", lambda root: "app")
    monkeypatch.setattr("app.stacks.contract.the_pack", lambda root: None)
    archive = zipfile.ZipFile(io.BytesIO(product_archive.build(root, "run-1")))
    names = archive.namelist()
    assert "run-1/app/server.py" in names and "run-1/HOW-TO-RUN.txt" in names
    assert "cd app\nsh start.sh" in archive.read("run-1/HOW-TO-RUN.txt").decode()


def test_the_server_offers_it(client):
    for path in ("/api/runs/run-none/product", "/api/runs/run-none/how-to-run", "/api/runs/run-none/product/summary"):
        answer = client.get(path)
        # The run is unknown, so the route answers for the run - not "Not Found" for a path it does not have.
        assert answer.status_code == 404 and "Run run-none not found" in answer.json().get("detail", ""), path
