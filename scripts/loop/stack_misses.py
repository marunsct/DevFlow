"""Every stored run whose stack decision said no pack fits while today's `choose_pack` fits one (scaffolding plan SF.0c).

    scripts/loop/loop.sh stack-misses      (runs inside the worker)

A stack sent to the custom setup costs a run its setup stage (median 18 minutes, a tail past 100) and scores lower
than a pack. Misses were fixed one at a time as they were noticed (LF.586, LF.644 ...). This reads every stored
workspace's `docs/technology_stack.md` and decision log, rebuilds the stack it chose, and asks today's selection
again: a run that went custom then and fits a pack now is a miss already fixed; one that still fits none is either
a stack no pack covers (expected) or a miss class still open - the selector's rationale is printed to tell which.
Report only.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path("/app/data/workspaces/default")
_FIELD = re.compile(r"^- \*\*(.+?):\*\*\s*(.*)$", re.M)
_KEYS = {"Language": "language", "Framework": "framework", "Frontend framework": "frontend_framework",
         "Database": "database", "Testing framework": "testing_framework", "Kind of product": "product_kind"}


def stack_of(workspace: Path) -> tuple[SimpleNamespace, str] | None:
    """The stack a run chose and its rationale, from its stack document; None when it has none."""
    try:
        text = (workspace / "docs" / "technology_stack.md").read_text(encoding="utf-8")
    except OSError:
        return None
    fields = {_KEYS[name]: ("" if value.strip().lower() in ("not stated", "none", "-") else value.strip())
              for name, value in _FIELD.findall(text) if name in _KEYS}
    fields["product_kind"] = fields.get("product_kind", "").replace(" ", "_")
    rationale = text.split("## Rationale", 1)[1].split("<!--", 1)[0].strip() if "## Rationale" in text else ""
    return SimpleNamespace(**fields), rationale


def went_custom(workspace: Path) -> bool:
    try:
        decisions = json.loads((workspace / ".harness" / "decisions.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    rows = decisions if isinstance(decisions, list) else decisions.get("decisions", [])
    return any(str(r.get("point")) == "stack" and "no stack pack fits" in str(r.get("decision", "")).lower()
               for r in rows if isinstance(r, dict))


def main(argv: list[str]) -> int:
    sys.path.insert(0, "/app/src")
    from app.stacks import choose_pack

    root = Path(argv[1]) if len(argv) > 1 else ROOT
    fixed, open_ = [], []
    for workspace in sorted(root.glob("workspace-run-*")):
        if not went_custom(workspace):
            continue
        found = stack_of(workspace)
        if found is None:
            continue
        stack, rationale = found
        brief = ""
        try:
            brief = (workspace / "docs" / "product_intake.md").read_text(encoding="utf-8")
        except OSError:
            pass
        pack = choose_pack(stack, brief, rationale)
        line = (f"{workspace.name[10:22]}  {stack.language} / {stack.framework or '-'} / "
                f"{stack.frontend_framework or '-'} / {stack.testing_framework or '-'}")
        (fixed if pack is not None else open_).append((line, pack.name if pack else "", rationale[:160]))
    print(f"runs that went to the custom setup: {len(fixed) + len(open_)}")
    print(f"\nnow fit a pack (a miss since fixed): {len(fixed)}")
    for line, name, _ in fixed:
        print(f"  {line}  -> {name}")
    print(f"\nstill fit no pack: {len(open_)} (a stack no pack covers, or a miss class still open)")
    for line, _, rationale in open_:
        print(f"  {line}\n      {rationale}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
