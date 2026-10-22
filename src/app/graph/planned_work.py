"""Work orders made from the specification by the harness, in fast delivery.

The specification already names every file, what each exports, the order to
build them in, the errors they raise and the cases that prove them. A model
re-deriving work orders from it is a translation, and an unreliable one: one
run's lead was sent back three times for test files its plan gave nobody,
returned the same plan each time, and started over - 23 minutes for a plan.

Here the files are grouped by who writes them - tests to testing, documents
to documentation, the rest to the role that builds the product - and each
work order carries the specification's own lines for its files. The plan is
held to the same definition of ready as a lead's; one that is not ready is
the lead's to write, as before.

Only for building the product, not for changing it. Each planned file is
drafted whole from the specification, so a plan made once the product
exists would write it again and lose every fix since. Measured on one run:
a sprint planned again after its unit tests failed - its acceptance suite
passing - was given every file in the specification to write again. Files
the harness keeps (`contract.owned_by_the_harness`) are no work order's: the
plan that listed `package.json`, `package-lock.json` and `tsconfig.json` was
sent back three times for them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

#: The role that builds the product's code, when no file says otherwise.
_BUILDS = "backend"


def _naming(lines: Any, files: list[str]) -> list[str]:
    """The lines that name one of `files`, by path or by file name."""
    names = {f for path in files for f in (path, path.rsplit("/", 1)[-1])}
    return [str(line) for line in lines or [] if any(name in str(line) for name in names)]


def _role_of(path: str, interface_files: set[str]) -> str:
    from app.analysis.file_kinds import classify_file

    kind = classify_file(path)
    if kind == "test":
        return "testing"
    if kind == "document":
        return "documentation"
    if path in interface_files:
        return "ui_ux"
    return _BUILDS


#: The share of the planned files that, once they exist, makes the product
#: built: a setup may write a few of them before any work order runs.
BUILT_SHARE = 0.5


def work_orders_from_the_specification(
    specification: Any, goal: str, criteria: list[str], verification: list[str],
    repo_root: str | Path | None = None,
) -> Any | None:
    """A milestone plan of one work order per role, made from the specification.

    None when it plans no files, or when the product is already built
    (`BUILT_SHARE` of its planned files exist): changing it is the lead's.
    """
    from app.agents.technical_lead import MilestonePlanOutput, SpecialistTask
    from app.graph.drafting import planned_files
    from app.stacks.contract import owned_by_the_harness

    from app.analysis.work_orders import inside_the_project

    # Named from the workspace root first: the file plan names them as the
    # project sees them, and what the harness keeps is named from the root -
    # `vite.config.ts` was given to a work order, and the plan sent back for it.
    files = [inside_the_project(path, repo_root) for path in planned_files(specification)]
    files = list(dict.fromkeys(path for path in files if not owned_by_the_harness(repo_root, path)))
    if not files:
        return None
    if repo_root and sum((Path(repo_root) / path).is_file() for path in files) >= BUILT_SHARE * len(files):
        return None
    interface_lines = getattr(specification, "interface_design", None) or []
    interface_files = {path for path in files if _naming(interface_lines, [path])}
    by_role: dict[str, list[str]] = {}
    for path in files:
        by_role.setdefault(_role_of(path, interface_files), []).append(path)

    contracts = getattr(specification, "function_contracts", None) or []
    order = getattr(specification, "implementation_order", None) or []
    errors = getattr(specification, "error_catalogue", None) or []
    cases = getattr(specification, "test_cases", None) or []
    tasks = []
    for role, mine in by_role.items():
        product = role != "testing"
        tasks.append(SpecialistTask(
            specialist_role=role,
            title=f"{role.replace('_', ' ').capitalize()}: {', '.join(p.rsplit('/', 1)[-1] for p in mine[:4])}"
                  + (" and more" if len(mine) > 4 else ""),
            task_description=(
                f"Write {', '.join(mine)} exactly as the specification gives them: each file's exports, "
                "function contracts, messages and library calls."
            ),
            acceptance_criteria=list(criteria),
            files=mine,
            interfaces=_naming(contracts, mine) or [f"{path} as the specification's file plan gives it" for path in mine],
            steps=_naming(order, mine) or [f"Write {path}" for path in mine],
            edge_cases=_naming(errors, mine) or ["Every error the specification's error catalogue gives for these files"],
            test_cases=(_naming(cases, mine) or list(cases)) if product else list(cases),
            verification=list(verification) if role != "documentation" else [],
            out_of_scope=["Any file another work order lists", "The locked acceptance suite"],
        ))
    return MilestonePlanOutput(
        selected_sprint_goal=goal,
        milestone_scope=[f"Every file the specification plans: {len(files)} file(s)"],
        delegated_tasks=tasks,
        integration_notes=["Made from the specification by the harness (fast delivery)."],
    )
