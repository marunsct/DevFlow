"""Where a project's unit runner collects its tests, and what follows from a test written anywhere else.

Measured on a full-stack run (a page and a Python service, LF.1262-1263): the lead's work order told the testing
stage to write the service's unit tests in a test folder inside the service's package, beside its code; the pack's
runner collects them only from the project's own unit test folder. The two files written there (361 and 708 lines)
were never run, the throwaway sweep before each test round then deleted them as "tests no suite runs", and the unit
gate passed every round on a run that collected no test at all ("No test files found").

One answer here for every place that asks "is this test file where the runner looks, and if not, where would it be
collected": the work orders, the write guard, the throwaway sweep and the unit gate. All of it is read from the pack:
its unit and acceptance folders, its unit test names, and the folders its own smoke tests sit in.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path, PurePosixPath
from typing import Any, Sequence

logger = logging.getLogger(__name__)

#: A folder whose name says what is inside is tests: what follows it is kept when a test is sent to the unit folder.
_TEST_FOLDERS = frozenset({"tests", "test", "__tests__", "spec", "specs", "e2e"})


def _the_pack(repo_root: str | Path | None) -> tuple[Any, dict[str, Any]] | None:
    try:
        from app.stacks import contract

        return contract.the_pack(repo_root)
    except Exception:  # noqa: BLE001 - no pack says nothing about where tests run
        return None


def _the_unit_folder(pack: Any) -> str:
    """The pack's unit test folder, or "" when its tests sit beside the code and its runner finds them anywhere."""
    folder = str(getattr(pack, "unit_dir", "") or "").strip("/")
    return "" if folder in {"", "."} else folder


def unit_test_names(pack: Any) -> list[str]:
    """The names the pack's unit runner collects, each once: the pack's own list, else its one pattern."""
    names = [str(n) for n in (getattr(pack, "unit_test_names", None) or ()) if str(n).strip()]
    pattern = str(getattr(pack, "unit_pattern", "") or "")
    return list(dict.fromkeys([*names, pattern] if pattern else names))


def _the_folder_for(pack: Any, record: dict[str, Any], name: str, unit_folder: str) -> str:
    """The folder under the project a unit test called `name` is collected from: the folder of the pack's own smoke
    test of the same kind (a page's tests and a service's may sit apart), else the unit folder."""
    suffix = "".join(PurePosixPath(name).suffixes[-1:]).lower()
    try:
        smoke = pack.rendered_smoke_files(str(record.get("project") or ""), str(record.get("title") or ""),
                                          record.get("package"))
    except Exception:  # noqa: BLE001 - the unit folder itself, then
        smoke = {}
    for path in smoke:
        relative = str(path).strip("/")
        if (relative.startswith(f"{unit_folder}/") and suffix
                and "".join(PurePosixPath(relative).suffixes[-1:]).lower() == suffix):
            return str(PurePosixPath(relative).parent)
    return unit_folder


def collected_path(repo_root: str | Path | None, relative_path: str) -> str:
    """The workspace-relative path where the pack's unit runner collects this test file, when it is a test file written
    where none of the project's runners look; "" otherwise (not a test, already collected, a throwaway, the harness's
    own, or no pack that says where its tests run). Never raises."""
    try:
        from app.analysis.file_kinds import classify_file, is_scratch
        from app.stacks import contract

        found = _the_pack(repo_root)
        if found is None:
            return ""
        pack, record = found
        unit_folder = _the_unit_folder(pack)
        if not unit_folder:
            return ""
        project = str(record.get("project") or "").strip("/")
        path = str(relative_path or "").replace("\\", "/").strip().lstrip("/")
        while path.startswith("./"):
            path = path[2:]
        # Without the project's directory on record nothing says where inside it a path starts.
        if not project or not path.startswith(f"{project}/"):
            return ""
        inside = path[len(project) + 1:]
        name = PurePosixPath(inside).name
        if not name or classify_file(inside) != "test" or is_scratch(name):
            return ""
        homes = tuple(f"{d.strip('/')}/" for d in (unit_folder, str(getattr(pack, "acceptance_dir", "") or ""))
                      if d.strip("/"))
        if inside.startswith(homes) or contract.owned_by_the_harness(repo_root, path):
            return ""
        parts = inside.split("/")
        marks = [i for i, part in enumerate(parts[:-1]) if part.lower() in _TEST_FOLDERS]
        below = parts[marks[-1] + 1:] if marks else [name]
        folder = _the_folder_for(pack, record, name, unit_folder)
        return "/".join(part for part in (project, folder, *below) if part)
    except Exception:  # noqa: BLE001 - a check that cannot answer moves nothing
        logger.debug("Could not tell where %s is collected", relative_path, exc_info=True)
        return ""


def the_refusal(relative_path: str, collected: str, where: str) -> str:
    """What a stage is told when it writes a unit test where the runner does not look."""
    return (
        f"Refusing to write '{relative_path}': this project's unit runner collects its tests only under `{where}/`, "
        f"so a test file here would never run. Write it as '{collected}' instead, with the same content (imports "
        "name the product's modules as they are, from the project directory). A throwaway check takes a name "
        "beginning `tmp_`, which the harness clears. Nothing was written."
    )


def _project_files(root: Path, project: str) -> list[str]:
    """Workspace-relative paths of the project's own files: nothing a tool installed or built."""
    from app.analysis.walk import files_under
    from app.tools.repository import IGNORED_DIRECTORIES

    base = root / project if project else root
    if not base.is_dir():
        return []
    skip = {*IGNORED_DIRECTORIES, "node_modules", "__pycache__", "test-results", "playwright-report", ".harness",
            ".git"}
    return sorted(path.relative_to(root).as_posix() for path in files_under(base, skip) if path.is_file())


def _unit_tests_ordered(root: Path, pack: Any, record: dict[str, Any]) -> tuple[list[str], list[str]]:
    """(the unit test files written in the project, the planned ones not written yet): both empty when none was
    ordered. Acceptance tests and the harness's own files are neither."""
    from app.analysis.file_kinds import classify_file, is_scratch
    from app.stacks import contract

    project = str(record.get("project") or "").strip("/")
    acceptance = str(getattr(pack, "acceptance_dir", "") or "").strip("/")

    def a_unit_test(path: str) -> bool:
        if project and not path.startswith(f"{project}/"):
            return False
        inside = path[len(project) + 1:] if project else path
        if classify_file(inside) != "test" or is_scratch(PurePosixPath(inside).name):
            return False
        if acceptance and inside.startswith(f"{acceptance}/"):
            return False
        # A file a test folder holds that is no test by name - a helper, an `__init__` - orders no test.
        return _named_as_a_test(pack, inside) and not contract.owned_by_the_harness(root, path)

    written = [path for path in _project_files(root, project) if a_unit_test(path)]
    planned: list[str] = []
    try:
        from app.tools.repository import WORK_ORDER_FILES

        table = json.loads((root / WORK_ORDER_FILES).read_text(encoding="utf-8"))
        if isinstance(table, dict):
            planned = [str(path) for path in table if a_unit_test(str(path)) and not (root / str(path)).exists()]
    except (OSError, ValueError):
        planned = []
    return written, planned


def _named_as_a_test(pack: Any, inside: str) -> bool:
    """Whether the file's own name is a test's: one the pack's runner collects, or its language's convention (the
    pack's list may name only one of its runners')."""
    import fnmatch

    from app.analysis.file_kinds import classify_file

    name = PurePosixPath(inside).name
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in unit_test_names(pack)) or classify_file(name) == "test"


def none_collected(repo_root: str | Path, reports: Sequence[str | Path], output: str) -> str:
    """Why a unit run that exited as a pass is not one: it collected no test while unit tests were ordered; "" when it
    collected some, cannot be read, or none was ordered yet (a first round before any test is written). Never raises.

    `reports` are the run's JUnit reports, `output` what it printed. Only when a report was read and holds no test,
    and the printed totals say no test ran either.
    """
    try:
        from app.acceptance import junit
        from app.tools.sandbox import _the_counts_a_test_run_reported

        found = _the_pack(repo_root)
        if found is None:
            return ""
        pack, record = found
        read = [junit.read(report) for report in reports]
        if not any(r.found for r in read) or any(r.tests for r in read):
            return ""
        if int(_the_counts_a_test_run_reported({"stdout": str(output or "")}).get("tests") or 0) > 0:
            return ""
        root = Path(repo_root)
        written, planned = _unit_tests_ordered(root, pack, record)
        if not written and not planned:
            return ""
        project = str(record.get("project") or "").strip("/")
        unit_folder = _the_unit_folder(pack)
        command = " ".join(str(part) for part in (record.get("unit_test") or ()))
        where = "/".join(part for part in (project, unit_folder) if part) or "the project"
        names = ", ".join(f"`{name}`" for name in unit_test_names(pack))
        said = [
            f"No unit test ran: `{command}` in `{project or '.'}/` collected none and exited as a pass, while this "
            f"product's unit tests were ordered. The unit runner collects {names or 'its test files'} under "
            f"`{where}/` and nowhere else."
        ]
        misplaced = [(path, collected_path(root, path)) for path in written]
        moved = [f"`{path}` (collected as `{to}`)" for path, to in misplaced if to]
        if moved:
            said.append("These test files sit where it does not look: " + "; ".join(moved[:8])
                        + (f"; and {len(moved) - 8} more" if len(moved) > 8 else "")
                        + ". Move each to the path named, keeping its content.")
        unnamed = [f"`{path}`" for path, to in misplaced if not to]
        if unnamed:
            said.append("These are in its folder and it collected none of them; each must be named as it collects "
                        "and define at least one test: " + ", ".join(unnamed[:8]) + ".")
        if planned:
            said.append("The work orders plan these unit test files, not written yet: "
                        + ", ".join(f"`{path}`" for path in planned[:8]) + ".")
        return " ".join(said)
    except Exception:  # noqa: BLE001 - the run's own exit code stands
        logger.debug("Could not tell whether the unit run collected any test", exc_info=True)
        return ""


__all__ = ["collected_path", "none_collected", "the_refusal", "unit_test_names"]
