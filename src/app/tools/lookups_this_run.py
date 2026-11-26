"""The run's own record of what it looked up once, kept in its workspace (LF.1505).

`lookup_service.once_per_run` asks a stuck fixer's error, or a library's usage example, once per run. Its record lived
only in the shared lookup store, and that store is the queue's Redis: past `LOOKUP_STORE_MEMORY_SHARE` of its memory a
value goes to this machine's files instead. Measured on a live run with the store at 307 of 512 MB: the record was
written to the files and read back from the store, which never had it, so one fixer's resumed stage sent the same
query ten times in eleven minutes. The workspace is the run's own and travels with it to any worker, so the record is
read from here first and written here as well, whatever the shared store holds or refuses.

The file names the run it belongs to: a workspace another run reuses starts with an empty record. At most
`MOST_KEPT` values are kept, the oldest dropped first.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Any, Iterator

#: Where the record is kept in the run's workspace.
RECORD_FILE = ".harness/lookups-this-run.json"
#: Values kept at most; the oldest goes first.
MOST_KEPT = 200

_LOCK = threading.Lock()


def _id(kind: str, key: str) -> str:
    return hashlib.sha256(f"{kind}\n{key}".encode("utf-8", errors="replace")).hexdigest()[:32]


def _run_id(run: str) -> str:
    return hashlib.sha256(str(run or "").encode("utf-8", errors="replace")).hexdigest()[:24]


def _file(repo_root: str | Path | None) -> Path | None:
    if not repo_root or not Path(repo_root).is_dir():
        return None
    return Path(repo_root) / RECORD_FILE


def _read(path: Path, run: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or data.get("run") != _run_id(run) or not isinstance(data.get("kept"), dict):
        return {}
    return data["kept"]


@contextlib.contextmanager
def _turn(path: Path) -> Iterator[None]:
    """This record's turn: every thread of this process, and every process on the workspace's machine, waits."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK, open(path.with_name(f".{path.name}.lock"), "a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def kept(repo_root: str | Path | None, run: str, kind: str, key: str) -> Any:
    """The value this run kept for `kind` and `key`, or None. Never raises."""
    path = _file(repo_root)
    if path is None:
        return None
    try:
        return _read(path, run).get(_id(kind, key))
    except Exception:  # noqa: BLE001 - not kept is asked again
        return None


def keep(repo_root: str | Path | None, run: str, kind: str, key: str, value: Any) -> None:
    """Keep `value` for `kind` and `key` in this run's record. Never raises."""
    path = _file(repo_root)
    if path is None or value is None:
        return
    try:
        with _turn(path):
            record = _read(path, run)
            record.pop(_id(kind, key), None)
            record[_id(kind, key)] = value
            text = json.dumps({"run": _run_id(run), "kept": dict(list(record.items())[-MOST_KEPT:])})
            temporary = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
            temporary.write_text(text, encoding="utf-8")
            temporary.replace(path)
    except Exception:  # noqa: BLE001 - the shared store's record still serves
        pass


__all__ = ["MOST_KEPT", "RECORD_FILE", "keep", "kept"]
