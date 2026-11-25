"""Which programs the image a run's commands run in has: one source for every sentence that says so (deep review
2026-11-25, item 5).

Three texts told a model which programs exist, and each was measured somewhere else: the environment contract listed
the testing role's whole allowlist as "Available"; the stack note said "`make`, `pnpm` and `yarn` are not installed
here", measured once on the worker image; and a refusal's "Allowed and installed" asked `shutil.which` in the worker.
In container mode a command runs in its pack's own image, not in the worker. Measured on one Python pack run, one
request said pnpm, poetry, ruff and uv were available (none is in the image), that make and yarn were not installed
(both are), and that cargo and go were installed (neither is).

So the pack's image is asked once per run - one throwaway container running `which` over every program the harness
names - and the answer is kept in `RECORD`. Every text reads it. A program installed into the project's virtualenv,
which every command's PATH puts first, counts as there. Without a pack image, in-container mode, or before the image
has been asked, the worker is asked as before (`sandbox._installed`). Never raises.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

#: The record of what the pack's image has, from the workspace root.
RECORD = ".harness/image-programs.json"
#: Seconds the one probe may take; an image is pulled already, so it starts in a second or two.
PROBE_TIMEOUT = 120
#: Programs the harness's own texts name beyond the allowlists.
_ALSO_NAMED = frozenset({"make", "pnpm", "yarn", "poetry", "uv", "ruff", "cargo", "go"})

_PROBING = threading.Lock()


def the_image(workspace: str | Path | None) -> str:
    """The pack's image this workspace's commands run in, or "" when they run elsewhere."""
    if not workspace:
        return ""
    try:
        from app.stacks.contract import the_pack
        from app.tools.sandbox import CONTAINER_MODE, execution_mode

        if execution_mode() != CONTAINER_MODE:
            return ""
        found = the_pack(workspace)
        return str(found[0].sandbox_image or "") if found is not None else ""
    except Exception:  # noqa: BLE001 - no image known
        return ""


def _every_program_named() -> list[str]:
    from app.tools.sandbox import COMMON_EXECUTABLES, ROLE_EXECUTABLES, TOOLCHAINS

    names = set(COMMON_EXECUTABLES) | set(_ALSO_NAMED)
    for programs in [*ROLE_EXECUTABLES.values(), *TOOLCHAINS.values()]:
        names |= set(programs)
    return sorted(name for name in names if name and "/" not in name)


def read_which(output: str, asked: Iterable[str]) -> set[str]:
    """The programs among `asked` whose path `which` printed."""
    wanted = set(asked)
    return {os.path.basename(line.strip()) for line in str(output or "").splitlines() if line.strip()} & wanted


def _probe(image: str, names: list[str]) -> set[str] | None:
    """The programs among `names` on the image's PATH, by one throwaway container; None when it cannot be asked."""
    from app.tools.sandbox import _docker_binary

    docker = _docker_binary()
    result = subprocess.run(
        [docker, "run", "--rm", "--network", "none", "--entrypoint", "which", image, *names],
        capture_output=True, text=True, timeout=PROBE_TIMEOUT, check=False,
    )
    # `which` exits 1 when any one is missing, and prints the paths of the rest; nothing printed and a failure is
    # an image that could not be started or has no `which`.
    if result.returncode not in (0, 1) or (result.returncode == 1 and not result.stdout.strip()):
        logger.info("Could not ask %s which programs it has (exit %s): %s", image, result.returncode,
                    (result.stderr or "").strip()[:200])
        return None
    return read_which(result.stdout, names)


def recorded(workspace: str | Path | None) -> dict | None:
    """The record for this workspace's current image, or None."""
    image = the_image(workspace)
    if not image:
        return None
    try:
        record = json.loads((Path(workspace) / RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) and record.get("image") == image else None


def ensure(workspace: str | Path | None) -> dict | None:
    """The record for this workspace's image, asking the image once when there is none and commands may run here."""
    try:
        found = recorded(workspace)
        if found is not None:
            return found
        image = the_image(workspace)
        from app.tools.sandbox import execution_enabled

        if not image or not execution_enabled():
            return None
        with _PROBING:
            found = recorded(workspace)
            if found is not None:
                return found
            names = _every_program_named()
            present = _probe(image, names)
            if present is None:
                return None
            record = {"image": image, "asked": names, "present": sorted(present)}
            path = Path(workspace) / RECORD
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
            return record
    except Exception:  # noqa: BLE001 - the worker is asked, as before
        logger.debug("Could not ask the image which programs it has", exc_info=True)
        return None


def _in_the_virtualenv(workspace: str | Path) -> set[str]:
    try:
        from app.tools.sandbox import _the_project_virtualenv

        folder = _the_project_virtualenv(str(workspace), follow_links=False)
        return set(os.listdir(folder)) if folder and os.path.isdir(folder) else set()
    except Exception:  # noqa: BLE001 - none there
        return set()


def split(workspace: str | Path | None, names: Iterable[str], *, with_the_virtualenv: bool = True) -> tuple[list[str], list[str]] | None:
    """`names` as (in the image, not in it) for this workspace's commands; None when the image has not been asked.

    `with_the_virtualenv`: a program the project installed into its virtualenv counts as there. Off for a text that
    must stay the same all run (the environment contract).
    """
    record = ensure(workspace)
    if record is None:
        return None
    present = set(record.get("present") or [])
    asked = set(record.get("asked") or [])
    if with_the_virtualenv:
        present |= _in_the_virtualenv(workspace)
    wanted = sorted(set(names))
    if any(name not in asked and name not in present for name in wanted):
        return None
    return [n for n in wanted if n in present], [n for n in wanted if n not in present]


__all__ = ["RECORD", "ensure", "read_which", "recorded", "split", "the_image"]
