"""A run's handover pack holds its documents, its decisions and its acceptance suite, and nothing else."""

from __future__ import annotations

import io
import zipfile

from app.sprint import handover


def test_the_pack_holds_the_documents_decisions_and_suite(tmp_path, monkeypatch):
    (tmp_path / "docs" / "reviews").mkdir(parents=True)
    (tmp_path / "docs" / "technical_specification.md").write_text("# Spec\n")
    (tmp_path / "docs" / "reviews" / "release-evidence.md").write_text("# Release\n")
    (tmp_path / ".harness").mkdir()
    (tmp_path / ".harness" / "decisions.json").write_text("[]")
    (tmp_path / ".harness" / "secret-scratch.txt").write_text("no")
    (tmp_path / "notes-api" / "acceptance").mkdir(parents=True)
    (tmp_path / "notes-api" / "acceptance" / "api.spec.ts").write_text("test()")
    (tmp_path / "notes-api" / "src").mkdir()
    (tmp_path / "notes-api" / "src" / "app.ts").write_text("code")
    monkeypatch.setattr(handover, "_acceptance_directory", lambda root: "notes-api/acceptance")

    names = zipfile.ZipFile(io.BytesIO(handover.build(tmp_path, "run-x"))).namelist()

    assert names == [
        "run-x-handover/docs/reviews/release-evidence.md",
        "run-x-handover/docs/technical_specification.md",
        "run-x-handover/notes-api/acceptance/api.spec.ts",
        "run-x-handover/.harness/decisions.json",
    ]


def test_the_server_serves_a_run_s_pack_as_a_zip(client, run_store, tmp_path):
    brief = tmp_path / "brief.md"
    brief.write_text("A product")
    with open(brief, "rb") as handle:
        run_id = client.post("/api/runs", files=[("files", ("brief.md", handle, "text/plain"))]).json()["run_id"]
    record = run_store.load(run_id)
    record.repo_root = str(tmp_path)
    run_store.save(record)

    answer = client.get(f"/api/runs/{run_id}/handover")

    assert answer.status_code == 200 and answer.headers["content-type"] == "application/zip"
    assert zipfile.ZipFile(io.BytesIO(answer.content)).testzip() is None
