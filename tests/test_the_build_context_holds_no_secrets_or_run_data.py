"""The image's build context holds no secrets, run data or local environments (LR.40).

Found in the launch review: there was no `.dockerignore`, so `.env` and `data/` went into every build's context, and a
virtualenv of 3,628 files was tracked in git.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_secrets_and_run_data_stay_out_of_the_build():
    ignored = (ROOT / ".dockerignore").read_text().splitlines()
    for entry in (".env", ".env.*", "data/", ".langchain/", ".venv/", "**/node_modules/", ".git/"):
        assert entry in ignored, entry
    assert "!.env.example" in ignored


def test_no_local_environment_or_database_is_tracked():
    tracked = subprocess.run(["git", "ls-files", ".langchain", "data"], cwd=ROOT, capture_output=True, text=True).stdout
    assert not [line for line in tracked.splitlines() if line.startswith(".langchain/") or line.endswith(".db")]
