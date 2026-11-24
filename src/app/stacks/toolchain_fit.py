"""After an install resolves, each resolved package's runtime need is compared with the toolchain here (HK.2, LF.1293).

Measured: a Rust run's crates resolved to `icu_collections` 2.4, which needs rustc 1.88, under the image's 1.85; the
build failed round after round and a fixer pinned crates by hand before anything named the cause (LF.1277 answered it
for Rust alone, with cargo's resolver setting). A C# run pinned a release of a package that targets net10.0 only under
.NET 8, and every restore failed NU1202 while a web lookup and two rewrites left it so (LF.1248 answered the lookup).
Both were facts the lock file, the installed packages and the registry state exactly.

So when a command changes a lock file - or any install runs - the packages it resolved are read
(`app.analysis.resolved_packages`, one reader per language in the language table), each one's stated need is read
from the project's own files or else from its registry for that release (direct dependencies first, at most
`MOST_REGISTRY_READS`), and each that this toolchain does not meet is a mismatch, named with the newest release that
fits (`app.tools.release_fit`). The mismatches are said at once in the install's own result, kept in the stack facts
(`app.stacks.stack_facts`), and given as a stated cause to the first defect a test round raises after them
(`with_fit_causes`) - the first minute, not after rounds.

Always on as part of the stack facts (`STACK_FACTS`, a built-in fix). A project whose resolved packages all fit is
told nothing.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: Resolved releases whose need is asked of their registry per check, direct dependencies first.
MOST_REGISTRY_READS = 40
#: Registry reads at once.
AT_ONCE = 8
#: Mismatches named in one note.
MOST_NAMED = 6

#: How a mismatch is introduced in an install's result and a defect's actual behaviour; never added twice.
FIT_CAUSE = "Toolchain fit:"


def lock_state(directory: str | Path) -> tuple:
    """What the lock files and resolution records in `directory` are now (name, size, modification), to tell
    whether a command resolved again."""
    from app.analysis.resolved_packages import RESOLUTION_FILES
    from app.stacks.languages import LOCKFILES

    directory = Path(directory)
    state = []
    candidates = [directory / name for name in LOCKFILES]
    candidates += [project.parent / relative for project in directory.glob("*.csproj") for relative in RESOLUTION_FILES]
    for path in candidates:
        try:
            stat = path.stat()
        except OSError:
            continue
        state.append((str(path), stat.st_size, stat.st_mtime_ns))
    return tuple(sorted(state))


def check(root: str | Path, directory: str | Path) -> list[dict[str, Any]]:
    """Each resolved package in `directory` whose stated runtime need this toolchain does not meet, with the newest
    release that fits; [] when all fit or nothing could be read. Never raises."""
    from app.analysis.resolved_packages import resolved_in
    from app.tools import release_fit

    try:
        resolved = resolved_in(directory, root)
        if not resolved:
            return []
        here = {e: release_fit.toolchain(e, root) for e in {r.ecosystem for r in resolved}}
        here = {e: banner for e, banner in here.items() if release_fit.numbers(banner)}
        unknown = sorted((r for r in resolved if r.needs is None and r.ecosystem in here), key=lambda r: not r.direct)
        asked = unknown[:MOST_REGISTRY_READS]
        with ThreadPoolExecutor(max_workers=AT_ONCE) as pool:
            read = dict(zip(asked, pool.map(lambda r: release_fit.needs_of(r.ecosystem, r.name, r.version), asked)))
        mismatches = []
        for entry in resolved:
            if entry.ecosystem not in here:
                continue
            needs = entry.needs if entry.needs is not None else (read[entry].needs if entry in read else None)
            if not needs or release_fit.fits(entry.ecosystem, needs, here[entry.ecosystem]):
                continue
            mismatches.append({"ecosystem": entry.ecosystem, "package": entry.name, "version": entry.version,
                               "needs": f"{release_fit.RUNTIME_OF.get(entry.ecosystem, entry.ecosystem)} {needs}",
                               "toolchain": here[entry.ecosystem], "source": entry.source, "direct": entry.direct})
        mismatches.sort(key=lambda m: not m["direct"])
        with ThreadPoolExecutor(max_workers=AT_ONCE) as pool:
            fitting = list(pool.map(lambda m: release_fit.newest_that_fits(m["ecosystem"], m["package"],
                                                                           m["toolchain"]), mismatches[:MOST_NAMED]))
        for mismatch, found in zip(mismatches, fitting):
            if found.get("version") and found["version"] != mismatch["version"]:
                mismatch["fits"] = found["version"]
        return mismatches
    except Exception:  # noqa: BLE001 - no finding rather than a crash
        logger.debug("Could not check the resolved packages against the toolchain", exc_info=True)
        return []


def described(mismatches: list[dict[str, Any]]) -> str:
    """The mismatches as one cause a stage or a fixer reads: each package, what it needs, what is here, what fits."""
    if not mismatches:
        return ""
    lines = []
    for m in mismatches[:MOST_NAMED]:
        if m.get("said"):
            # Said whole by the check that found it: a release line the brief asks for (`stated_releases`, LF.1311).
            lines.append(f"- {m['said']}")
            continue
        line = (f"- `{m['package']}` {m['version']} ({m['source']}) needs {m['needs']}; this environment has "
                f"{m['toolchain']}.")
        line += (f" {m['fits']} is the newest release that fits: pin it, or a release of the package that brings it"
                 " which allows it." if m.get("fits") else " No release that fits was found: use another package.")
        lines.append(line)
    more = len(mismatches) - MOST_NAMED
    return (f"{FIT_CAUSE} what the install resolved needs a newer toolchain than this environment has, so it will "
            "not build or run here whatever the code says:\n" + "\n".join(lines)
            + (f"\n- and {more} more" if more > 0 else ""))


def after_resolving(root: str | Path, directory: str | Path) -> str:
    """Check what an install in `directory` resolved, keep it in the stack facts, and return the note for the
    install's result ("" when everything fits or the facts are off). Never raises."""
    from app.stacks import stack_facts

    if not stack_facts.enabled():
        return ""
    try:
        root, directory = Path(root), Path(directory)
        mismatches = check(root, directory)
        where = str(directory.relative_to(root)) if directory != root and directory.is_relative_to(root) else "."
        stack_facts.write(root, mismatches={where: mismatches})
        # The advisories and support dates of what it resolved (HK.6, `app.stacks.advisories`).
        from app.stacks import advisories

        advisories.after_resolving(root, directory)
        return described(mismatches)
    except Exception:  # noqa: BLE001 - the install's result as it was
        logger.debug("Could not check the toolchain fit after an install", exc_info=True)
        return ""


def before_a_command(root: str | Path, working_directory: str | None) -> tuple[Path, tuple] | None:
    """(the folder a command runs in, its lock files now), for `after_a_command`; None when the facts are off."""
    from app.stacks import stack_facts

    if not stack_facts.enabled():
        return None
    try:
        directory = Path(root) / str(working_directory or "").strip().strip("/")
        return directory, lock_state(directory)
    except Exception:  # noqa: BLE001 - not checked
        return None


def after_a_command(root: str | Path, before: tuple[Path, tuple] | None, category: str) -> str:
    """The fit note for a command's result: checked when it was an install or changed a lock file; "" otherwise."""
    if before is None:
        return ""
    directory, locks = before
    if category != "install" and lock_state(directory) == locks:
        return ""
    return after_resolving(root, directory)


def with_fit_causes(root: str | Path | None, defects: list[Any]) -> list[Any]:
    """`defects`, the mismatches the stack facts hold given as a stated cause: to each defect naming a mismatched
    package, else to the first. As they were when there are none. Never raises."""
    from app.stacks import stack_facts

    try:
        if not defects or not stack_facts.enabled():
            return defects
        mismatches = [m for found in (stack_facts.read(root).get("mismatches") or {}).values()
                      for m in found or [] if isinstance(m, dict)]
        cause = described(mismatches)
        if not cause:
            return defects

        def text(defect: Any) -> str:
            return f"{getattr(defect, 'description', '')} {getattr(defect, 'actual_behavior', '')}".lower()

        naming = [i for i, d in enumerate(defects) if any(str(m["package"]).lower() in text(d) for m in mismatches)]
        out = list(defects)
        for index in naming or [0]:
            defect = out[index]
            actual = str(getattr(defect, "actual_behavior", "") or "")
            if FIT_CAUSE in actual:
                continue
            try:
                out[index] = defect.model_copy(update={"actual_behavior": (actual + "\n" + cause).strip()})
            except Exception:  # noqa: BLE001 - the defect as raised
                continue
        return out
    except Exception:  # noqa: BLE001 - the defects as raised
        logger.debug("Could not add the toolchain fit to the defects", exc_info=True)
        return defects


__all__ = ["FIT_CAUSE", "MOST_REGISTRY_READS", "after_resolving", "check", "described", "lock_state",
           "with_fit_causes"]
