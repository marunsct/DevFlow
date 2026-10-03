"""How often each cross-file check fires over stored products, and how often wrongly.

Run inside the worker, where the workspaces are:

    scripts/loop/loop.sh checks [labels.json]

For every workspace under the workspace root, every registered check is run and
its findings counted. With a labels file - {"<workspace name>": {"<check
name>": "false"}} marking findings a person has judged wrong - each check's
precision is printed too. A check that is not mechanical (see
`integration_checks._MECHANICAL`) and fires falsely is a hint at best; one that
is mechanical and fires falsely is a bug.

Prints one line per check, most-firing first, then the workspaces each flagged.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from app.analysis.integration_checks import _CHECKS, _MECHANICAL, _source_files

ROOT = Path("/app/data/workspaces/default")


def main() -> None:
    labels: dict[str, dict[str, str]] = {}
    if len(sys.argv) > 1 and Path(sys.argv[1]).is_file():
        labels = json.loads(Path(sys.argv[1]).read_text())
    brief = ""
    flagged: dict[str, list[str]] = defaultdict(list)
    workspaces = sorted(p for p in ROOT.iterdir() if p.is_dir() and p.name.startswith("workspace-"))
    for workspace in workspaces:
        try:
            files = _source_files(workspace)
        except Exception:  # noqa: BLE001
            continue
        for name, check in _CHECKS:
            try:
                found = check(files, workspace, None, brief)
            except Exception:  # noqa: BLE001 - a check that raises is reported as such
                found = ["(raised)"]
            if found:
                flagged[name].append(workspace.name)
    print(f"{len(workspaces)} workspaces, {len(_CHECKS)} checks\n")
    print(f"{'fires':>5}  {'false':>5}  kind        check")
    for name, _ in sorted(_CHECKS, key=lambda entry: -len(flagged.get(entry[0], []))):
        hits = flagged.get(name, [])
        false = sum(1 for ws in hits if labels.get(ws, {}).get(name) == "false")
        kind = "mechanical" if name in _MECHANICAL else "inferred"
        print(f"{len(hits):>5}  {false if labels else '-':>5}  {kind:<10}  {name}")
    print()
    for name, hits in sorted(flagged.items(), key=lambda item: -len(item[1])):
        print(f"{name}:")
        for ws in hits:
            print(f"    {ws}")


if __name__ == "__main__":
    main()
