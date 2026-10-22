"""Which stack packs pin a package a major version behind its registry.

A pack is a setup proven on the versions it pins, and the registries move on:
Node 20 reached end of life and Angular 22 refused it, and nothing said so
until a run failed. This reads every version each pack pins - package.json,
pyproject.toml and requirements, go.mod, Cargo.toml, pom.xml, composer.json,
Gemfile, .csproj - asks each package's registry for its current release
(`app.tools.package_registry`), and lists the pins a major version behind (for
a 0.x package, a minor version: that is its major).

Runs on the host, with the repository's own environment:

    scripts/loop/loop.sh freshness

A pin behind is a reason to update the pack and run `verify_packs.py`, not an
error: a pack on the previous major still works until that major's support ends.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from app.stacks.packs import ALL_PACKS  # noqa: E402
from app.analysis.manifests import pins  # noqa: E402,F401 - the one reader, kept importable from here
from app.tools.package_registry import look_up  # noqa: E402

_NUMBER = re.compile(r"(\d+)(?:\.(\d+))?")


def _significant(version: str) -> tuple[int, int] | None:
    """(major, minor) of the first version in a range, or None."""
    found = _NUMBER.search(str(version or ""))
    if not found:
        return None
    return int(found.group(1)), int(found.group(2) or 0)


def _behind(pinned: str, latest: str) -> bool:
    have, now = _significant(pinned), _significant(latest)
    if have is None or now is None:
        return False
    if have[0] == 0 and now[0] == 0:
        return now[1] > have[1]
    return now[0] > have[0]


def main() -> int:
    behind = 0
    checked = 0
    for pack in ALL_PACKS:
        files = pack.render("demo-app", "Demo App", "demo_app")
        for file, ecosystem, package, pinned in pins(files):
            checked += 1
            current = look_up(ecosystem, package)
            latest = str(current.get("version") or "")
            if latest and _behind(pinned, latest):
                behind += 1
                print(f"{pack.name:28} {file:22} {package:40} pins {pinned:12} latest {latest}")
    print(f"{checked} pins checked; {behind} a major version behind")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
