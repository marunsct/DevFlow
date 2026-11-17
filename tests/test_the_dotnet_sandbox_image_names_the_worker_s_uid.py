"""The .NET sandbox image has an account for the uid the worker runs commands as, its home somewhere writable.

Measured in container mode: .NET keeps its named mutexes under the account's home from the passwd database, not
`$HOME`; the worker runs each command as its own uid, which the image had no entry for, and every `dotnet restore`
failed on "cannot open the device or file specified: 'NuGet-Migrations'" - the C# scaffold could not be proven.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_the_image_s_account_is_the_worker_s_uid_and_its_home_is_the_writable_tmp():
    worker = re.search(r"useradd [^\n]*--uid (\d+)[^\n]*appuser", (ROOT / "Dockerfile").read_text())
    assert worker, "the worker image's appuser uid"
    image = (ROOT / "deploy/sandbox-images/dotnet/Dockerfile").read_text()
    account = re.search(r"useradd --uid (\d+) --gid (\d+) --home-dir (\S+)", image)
    assert account and account.group(1) == worker.group(1) == account.group(2)
    assert account.group(3) == "/tmp"  # the container's one writable place (`sandbox` mounts a tmpfs there)
