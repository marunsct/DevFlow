"""One account of the facts a sprint's work is built under, for the stages that build it and the stages that judge it (plan CM.1).

Of fifteen failures traced to agents missing something, about eleven were one
stage lacking a fact another stage or the harness already had, each patched for
one stage at a time: a review undid the file-database fallback the architect
had been told to plan (LF.42), the security review demanded a secret the
product then could not start without (LF.90). Measured again on one run: every
fixer was told which code the product does not run, and the milestone review
that accepted the release was not - it passed a product whose planned modules,
59% of its lines, nothing imported.

So the facts come from one function, read from the workspace and the pack it is
set up with, and every builder and judge request appends the same block. A
judge sees what the builder was given; it never sees the builder's reasoning
or transcript (CM.5).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: Group 2 of the plan is measured before and after (ADR-0010): built while a
#: gate run measures the code without it, so it stays off until that run ends.
#: `SHARED_FACTS` set to on or off overrides this.
ON_BY_DEFAULT = False


def enabled() -> bool:
    """Whether builder and judge requests end with the facts (plan CM.1)."""
    from app.switches import is_on

    return is_on("SHARED_FACTS", ON_BY_DEFAULT)

#: The heading every builder and judge reads the block under.
HEADING = "--- The facts this work is built and judged under ---"


def layout_facts(pack: Any, project: str, package: str | None) -> list[str]:
    """The pack's layout and data store for this project, one line each.

    The architect wrote the file plan knowing the stack, not the layout the
    harness would set up for it. Measured on one run: the plan put the service
    in `backend/app/` and the page in `frontend/src/` while the scaffold served
    the package's `main.py` and `src/App.tsx`; 28 files were drafted where
    nothing served them.
    """
    served = [pack.filled(e, project, "", package) for e in (pack.entrypoint, *pack.entrypoints) if e]
    prefix = f"{project}/" if project else ""
    lines = [f"- The project lives in `{prefix or './'}`."]
    if served:
        lines.append("- What the product serves, and the acceptance suite runs through: "
                     + ", ".join(f"`{prefix}{path}`" for path in served)
                     + ". Plan the product in these files, or in modules they import.")
    lines.append(f"- Unit tests: `{pack.unit_pattern}` in `{prefix}{pack.unit_dir}/`; acceptance tests: "
                 f"`{pack.acceptance_pattern}` in `{prefix}{pack.acceptance_dir}/`.")
    if getattr(pack, "data_store", ""):
        lines.append("- Where the data lives: " + " ".join(str(pack.data_store).split()))
    started = str((getattr(pack, "files", None) or {}).get("start.sh") or "")
    if started:
        # The setup's own start script, already proven by its smoke test. Both
        # Measure gate runs' specifications designed a start.sh of their own,
        # and one - `exec python tasks_api/app.py`, a Python without the
        # product's dependencies - was drafted over the working one: every
        # locked test passed and the service did not start for anyone else.
        command = next((line.strip() for line in pack.filled(started, project, "", package).splitlines()
                        if line.strip() and not line.startswith("#")), "")
        lines.append(f"- `{prefix}start.sh` is already set up and starts the service as the brief asks"
                     + (f" (`{command}`)" if command else "")
                     + ": the file plan keeps it as it is, and changes it only for something the brief "
                     "asks that it does not do.")
    kept = [path for path in pack.kept_files if path not in served]
    if kept:
        lines.append("- Kept by the harness, not the product's to write: "
                     + ", ".join(f"`{prefix}{path}`" for path in kept[:8]) + ".")
    if kept or started:
        # Measured on three runs: the specification put creating the data directory and checking the port in the
        # pack's `start.sh`, and signal handling in its kept start file; the reviews then sent the sprint back for
        # behaviour no work order may write there.
        lines.append("- Those files do what they do now and nothing more: put whatever else the product must do - "
                     "at start, at shutdown, with its settings or its data directory - in the product's own files.")
    return lines


def facts_from_the_workspace(root: str | Path | None, *, built: bool = True) -> list[str]:
    """The layout, a served stub and the code the product does not run, as measured now; [] before a pack is set up. Never raises.

    `built` is False for the stages still writing the product: until the work
    orders are done the scaffold's stub is still served and the modules
    written so far are not yet imported, which is how building goes, not a
    finding. They get the layout alone.
    """
    if not root:
        return []
    try:
        from app.stacks import contract, pack_named
        from app.stacks.scaffold import code_the_product_does_not_run, entrypoint_is_still_the_stub

        record = contract.read(root) or {}
        pack = pack_named(str(record.get("pack") or ""))
        if pack is None:
            return []
        lines = layout_facts(pack, str(record.get("project") or ""), str(record.get("package") or "") or None)
        if not built:
            return lines
        stub = entrypoint_is_still_the_stub(root)
        if stub:
            lines.append(f"- `{stub}` is still byte for byte the scaffold's stub: nothing drafted elsewhere is served.")
        lines.extend(f"- Code the product does not run: {problem}" for problem in code_the_product_does_not_run(root))
        return lines
    except Exception:  # noqa: BLE001 - a request without the facts is the request as it was
        logger.debug("Could not read the workspace's facts", exc_info=True)
        return []


def the_facts_section(root: str | Path | None, *, built: bool = True) -> str:
    """The block a builder or judge request ends with; "" when there are no facts yet or it is off."""
    if not enabled():
        return ""
    facts = facts_from_the_workspace(root, built=built)
    if not facts:
        return ""
    return f"\n\n{HEADING}\n" + "\n".join(facts) + "\n"


def with_the_facts(request: dict[str, Any], root: str | Path | None, *, built: bool = True) -> dict[str, Any]:
    """`request` with the facts block appended to its last message. Never raises."""
    try:
        section = the_facts_section(root, built=built)
        if section and request.get("messages"):
            last = request["messages"][-1]
            if isinstance(last, dict) and isinstance(last.get("content"), str):
                last["content"] += section
    except Exception:  # noqa: BLE001 - as above
        logger.debug("Could not add the facts to a request", exc_info=True)
    return request
