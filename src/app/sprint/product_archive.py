"""The product itself, as one archive a person can download, with its handover page (LR.30a, deep review F4b).

Found in the launch review: after a run of one to three hours the page said "Finished. The results are ready below",
and the only download was the handover pack (documents, decisions and the acceptance suite) or one file at a time:
the product could not be taken away. The archive holds the workspace as the product ships - its git history
included, so its commits come with it - without dependency folders, build output, test-runner output, or the
harness's own files.

Found in the deep review of 2026-11-18 (F4b): a delivered product's root held installed dependencies, test-runner
output and built binaries; its `docs/` mixed some 1,400 lines of the harness's process documents with the product's
own; and the state of the handoff was a machine file. The archive now leaves out what git ignores and what a build
or an install fills, keeps the harness's process documents under `docs/process/`, and opens with `HANDOVER.md`
(`app.handover.handover_document`). Nothing in the workspace is changed: all of it happens as the archive is built.
"""
from __future__ import annotations

import io
import os
import re
import shlex
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Any

#: The most one archive may hold, uncompressed.
MOST_BYTES = 300 * 1024 * 1024
#: Folders left out wherever they are: dependencies and build caches a person installs or rebuilds.
_LEFT_OUT = frozenset({
    "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "target",
    "test-results", "playwright-report", "blob-report", "coverage", ".nyc_output", "htmlcov", ".turbo",
    ".parcel-cache", ".vite", ".cache",
})
#: The harness's own folders at the workspace root: how it worked, not what it built.
_HARNESS_OWN = frozenset({".harness", ".agent-home"})
#: Folders a build or an install fills, by the project file beside them: .NET's `bin/` and `obj/`; `vendor/`.
_FILLED_BESIDE = {
    "bin": (".csproj", ".fsproj", ".vbproj"),
    "obj": (".csproj", ".fsproj", ".vbproj"),
    "vendor": ("composer.json", "go.mod", "Gemfile"),
}
#: The first bytes of a compiled executable or class: ELF, Windows PE, Mach-O (both byte orders, fat), Java.
_COMPILED = (b"\x7fELF", b"MZ", b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe")
#: Where the harness's own documents go in the archive, apart from the product's.
PROCESS_FOLDER = "docs/process"
#: The harness's process documents under `docs/`, by the names it writes them under (`app.doc_templates`,
#: `app.decisions`, the sprint record)...
_PROCESS_NAMES = re.compile(
    r"^(?:sprint_plan|milestone_plan|milestone_review|architecture_review|security_review|product_intake"
    r"|technology_stack|tools_and_models|decision_log|sprint_\d+_summary)(?:[_-]\d+)?\.md$")
#: ...the folders it keeps its reviews, evidence pages and stage summaries in...
_PROCESS_FOLDERS = frozenset({"reviews", "stage_summaries", "generated"})
#: ...and by how they are written: the first heading each of those templates gives its document.
_PROCESS_HEADINGS = re.compile(
    r"^#\s+(?:Sprint Plan|Milestone Plan|Milestone Review|Architecture Review|Security Review|Product Intake"
    r"|Technology Stack|Tools and Models|Decision log|Sprint \d+\b.*\bSummary)\s*(?:$|[—:-])", re.IGNORECASE)


def _shipped(relative: Path) -> bool:
    """Whether a workspace-relative path belongs in the product archive, by its name alone."""
    parts = relative.parts
    if not parts or parts[0] in _HARNESS_OWN or any(part in _LEFT_OUT for part in parts):
        return False
    return not relative.name.startswith("tmp-inline-")


def _ignored(root: Path) -> list[str]:
    """What git ignores in the workspace (folders end in `/`): never part of the product a clone of it holds."""
    try:
        from app import ci

        found = ci._git(root, "ls-files", "--others", "--ignored", "--exclude-standard", "--directory", "-z")
    except Exception:  # noqa: BLE001 - nothing known to be ignored
        return []
    if found is None or found.returncode != 0:
        return []
    return [name for name in found.stdout.split("\0") if name]


def _filled_by_a_build(path: Path) -> bool:
    """A folder a build or an install fills, known by the project file beside it."""
    beside = _FILLED_BESIDE.get(path.name)
    if not beside:
        return False
    try:
        return any(sibling.name.endswith(beside) for sibling in path.parent.iterdir())
    except OSError:
        return False


def _compiled(head: bytes) -> bool:
    return head.startswith(_COMPILED)


def _a_compiled_file_in_bin(relative: Path, head: bytes) -> bool:
    """A compiled executable in a `bin/` folder: the build's output, made again from the source."""
    return "bin" in relative.parts[:-1] and _compiled(head)


def files_of(repo_root: str | Path) -> list[str]:
    """The workspace-relative files the product archive holds, in order.

    Left out: the harness's own files, dependency folders and caches, what git ignores, a folder a build or an
    install fills beside its project file, and compiled executables in a `bin/` folder.
    """
    root = Path(repo_root)
    ignored = _ignored(root)
    ignored_files = {name for name in ignored if not name.endswith("/")}
    ignored_folders = tuple(name for name in ignored if name.endswith("/"))
    found: list[str] = []
    for folder, folders, files in os.walk(root):
        here = Path(folder)
        relative_here = here.relative_to(root)
        kept = []
        for name in folders:
            relative, path = relative_here / name, here / name
            if path.is_symlink() or not _shipped(relative) or _filled_by_a_build(path):
                continue
            if ignored_folders and (relative.as_posix() + "/").startswith(ignored_folders):
                continue
            kept.append(name)
        folders[:] = kept
        for name in files:
            relative, path = relative_here / name, here / name
            if path.is_symlink() or not _shipped(relative) or relative.as_posix() in ignored_files:
                continue
            if "bin" in relative.parts[:-1]:
                try:
                    with path.open("rb") as handle:
                        if _compiled(handle.read(4)):
                            continue
                except OSError:
                    continue
            found.append(relative.as_posix())
    return sorted(found)


def is_a_process_document(relative: str, first_line: str = "") -> bool:
    """Whether a workspace file is one of the harness's documents of how the product was built, not of the product.

    Only Markdown under the workspace's `docs/`; never the specification, the criteria or the acceptance tests' own
    page, which describe the product. Known by the name the harness writes it under, the folder it keeps its reviews
    and summaries in, or the first heading its template gives it.
    """
    parts = Path(relative).parts
    if len(parts) < 2 or parts[0] != "docs" or not relative.endswith(".md") or relative.startswith(PROCESS_FOLDER + "/"):
        return False
    if len(parts) > 2 and parts[1] in _PROCESS_FOLDERS:
        return True
    return bool(_PROCESS_NAMES.match(parts[-1]) or (len(parts) == 2 and _PROCESS_HEADINGS.match(first_line.strip())))


def _first_line(data: bytes) -> str:
    for line in data[:2000].decode("utf-8", errors="replace").splitlines():
        if line.strip():
            return line
    return ""


def _criteria(root: Path) -> tuple[int | None, int | None]:
    """The criteria passing and the criteria there are in the last measurement; (None, None) before one."""
    try:
        from app.acceptance import suite

        criteria = (suite.last_result(root) or {}).get("criteria") or {}
    except Exception:  # noqa: BLE001 - the download is offered without the count
        return None, None
    if not criteria:
        return None, None
    return sum(1 for c in criteria.values() if (c or {}).get("status") == "passed"), len(criteria)


def what_it_holds(repo_root: str | Path, *, finished: bool) -> dict[str, Any]:
    """Which product the download holds and what it was measured to pass (deep review 2026-11-18, F4a).

    A finished run's download is the product as it stands. A run that did not finish (stopped, cancelled) offers its
    best attempt: the product as it stands when that is its best, or the files of the best commit when the record of
    the best attempt (`app.graph.best_attempt`) passed more acceptance tests than the product does now. `version` is
    "latest" or "best"; `commit` names the best commit only when the download is built from it.
    """
    root = Path(repo_root)
    passed, total = _criteria(root)
    said: dict[str, Any] = {"version": "latest", "commit": "", "criteria_passed": passed, "criteria_total": total,
                            "tests_passed": None, "tests_total": None}
    if finished:
        return said
    said["version"] = "best"
    try:
        from app.graph import best_attempt

        best = best_attempt.better_than_now(root)
    except Exception:  # noqa: BLE001 - the product as it stands
        best = {}
    if best:
        # The record counts acceptance tests, not criteria: the criteria of that commit were never kept.
        said.update(commit=str(best["commit"]), criteria_passed=None, criteria_total=None,
                    tests_passed=int(best.get("passed") or 0), tests_total=int(best.get("tests") or 0) or None)
    return said


def _files_at(root: Path, commit: str) -> dict[str, bytes] | None:
    """The product's files as they were at `commit`; None when git cannot give them."""
    from app import ci

    with tempfile.TemporaryDirectory(prefix="best-attempt-") as scratch:
        tar_path = Path(scratch) / "best.tar"
        made = ci._git(root, "archive", "--format=tar", "-o", str(tar_path), commit)
        if made is None or made.returncode != 0 or not tar_path.is_file():
            return None
        found: dict[str, bytes] = {}
        used = 0
        with tarfile.open(tar_path) as tar:
            members = [m for m in tar.getmembers() if m.isfile()]
            in_folder: dict[Path, list[str]] = {}
            for m in members:
                in_folder.setdefault(Path(m.name).parent, []).append(Path(m.name).name)

            def filled(relative: Path) -> bool:
                for depth, part in enumerate(relative.parts[:-1]):
                    beside = _FILLED_BESIDE.get(part)
                    if beside and any(name.endswith(beside) for name in in_folder.get(Path(*relative.parts[:depth]), ())):
                        return True
                return False

            for member in members:
                relative = Path(member.name)
                if not _shipped(relative) or filled(relative):
                    continue
                if used + member.size > MOST_BYTES:
                    break
                handle = tar.extractfile(member)
                if handle is None:
                    continue
                data = handle.read()
                if _a_compiled_file_in_bin(relative, data[:4]):
                    continue
                found[member.name] = data
                used += member.size
    return found


def _workspace_files(root: Path) -> dict[str, bytes]:
    found: dict[str, bytes] = {}
    used = 0
    for relative in files_of(root):
        size = (root / relative).stat().st_size
        if used + size > MOST_BYTES:
            break
        found[relative] = (root / relative).read_bytes()
        used += size
    return found


def _moved_links(text: str, moved: dict[str, str]) -> str:
    """A document's mentions of a moved process document, pointed at where it now is."""
    names = "|".join(re.escape(old) for old in sorted(moved, key=len, reverse=True))
    return re.sub(rf"(?<![\w/.-])({names})(?![\w/-])", lambda m: moved[m.group(1)], text)


def how_to_run(repo_root: str | Path) -> list[str]:
    """The commands that install, test and start the product, from the stack it was built on; [] when unknown."""
    root = Path(repo_root)
    lines: list[str] = []
    try:
        from app.stacks import contract
        from app.tools.repository import pinned_project_directory

        project = pinned_project_directory(root) or ""
        found = contract.the_pack(root)
        where = root / project if project else root
        if project:
            lines.append(f"cd {project}")
        if found:
            pack = found[0]
            lines += [shlex.join(step) for step in pack.install or ()]
            if pack.unit_test:
                lines.append(shlex.join(pack.unit_test))
        if (where / "start.sh").is_file():
            lines.append("sh start.sh")
    except Exception:  # noqa: BLE001 - the archive without the commands
        return []
    return lines


def build(repo_root: str | Path, run_id: str, *, at_commit: str = "") -> bytes:
    """The product as a zip archive under a folder named for the run, with `HANDOVER.md` at its top.

    With `at_commit` (a best attempt better than the product now), the files are those of that commit, without the
    git history; if git cannot give them, the product as it stands. The harness's process documents go under
    `docs/process/`, and every mention of one in the product's Markdown goes with it.
    """
    root = Path(repo_root)
    files = _files_at(root, at_commit) if at_commit else None
    from_the_best = files is not None
    if files is None:
        files = _workspace_files(root)
    moved = {relative: f"{PROCESS_FOLDER}/{relative.removeprefix('docs/')}" for relative, data in files.items()
             if is_a_process_document(relative, _first_line(data) if relative.endswith(".md") else "")}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for relative, data in files.items():
            if moved and relative.endswith(".md"):
                data = _moved_links(data.decode("utf-8", errors="replace"), moved).encode("utf-8")
            archive.writestr(f"{run_id}/{moved.get(relative, relative)}", data)
        steps = how_to_run(root)
        try:
            from app.handover.handover_document import write_for

            page = write_for(root, run_id=run_id, steps=steps, moved_documents=bool(moved))
        except Exception:  # noqa: BLE001 - the archive without its handover page, never without the product
            page = ("# Handover\n\n## How to run, test and deploy it\n\nFrom this folder:\n\n```sh\n"
                    + "\n".join(steps) + "\n```\n") if steps else ""
        if page and from_the_best:
            title, _, rest = page.partition("\n")
            page = (f"{title}\n\n> These are the product's files at its best attempt (commit `{at_commit}`), not as "
                    f"the run left them; the git history is not included.\n{rest}")
        if page:
            place = "HANDOVER.md" if "HANDOVER.md" not in files else f"{PROCESS_FOLDER}/HANDOVER.md"
            archive.writestr(f"{run_id}/{place}", page)
    return buffer.getvalue()


__all__ = ["MOST_BYTES", "PROCESS_FOLDER", "build", "files_of", "how_to_run", "is_a_process_document", "what_it_holds"]
