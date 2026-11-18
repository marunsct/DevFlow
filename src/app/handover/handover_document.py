"""`HANDOVER.md`: the one document a person taking the product over reads first (deep review 2026-11-18, F4b).

Found on a delivered product: the state of the handoff was a machine file (`DELIVERY-NOTES.json`), the README a
generated block, and what the product was proven to do, what was cut and why, and how to run and deploy it were
spread over JSON, the README and some 1,400 lines of process documents. This writes them as one page, from what the
run recorded (`facts.document_facts`, the terminal marker or delivery notes, the stack's commands, the release files
present). No model writes a word of it, so it cannot claim a test that did not run. Assembled when the product is
downloaded; nothing is written to the workspace.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

#: The release files that say how the product is deployed, where the stack pack writes them.
_DEPLOY_FILES = ("Dockerfile", "docker-compose.yml", "compose.yaml", "Procfile")


def _one_line(text: Any, most: int = 300) -> str:
    said = " ".join(str(text or "").split())
    return said if len(said) <= most else said[: most - 3].rstrip() + "..."


def _the_state(root: Path) -> dict[str, Any]:
    """The terminal marker or the delivery notes the run left, as written; {} when it left neither."""
    from app.graph import terminal_state

    marker = terminal_state.read(root)
    if marker:
        return marker
    try:
        found = json.loads((root / terminal_state.NOTES).read_text(encoding="utf-8"))
        return found if isinstance(found, dict) else {}
    except (OSError, ValueError):
        return {}


def _deploy_files(root: Path, project: str) -> list[str]:
    found = sorted(p.relative_to(root).as_posix() for p in (root / ".github" / "workflows").glob("*.y*ml")) \
        if (root / ".github" / "workflows").is_dir() else []
    base = root / project if project else root
    for name in _DEPLOY_FILES:
        if (base / name).is_file():
            found.append((base / name).relative_to(root).as_posix())
    return found


def document(facts: dict[str, Any], state: dict[str, Any], steps: list[str], deploy_files: list[str],
             *, acceptance_dir: str = "", moved_documents: bool = False) -> str:
    """The handover page from the run's recorded facts; pure, so every line is a fact passed in."""
    from app import completion_verdict

    product = facts.get("product") or facts.get("project") or "the product"
    project = str(facts.get("project") or "")
    gaps = [str(g) for g in state.get("completion_gaps") or []]
    notes = [str(n) for n in state.get("notes") or []]
    cuts = [n for n in [*gaps, *notes] if completion_verdict.is_a_cut(n)]
    limits = [n for n in [*gaps, *notes] if not completion_verdict.is_a_cut(n)]
    criteria = list(facts.get("criteria") or [])
    passed = [c for c in criteria if c.get("status") == "passed"]

    lines = [f"# Handover: {product}", ""]
    if state.get("deliverable") is False:
        lines += [f"**Not deliverable as it stands.** {_one_line(state.get('reason'), 600)}", ""]
    elif state:
        lines += ["**Delivered**" + (" with scope cuts, named below." if cuts else ".")
                  + (" Read the known limits before relying on it." if limits else ""), ""]
    lines += ["Written by the harness from what it recorded and measured; nothing here is a model's claim.", ""]

    lines += ["## What was built", ""]
    where = f" in `{project}/`" if project else ""
    pack = f", on the `{facts['pack']}` stack" if facts.get("pack") else ""
    commit = f" at commit `{str(facts['commit'])[:12]}`" if facts.get("commit") else ""
    lines += [f"{product}{where}{pack}{commit}. What it does is held to these acceptance criteria:", ""]
    lines += [f"- {c['id']}: {_one_line(c.get('text'))}" for c in criteria] or ["- No acceptance criteria were recorded."]
    lines.append("")

    lines += ["## What is proven", ""]
    acceptance = facts.get("acceptance") or {}
    if criteria and acceptance.get("ran"):
        command = f" by `{facts['acceptance_command']}`" if facts.get("acceptance_command") else ""
        lines += [f"{len(passed)} of {len(criteria)} criteria pass, measured{command}: "
                  f"{acceptance.get('passed', 0)} acceptance tests passed, {acceptance.get('failed', 0)} failed.", "",
                  "| Criterion | Status | Proven by |", "| --- | --- | --- |"]
        for c in criteria:
            tests = [t for t in c.get("tests") or [] if (t or {}).get("name")]
            by = "; ".join(_one_line(t["name"], 80) for t in tests[:3]) + (f" and {len(tests) - 3} more" if len(tests) > 3 else "")
            lines.append(f"| {c['id']} | {c.get('status') or 'untested'} | {(by or 'no test').replace('|', '/')} |")
    else:
        lines.append("The acceptance suite has no measurement on record.")
    unit = list(facts.get("unit_tests") or [])
    if unit:
        failed = sum(1 for t in unit if t.get("outcome") == "failed")
        command = f" (`{facts['unit_command']}`)" if facts.get("unit_command") else ""
        lines += ["", f"Unit tests{command}: {len(unit) - failed} of {len(unit)} pass."]
    lines.append("")

    lines += ["## What was cut and why", ""]
    lines += [f"- {_one_line(cut, 600)}" for cut in cuts] or ["Nothing was cut: every criterion was built and measured."]
    lines.append("")

    lines += ["## How to run, test and deploy it", ""]
    if steps:
        lines += ["From this folder:", "", "```sh", *steps, "```"]
    else:
        lines.append("The stack recorded no commands to install, test and start it; the README says what is known.")
    if deploy_files:
        lines += ["", "Deployment files the release added or kept: " + ", ".join(f"`{f}`" for f in deploy_files)
                  + ". The CI pipeline runs the commands above; a container definition was written, not built, by "
                  "the harness."]
    lines.append("")

    lines += ["## Known limits", ""]
    lines += [f"- {_one_line(limit, 600)}" for limit in limits] or ["None recorded."]
    lines.append("")

    lines += ["## Where the rest is", "", "- `README.md`: the product's own introduction."]
    if acceptance_dir:
        lines.append(f"- `{acceptance_dir}/`: the locked acceptance suite the criteria above were measured with.")
    lines.append("- `docs/`: the product's documents, the specification among them.")
    if moved_documents:
        lines.append("- `docs/process/`: how the product was built - plans, reviews and sprint records.")
    return "\n".join(lines).rstrip() + "\n"


def write_for(repo_root: str | Path, *, run_id: str = "", steps: list[str] | None = None,
              moved_documents: bool = False) -> str:
    """The handover page for a workspace. Never raises: a part that cannot be read is left out, never invented."""
    from app.handover.facts import document_facts
    from app.stacks import contract

    root = Path(repo_root)
    facts = document_facts(root, run_id=run_id)
    try:
        record = contract.read(root) or {}
    except Exception:  # noqa: BLE001 - the page without the suite's place
        record = {}
    project = str(record.get("project") or "")
    acceptance = str(record.get("acceptance_dir") or "")
    try:
        state = _the_state(root)
    except Exception:  # noqa: BLE001
        state = {}
    return document(facts, state, list(steps or []), _deploy_files(root, project),
                    acceptance_dir=f"{project}/{acceptance}" if project and acceptance else acceptance,
                    moved_documents=moved_documents)


__all__ = ["document", "write_for"]
