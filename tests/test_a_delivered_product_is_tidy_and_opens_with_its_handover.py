"""A delivered product is tidy and opens with one handover page a person reads.

Deep review 2026-11-18, item F4b: a delivered product's root held installed dependencies, test-runner output and
built binaries; its `docs/` held some 1,400 lines of the harness's process documents beside the product's own; the
state of the handoff was a machine file (`DELIVERY-NOTES.json`); and its commit subjects read like
"Retention, defect_fix_3_3: its tests notice nothing".
"""
from __future__ import annotations

import io
import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from app.acceptance import suite
from app.sprint import product_archive
from app.tools.version_control import commit_all


@pytest.fixture(autouse=True)
def _no_pack(monkeypatch):
    monkeypatch.setattr("app.stacks.contract.the_pack", lambda root: None)
    monkeypatch.setattr("app.tools.repository.pinned_project_directory", lambda root: "app")


def _write(root: Path, files: dict[str, str | bytes]) -> Path:
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode())
    return root


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          check=True, capture_output=True, text=True).stdout


def _archive(root: Path) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(product_archive.build(root, "run-1")))


def test_the_archive_opens_with_a_handover_that_says_what_is_proven_cut_and_limited(tmp_path, monkeypatch):
    root = _write(tmp_path, {
        "app/server.py": "print('hi')\n", "app/start.sh": "python3 server.py\n",
        "DELIVERY-NOTES.json": json.dumps({"deliverable": True, "status": "completed", "notes": [
            "AC-3 ships deferred, unproven by the suite: the export needs a mail server",
            "The product serves through a development server: flask run"]}),
    })
    monkeypatch.setattr(suite, "last_result", lambda repo: {"ran": True, "passed": 4, "failed": 0, "command": "npx playwright test",
        "criteria": {"AC-1": {"text": "Add a note", "status": "passed", "tests": [{"name": "adds a note", "outcome": "passed"}]},
                     "AC-2": {"text": "Delete a note", "status": "passed", "tests": [{"name": "deletes a note", "outcome": "passed"}]},
                     "AC-3": {"text": "Export notes", "status": "deferred", "tests": []}}})

    page = _archive(root).read("run-1/HANDOVER.md").decode()

    assert "2 of 3 criteria pass" in page and "npx playwright test" in page and "adds a note" in page
    cut = page.split("## What was cut and why")[1].split("##")[0]
    assert "AC-3" in cut and "mail server" in cut
    assert "development server" in page.split("## Known limits")[1]
    assert "sh start.sh" in page.split("## How to run, test and deploy it")[1]


def test_the_harness_s_process_documents_go_under_docs_process_and_the_product_s_stay(tmp_path):
    root = _write(tmp_path, {
        "docs/sprint_plan.md": "# Sprint Plan\n", "docs/milestone_plan_2.md": "# Milestone Plan - search\n",
        "docs/reviews/sprint-1-evidence.md": "# Sprint 1 review: notes\n",
        "docs/choices.md": "# Tools and Models\n\n## Frameworks\n",
        "docs/technical_specification.md": "# Technical Specification\n", "docs/api.md": "# API\n",
        "README.md": "# Notes\n\nHow it was planned: docs/sprint_plan.md. The API: docs/api.md.\n",
    })

    names = set(_archive(root).namelist())
    readme = _archive(root).read("run-1/README.md").decode()

    assert {"run-1/docs/process/sprint_plan.md", "run-1/docs/process/milestone_plan_2.md",
            "run-1/docs/process/reviews/sprint-1-evidence.md", "run-1/docs/process/choices.md"} <= names
    assert {"run-1/docs/technical_specification.md", "run-1/docs/api.md"} <= names
    assert "run-1/docs/sprint_plan.md" not in names
    assert "docs/process/sprint_plan.md" in readme and "docs/api.md" in readme


def test_build_output_and_installed_dependencies_are_not_delivered(tmp_path):
    root = _write(tmp_path, {
        ".gitignore": "dist/\n*.log\n", "app/dist/bundle.js": "built", "app/server.log": "log",
        "svc/Svc.csproj": "<Project/>", "svc/bin/Debug/Svc.dll": b"MZ\x90\x00", "svc/obj/project.assets.json": "{}",
        "svc/Program.cs": "class P {}",
        "go/main.go": "package main", "go/bin/server": b"\x7fELF\x02\x01", "go/bin/run.sh": "#!/bin/sh\n",
        "php/composer.json": "{}", "php/vendor/autoload.php": "<?php",
        "cli/bin/cli.js": "#!/usr/bin/env node\n",
    })
    _git(root, "init", "-q")

    files = set(product_archive.files_of(root))

    assert {"svc/Program.cs", "go/main.go", "go/bin/run.sh", "cli/bin/cli.js", "php/composer.json"} <= files
    assert not files & {"app/dist/bundle.js", "app/server.log", "svc/bin/Debug/Svc.dll", "svc/obj/project.assets.json",
                        "go/bin/server", "php/vendor/autoload.php"}


@pytest.mark.parametrize(("message", "subject"), [
    ("Before defect_fix_3_3", "Before the fix of defect 4 in test round 3"),
    ("specialist_ui_ux_0 as written, kept as a candidate", "work order 1 (ui ux) as written, kept as a candidate"),
    ("Fix: docs/milestone_review.md names test_round_trip", "Fix: docs/milestone_review.md names test_round_trip"),
    ("Work orders: add a note", "Work orders: add a note"),
])
def test_a_harness_commit_subject_says_its_stage_in_words(tmp_path, message, subject):
    _git(tmp_path, "init", "-q")
    (tmp_path / "a.txt").write_text(message)

    commit_all(tmp_path, message)

    assert _git(tmp_path, "log", "-1", "--format=%s").strip() == subject
