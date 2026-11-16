"""Whether the disk the harness keeps its database and runs on has room for another run (LR.3).

Measured twice: the disk the database lives on filled (a model server's logs grew without bound), Postgres stopped
with "No space left on device" and every run failed; runs sat stopped for eleven hours. Nothing checked the space
before a run started. Prints one line; exits 1 when the free space is below `DISK_MIN_FREE_GB` (default 50) or
`DISK_MIN_FREE_PERCENT` (default 5), and warns from twice those.

Usage: python3 disk_ready.py [path ...]   (default: the repository's data directory)
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

GB = 1024 ** 3


def verdict(path: str, total: int, free: int, *, min_gb: float, min_percent: float) -> tuple[int, str]:
    """(exit code, line) for one disk: 1 below the floor, 0 otherwise (a warning from twice the floor)."""
    gb, percent = free / GB, (100.0 * free / total) if total else 0.0
    said = f"{path}: {gb:.0f} GB free ({percent:.0f}%)"
    if gb < min_gb or percent < min_percent:
        return 1, f"DISK FULL SOON {said}, under the floor of {min_gb:.0f} GB / {min_percent:.0f}%: start nothing; clear space"
    if gb < 2 * min_gb or percent < 2 * min_percent:
        return 0, f"DISK LOW {said}: clear space before it reaches {min_gb:.0f} GB"
    return 0, f"DISK OK {said}"


def main(argv: list[str]) -> int:
    min_gb = float(os.environ.get("DISK_MIN_FREE_GB", "50"))
    min_percent = float(os.environ.get("DISK_MIN_FREE_PERCENT", "5"))
    paths = argv or [str(Path(__file__).resolve().parents[2] / "data")]
    worst = 0
    for path in paths:
        usage = shutil.disk_usage(path)
        code, line = verdict(path, usage.total, usage.free, min_gb=min_gb, min_percent=min_percent)
        print(line)
        worst = max(worst, code)
    return worst


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
