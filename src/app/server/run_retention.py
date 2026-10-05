"""What deleting a run removes beyond its row, workspace, checkpoints and events.

A run leaves records in several places outside its workspace, and they hold the
same material the workspace did - the brief, the source, every model request
and reply. Deleting the run used to leave all of them behind:

    DATA_DIR/transcripts/<run>.jsonl         every model request, reply, tool call and result
    DATA_DIR/ledger/<workspace>.jsonl        every command the run ran
    DATA_DIR/journal/*-<run scope>-*.log     full outputs of commands the run ran
    object store  runs/<run>/...             the durable copy of the finished product
    object store  uploads/<name>             the durable copy of each upload

The contract: deleting a run removes all of them, along with what the delete
endpoint already removed. Kept: the audit log line recording who deleted it,
and the compaction context store, which is per agent rather than per run (see
`delete_run`) and ages out on its own. `RUN_DELETE_KEEPS_RECORDS=true` holds
the transcript, ledger and journal - for a deployment that must keep an audit
trail of what its agents did - and still removes the product and the uploads.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)


def records_are_held() -> bool:
    """Whether deleting a run keeps its transcript, ledger and journal."""
    return os.environ.get("RUN_DELETE_KEEPS_RECORDS", "").strip().lower() in {"1", "true", "yes", "on"}


def _unlink(path: Path | None) -> int:
    if path is None:
        return 0
    try:
        if path.is_file():
            path.unlink()
            return 1
    except OSError:
        logger.warning("Could not remove %s", path, exc_info=True)
    return 0


def purge_run_records(run_id: str, repo_root: str | None, removed_uploads: Iterable[str] = ()) -> int:
    """Remove what a deleted run left outside its workspace. Returns how many items went.

    Never raises: each store is tried on its own, so one that cannot be reached
    leaves the others to be removed, and a failure is logged rather than
    turning a delete the operator asked for into an error.
    """
    removed = 0
    if not records_are_held():
        try:
            from app.observability.transcript import transcript_path

            removed += _unlink(transcript_path(run_id))
        except Exception:  # noqa: BLE001
            logger.warning("Could not remove the transcript of %s", run_id, exc_info=True)
        if repo_root:
            try:
                from app.tools.sandbox import _ledger_path

                removed += _unlink(_ledger_path(repo_root))
            except Exception:  # noqa: BLE001
                logger.warning("Could not remove the ledger of %s", run_id, exc_info=True)
            try:
                from app.tools.journal import journal_root, scope_of

                scope = scope_of(repo_root)
                root = journal_root()
                if scope and root.is_dir():
                    for entry in root.glob(f"*-{scope}-*"):
                        removed += _unlink(entry)
            except Exception:  # noqa: BLE001
                logger.warning("Could not remove the journal entries of %s", run_id, exc_info=True)

    try:
        from app.server.object_store import get_object_store

        store = get_object_store()
        keys = list(store.list_prefix(f"runs/{run_id}"))
        keys += [f"uploads/{Path(path).name}" for path in removed_uploads]
        for key in keys:
            try:
                store.delete(key)
                removed += 1
            except Exception:  # noqa: BLE001
                logger.warning("Could not remove stored object %s", key, exc_info=True)
        local_copy = getattr(store, "root", None)
        if isinstance(local_copy, Path):
            # The local backend leaves the run's directories behind once empty.
            directory = local_copy / "runs" / run_id
            for child in sorted(directory.rglob("*"), reverse=True) if directory.is_dir() else ():
                if child.is_dir():
                    child.rmdir()
            if directory.is_dir():
                directory.rmdir()
    except Exception:  # noqa: BLE001
        logger.warning("Could not remove the stored copies of %s", run_id, exc_info=True)
    return removed
