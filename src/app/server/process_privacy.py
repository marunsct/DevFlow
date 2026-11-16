"""The worker's own memory and environment kept from the commands it runs (LR.30, first step of isolation).

Found in the launch review: in in-container mode an agent-run command runs as the worker's own user, and a same-user
process can read another's `/proc/<pid>/environ` - the database password, the signing key and the provider keys -
although the command's own environment is filtered. A process marked not dumpable keeps its `/proc` files owned by
root, so a same-user process can neither read them nor attach to it. A command the worker starts is dumpable again
after it executes its program, which is what it needs; only the worker's own processes are marked.
"""
from __future__ import annotations

import ctypes
import logging
import sys

logger = logging.getLogger(__name__)

PR_SET_DUMPABLE, PR_GET_DUMPABLE = 4, 3


def keep_private() -> bool:
    """Mark this process not dumpable; whether it now is. Never raises; does nothing off Linux."""
    if not sys.platform.startswith("linux"):
        return False
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(PR_SET_DUMPABLE, 0, 0, 0, 0) != 0:
            return False
        return libc.prctl(PR_GET_DUMPABLE, 0, 0, 0, 0) == 0
    except Exception:  # noqa: BLE001 - a worker that cannot be marked works as before
        logger.warning("Could not mark the worker process private", exc_info=True)
        return False


__all__ = ["keep_private"]
