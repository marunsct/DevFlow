"""Deleting a run removes its transcript, ledger, journal and stored copies.

They hold what the workspace held - the brief, the source, every model request
and reply - and the delete endpoint used to leave every one of them behind.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from app.server import object_store
from app.server.run_retention import purge_run_records

RUN = "run-deadbeef-1111-2222-3333-444455556666"
OTHER = "run-abc12345-1111-2222-3333-444455556666"


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("OBJECT_STORE_PATH", raising=False)
    monkeypatch.delenv("OBJECT_STORE_BUCKET", raising=False)
    monkeypatch.delenv("CTX_JOURNAL_ROOT", raising=False)
    monkeypatch.delenv("RUN_DELETE_KEEPS_RECORDS", raising=False)
    object_store.reset_object_store()
    yield tmp_path
    object_store.reset_object_store()


def _leave_records(root: Path, run_id: str) -> dict[str, Path]:
    workspace = root / "workspaces" / "default" / f"workspace-{run_id}"
    scope = "-".join(run_id.split("-")[:2])
    files = {
        "transcript": root / "transcripts" / f"{run_id}.jsonl",
        "ledger": root / "ledger" / f"workspace-{run_id}.jsonl",
        "journal": root / "journal" / f"1790906829-{scope}-npx-stdout-fe8478df.log",
        "product": root / "objects" / "runs" / run_id / "app" / "index.html",
        "upload": root / "objects" / "uploads" / f"brief_{run_id[4:12]}.md",
    }
    for path in files.values():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("brief, source, replies")
    files["workspace"] = workspace
    return files


def test_every_record_of_the_run_goes_and_no_other_runs(data) -> None:
    mine, theirs = _leave_records(data, RUN), _leave_records(data, OTHER)

    removed = purge_run_records(RUN, str(mine["workspace"]), [f"/app/data/uploads/{mine['upload'].name}"])

    assert removed == 5
    for name in ("transcript", "ledger", "journal", "product", "upload"):
        assert not mine[name].exists(), name
        assert theirs[name].exists(), name
    assert not (data / "objects" / "runs" / RUN).exists()


def test_an_upload_another_run_still_uses_is_kept(data) -> None:
    mine = _leave_records(data, RUN)
    purge_run_records(RUN, str(mine["workspace"]), [])
    assert mine["upload"].exists()


def test_held_records_keep_the_audit_trail_but_not_the_product(data, monkeypatch) -> None:
    monkeypatch.setenv("RUN_DELETE_KEEPS_RECORDS", "true")
    mine = _leave_records(data, RUN)

    purge_run_records(RUN, str(mine["workspace"]), [f"x/{mine['upload'].name}"])

    assert mine["transcript"].exists() and mine["ledger"].exists() and mine["journal"].exists()
    assert not mine["product"].exists() and not mine["upload"].exists()


def test_a_run_with_no_records_deletes_cleanly(data) -> None:
    assert purge_run_records(RUN, None, []) == 0


def test_a_store_that_fails_does_not_stop_the_others(data, monkeypatch) -> None:
    mine = _leave_records(data, RUN)

    def broken():
        raise RuntimeError("store down")

    monkeypatch.setattr(object_store, "get_object_store", broken)
    purge_run_records(RUN, str(mine["workspace"]), [])
    assert not mine["transcript"].exists() and mine["product"].exists()


def test_the_delete_endpoint_purges_them() -> None:
    from app.server import runs

    source = inspect.getsource(runs)
    start = source.index("async def delete_run")
    body = source[start:source.index("runner.run_store.delete(run_id)", start)]
    assert "purge_run_records(run_id, record.repo_root, unshared)" in body
