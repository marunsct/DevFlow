"""Services a test started with the harness's restart helper and never stopped are stopped after the command that ran it.

Measured on a run: the helper (`acceptance/service.cjs`) starts the project's `start.sh` in a process group of its own,
so that `stop()` can end the whole service; a test that failed before calling `stop()` left it running, owned by no one.
After a morning of runs 130 such services were alive in the worker, about 4 GB, and the worker's process was killed
with SIGKILL in the middle of a run. The helper marks every service it starts with `HARNESS_SERVICE_OF` (the project
folder); after each command, any such service whose parent is gone is stopped. Linux only (`/proc`); elsewhere nothing.
"""
from __future__ import annotations

import logging
import os
import signal
from pathlib import Path

logger = logging.getLogger(__name__)

#: The environment variable the helper puts on every service it starts.
MARK = "HARNESS_SERVICE_OF"


def _parent(stat: str) -> int:
    # `pid (comm) state ppid ...` - the command can hold spaces and brackets, so read after the last ")".
    return int(stat.rsplit(")", 1)[1].split()[1])


def stop_strays(repo_root: str | Path, proc: Path = Path("/proc")) -> int:
    """Stop the orphaned services the helper started under `repo_root`; how many. Never raises."""
    try:
        base = str(Path(repo_root).resolve())
        marker = MARK.encode() + b"="
        stopped = 0
        for entry in proc.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                environ = (entry / "environ").read_bytes().split(b"\0")
                stat = (entry / "stat").read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            owner = next((item[len(marker):].decode(errors="replace") for item in environ if item.startswith(marker)), "")
            if not owner or not (owner == base or owner.startswith(base + os.sep)):
                continue
            if _parent(stat) != 1:
                continue  # its test is still running it
            try:
                os.kill(int(entry.name), signal.SIGKILL)
                stopped += 1
            except OSError:
                continue
        if stopped:
            logger.warning("Stopped %d service(s) a test started and never stopped", stopped)
        return stopped
    except Exception:  # noqa: BLE001 - a clean-up never fails a command
        logger.debug("Could not look for stray services", exc_info=True)
        return 0


__all__ = ["MARK", "stop_strays"]
