"""A fix reverted for breaking tests, whose own defect's tests passed, is kept and measured a second time (behind `KEPT_FIX_CANDIDATES`).

Measured per sprint attempt: 4 to 6 fixes were reverted, and the defect was dispatched to a fixer again, which
wrote its change from nothing. A reverted fix is thrown away whole (`engineering.after_a_fix` resets the workspace),
including a fix that did what the defect asked and broke something else - something the next attempt's
circumstances (a repaired test, another fix landed) may no longer break.

With the switch on, a fix reverted for breaking tests is first checked against its own defect's tests
(`_the_defect_s_tests_pass`) while it is still in the workspace. When they pass, it is kept as a candidate for the
defect: the files it changed, each as a patch, and the size of the change (`keep`). At the defect's next attempt,
before a fixer or a rewrite is sent, the candidates are replayed (`replayed`):

- smallest diff first: the candidate that changed the fewest lines is applied first;
- composed across attempts: a further candidate is applied as well when it touches none of the files already
  applied, so a defect whose fix spans several files can be put together from attempts that each got one part;
- the result is measured as any fix is - the whole suite, reverted again when it breaks tests - which is the second
  measurement, at the price of a measurement and no model call;
- a candidate is replayed once: nothing is kept from a replay that is reverted again, and a patch that no longer
  applies to the workspace is dropped.

The candidates live in `.harness/kept_candidates.json` of the workspace, so a restarted worker has them.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Callable

from app.switches import is_on

logger = logging.getLogger(__name__)

#: `KEPT_FIX_CANDIDATES` set to on or off overrides this.
ON_BY_DEFAULT = False

STORE = ".harness/kept_candidates.json"
#: Candidates kept for one defect (the largest are dropped first), files in one, and characters of one file's patch.
MOST_KEPT = 4
MOST_FILES = 8
MOST_PATCH_CHARACTERS = 60_000
#: Paths a candidate never carries: the harness's own, and what installs put in the workspace.
_NOT_A_CHANGE = (".harness/", "node_modules/", ".agent-home/")


def enabled() -> bool:
    return is_on("KEPT_FIX_CANDIDATES", ON_BY_DEFAULT)


def defect_key(defect: Any) -> str:
    """One defect's name in the store: its description, whitespace and case set aside."""
    text = " ".join(str(getattr(defect, "description", "") or "").lower().split())
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]


def _read(root: str | Path) -> dict[str, Any]:
    try:
        found = json.loads((Path(root) / STORE).read_text(encoding="utf-8"))
        return found if isinstance(found, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(root: str | Path, store: dict[str, Any]) -> None:
    path = Path(root) / STORE
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(store, indent=1) + "\n", encoding="utf-8")
    except OSError:
        logger.debug("Could not write the kept candidates", exc_info=True)


def _version_control(root: str | Path, *args: str) -> Any:
    from app import ci

    return ci._git(root, *args)


def _lines_changed(patch: str) -> int:
    return sum(1 for line in patch.splitlines() if line[:1] in "+-" and not line.startswith(("+++", "---")))


def _patches_since(root: str | Path, base: str) -> dict[str, str]:
    """{file: its patch from `base` to the workspace's last commit}; {} when a change cannot be kept as a patch."""
    from app import ci

    paths = [p for p in ci.changed_since(root, base) if not p.startswith(_NOT_A_CHANGE)]
    if not paths or len(paths) > MOST_FILES:
        return {}
    patches: dict[str, str] = {}
    for path in paths:
        done = _version_control(root, "diff", "--no-color", base, "HEAD", "--", path)
        text = done.stdout if done is not None and done.returncode == 0 else ""
        if not text.strip() or "GIT binary patch" in text or "Binary files" in text or len(text) > MOST_PATCH_CHARACTERS:
            return {}
        patches[path] = text
    return patches


def keep(
    root: str | Path, base: str, defect: Any, stage_name: str, passes: Callable[[], bool | None], broke: list[str],
) -> bool:
    """Keep the fix in the workspace, about to be reverted, as a candidate for `defect` when its own tests pass.

    Called while the reverted fix is still in the workspace. Never raises; True when a candidate was kept.
    """
    if not enabled() or not base:
        return False
    try:
        from app import ci

        store = _read(root)
        mine = store.get(defect_key(defect)) or {"candidates": [], "spent": []}
        if mine.get("replayed_stage") == stage_name:
            return False  # a replay reverted again is not kept again
        ci.commit(root, f"{stage_name} as written, kept as a candidate")
        patches = _patches_since(root, base)
        if not patches or passes() is not True:
            return False
        text = "".join(patches[p] for p in sorted(patches))
        digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]
        if digest in mine["spent"] or any(c.get("digest") == digest for c in mine["candidates"]):
            return False
        mine["candidates"].append({
            "digest": digest, "stage": stage_name, "files": patches,
            "size": sum(_lines_changed(t) for t in patches.values()), "broke": [str(item)[:200] for item in broke[:3]],
        })
        mine["candidates"] = sorted(mine["candidates"], key=lambda c: c["size"])[:MOST_KEPT]
        store[defect_key(defect)] = mine
        _write(root, store)
        logger.warning("Kept %s as a candidate for its defect: its tests pass, and it broke %d test(s) that passed before",
                       stage_name, len(broke))
        return True
    except Exception:  # noqa: BLE001 - the fix is reverted as before
        logger.warning("Could not keep a reverted fix as a candidate", exc_info=True)
        return False


def _applies(root: str | Path, patch: str, *, check_only: bool) -> bool:
    file = Path(root) / ".harness" / "candidate.patch"
    try:
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(patch, encoding="utf-8")
        done = _version_control(root, "apply", "--whitespace=nowarn", *(("--check",) if check_only else ()), str(file))
        return done is not None and done.returncode == 0
    except OSError:
        return False
    finally:
        file.unlink(missing_ok=True)


def replayed(root: str | Path, defect: Any, stage_name: str) -> Any | None:
    """The fix stage's answer for `defect` put together from its kept candidates and applied; None when there is none.

    Smallest diff first; a further candidate is applied when it touches no file already applied. Each candidate
    applied is spent - replayed once - and one that no longer applies is dropped. The caller measures the result.
    """
    if not enabled():
        return None
    try:
        store = _read(root)
        mine = store.get(defect_key(defect))
        if not mine or not mine.get("candidates"):
            return None
        applied_files: list[str] = []
        used: list[str] = []
        remaining = []
        for candidate in sorted(mine["candidates"], key=lambda c: c.get("size", 0)):
            files = candidate.get("files") or {}
            if set(files) & set(applied_files):
                remaining.append(candidate)
                continue
            # One that does not apply is dropped: the workspace has moved on from what it was written for.
            if all(_applies(root, patch, check_only=True) for patch in files.values()) and all(
                    _applies(root, patch, check_only=False) for patch in files.values()):
                applied_files.extend(files)
                used.append(candidate["stage"])
                mine["spent"].append(candidate["digest"])
        mine["candidates"] = remaining
        if applied_files:
            mine["replayed_stage"] = stage_name
        _write(root, store)
        if not applied_files:
            return None
        from app.agents.specialists import SpecialistOutput

        logger.warning("Replaying %d kept candidate(s) for a defect before a fixer is sent: %s", len(used), ", ".join(used))
        return SpecialistOutput(
            changed_files=applied_files,
            tests=["the defect's own tests passed when this change was first made; the whole suite measures it again"],
            decisions=[f"Applied the kept change(s) of {', '.join(used)}, smallest diff first, for a second measurement."],
        )
    except Exception:  # noqa: BLE001 - a fixer is sent as before
        logger.warning("Could not replay the kept candidates", exc_info=True)
        return None


__all__ = ["MOST_KEPT", "ON_BY_DEFAULT", "defect_key", "enabled", "keep", "replayed"]
