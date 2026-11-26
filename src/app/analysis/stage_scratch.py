"""A fix or testing stage's scratch, known by what the file is rather than what it is called (LF.1533).

`file_kinds.SCRATCH_NAME` grew one name at a time - tmp, temp, scratch, debug,
test2, .probe, diag - each added after a run had already paid for the one it
missed. Measured on a page product: three fixers left `diag.js`, `diag.mjs`,
`diag2.mjs` and `diag-filter.js` at the project root; the cross-file check
raised `diag.js`'s `require` under `"type": "module"` as the product's defect,
and it took a fix round. The next probe will have a name no list knows.

So the rule here is structural. A file is a stage's scratch when all of these
hold:

- a fix stage, a test round or a testing stage created it, and no other kind of
  stage has changed it since (the project memory's `created_by` and
  `changed_by`; a file a command created is recorded there too, see
  `record_what_a_command_created`);
- it sits in the project's top folder or the workspace's, where every measured
  probe was written. A deeper folder is where a framework finds files by
  convention - routes, migrations, controllers - which nothing imports by name
  and which are the product all the same, so the rule leaves them to the names;
- it is code (`file_kinds.BEHAVIOUR_SUFFIXES`) and the application by kind: not
  a test, configuration, document or build output (`file_kinds.classify_file`),
  and not a file a tool loads by its name alone - a configuration, a package's
  own file, a runtime's default entry point (`_FOUND_BY_NAME`);
- no plan names it: not the work orders' file table, the specification or the
  sprint plan;
- no other file names it - no manifest, configuration, test, entry point or
  page carries its file name or its name without the extension - and the code
  graph (`analysis.project_graph`) shows nothing importing it, using its
  definitions or reaching it as a route. A file whose language the graph does
  not follow is never scratch by this rule.

A file the product comes to use stops being scratch the moment something names
or imports it, so the sweep, which reads this afresh, never removes it. Names
stay as the fallback (`file_kinds.is_scratch`).
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

logger = logging.getLogger(__name__)

#: The stages whose new files may be scratch: a fix (`defect_fix_*`, `fix`), a test round, a testing work order.
SCRATCH_MAKING_STAGES = ("defect_fix", "test_round_", "specialist_testing_")

#: The specification and the sprint plan, workspace-relative: a file either names is planned.
_PLANS = ("docs/technical_specification.md", "docs/sprint_plan.md")

#: Directories never read for a mention: installed and generated content, runner output, and the workspace's
#: own `docs/`, where the run's stage summaries name the probes they wrote.
_NOT_READ = frozenset({"node_modules", "test-results", "playwright-report", "blob-report", "coverage", "htmlcov"})

#: A file a tool loads by its name alone, which nothing else need name: configuration (`postcss.config.cjs`,
#: `gunicorn.conf.py`, `.eslintrc.js`, `gulpfile.js`), a package's own files (`__init__.py`) and the entry points a
#: runtime looks for (`index.js`, `main.go`). Never a probe by this rule, whoever created it.
_FOUND_BY_NAME = re.compile(
    r"(?:^|[._-])conf(?:ig)?(?:[._-]|$)|rc\.[^.]+$|file\.[^.]+$|^__\w+__\.|^(?:index|main|app|server|mod|lib)\.",
    re.IGNORECASE,
)

#: The largest file read for a mention of a probe's name.
_MOST_BYTES_READ = 400_000

#: Seconds an answer is reused while the project memory and the plans are unchanged.
_HELD_FOR_SECONDS = 30.0

_LOCK = threading.Lock()
_HELD: dict[str, tuple[tuple[Any, ...], float, frozenset[str]]] = {}
#: (workspace, stage) pairs already told, in a write's reply, that a new file reads as a probe.
_TOLD: set[tuple[str, str]] = set()


def makes_scratch(stage: str) -> bool:
    """Whether a stage of this name is one whose new files may be its scratch."""
    stage = str(stage or "")
    return stage == "fix" or stage.startswith(SCRATCH_MAKING_STAGES)


def _pinned(root: Path) -> str:
    try:
        from app.tools.repository import pinned_project_directory

        return (pinned_project_directory(root) or "").strip().strip("/")
    except Exception:  # noqa: BLE001
        return ""


def _at_the_top(path: str, pinned: str) -> bool:
    """Whether a workspace-relative path sits in the workspace's top folder or the project's."""
    parent = PurePosixPath(path).parent.as_posix()
    return parent in {".", ""} or bool(pinned) and parent == pinned


def _memory(root: Path) -> dict[str, dict]:
    try:
        from app.analysis.project_memory import MEMORY_FILE

        held = json.loads((root / MEMORY_FILE).read_text(encoding="utf-8"))
        return held if isinstance(held, dict) else {}
    except Exception:  # noqa: BLE001 - no memory, no stage's file known
        return {}


def _planned_text(root: Path) -> tuple[set[str], str]:
    """The work orders' files, and the plans' text, to look a name up in."""
    files: set[str] = set()
    try:
        from app.tools.repository import WORK_ORDER_FILES

        table = json.loads((root / WORK_ORDER_FILES).read_text(encoding="utf-8"))
        files = {str(path).strip().lstrip("./") for path in (table or {})}
    except Exception:  # noqa: BLE001 - no table, nothing planned by it
        pass
    texts = []
    for plan in _PLANS:
        try:
            texts.append((root / plan).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return files, "\n".join(texts)


def _named_in(text: str, words: Iterable[str]) -> bool:
    return any(re.search(rf"(?<![\w-]){re.escape(word)}(?![\w-])", text) for word in words if word)


def _its_names(path: str) -> tuple[str, str]:
    """A file's name and its name without the extension: an import names one or the other."""
    name = PurePosixPath(path).name
    return name, name.split(".", 1)[0]


def _candidates(root: Path, pinned: str) -> list[str]:
    """The files a scratch-making stage created at the top that are code, the application, and in no plan."""
    from app.analysis.file_kinds import BEHAVIOUR_SUFFIXES, classify_file

    planned_files, plans = _planned_text(root)
    found = []
    for path, entry in _memory(root).items():
        if not isinstance(entry, dict):
            continue
        created, changed = str(entry.get("created_by") or ""), str(entry.get("changed_by") or "")
        if not makes_scratch(created) or (changed and not makes_scratch(changed)):
            continue
        if not _at_the_top(path, pinned) or PurePosixPath(path).suffix.lower() not in BEHAVIOUR_SUFFIXES:
            continue
        if _FOUND_BY_NAME.search(PurePosixPath(path).name):
            continue
        if classify_file(path) != "application" or not (root / path).is_file():
            continue
        inside = path[len(pinned) + 1:] if pinned and path.startswith(pinned + "/") else path
        if path in planned_files or inside in planned_files or _named_in(plans, (inside, PurePosixPath(path).name)):
            continue
        found.append(path)
    return found


def _others(root: Path, candidates: set[str]) -> dict[str, str]:
    """Every other readable file of the workspace that may name a probe, by workspace-relative path, with its text."""
    from app.analysis.file_kinds import SCRATCH_NAME
    from app.analysis.walk import files_under
    from app.tools.repository import IGNORED_DIRECTORIES

    texts: dict[str, str] = {}
    for path in files_under(root, {*IGNORED_DIRECTORIES, *_NOT_READ}, skip_hidden=True):
        relative = path.relative_to(root).as_posix()
        # Not the run's own records (the workspace's `docs/`, its dot files), and not a probe named as one: a
        # `tmp-` file that runs a probe does not make the probe the product.
        if relative in candidates or relative.startswith(("docs/", ".")) or SCRATCH_NAME.search(path.name):
            continue
        try:
            if path.stat().st_size <= _MOST_BYTES_READ:
                texts[relative] = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
    return texts


def _the_graph_says_nothing_uses(root: Path, path: str, pinned: str, graph: dict[str, Any]) -> bool:
    """Whether the code graph holds this file, follows its language, and shows nothing reaching it."""
    if not pinned or not path.startswith(pinned + "/"):
        # Outside the product's tree, where the graph does not look: nothing of the product is there to import it.
        return True
    node = graph.get(path)
    if not isinstance(node, dict):
        return False
    from app.analysis.parsed_definitions import loads, row_for
    from app.analysis.reachability import FAMILIES, family_of

    row = row_for(path)
    if family_of(path) not in FAMILIES and not (row and row[1].resolver and loads(path)):
        return False
    return not (node.get("imported_by") or node.get("used_by") or node.get("routes"))


def _worked_out(root: Path) -> frozenset[str]:
    pinned = _pinned(root)
    candidates = set(_candidates(root, pinned))
    if not candidates:
        return frozenset()
    texts = _others(root, candidates)
    # A probe another kept file names is kept, and so is every probe that one names: until nothing changes.
    while True:
        named = {c for c in candidates if any(_named_in(text, _its_names(c)) for text in texts.values())}
        if not named:
            break
        candidates -= named
        for path in named:
            try:
                texts[path] = (root / path).read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
    if not candidates:
        return frozenset()
    from app.analysis import project_graph

    graph = project_graph.build(root) if pinned else {}
    return frozenset(c for c in candidates if _the_graph_says_nothing_uses(root, c, pinned, graph))


def _signature(root: Path) -> tuple[Any, ...]:
    from app.analysis.project_memory import MEMORY_FILE
    from app.tools.repository import WORK_ORDER_FILES

    seen = []
    for name in (MEMORY_FILE, WORK_ORDER_FILES, *_PLANS):
        try:
            stat = (root / name).stat()
            seen.append((stat.st_mtime_ns, stat.st_size))
        except OSError:
            seen.append(None)
    return tuple(seen)


def found(root: str | Path, *, fresh: bool = False) -> frozenset[str]:
    """The workspace-relative paths that are a stage's scratch by the structural rule. Never raises.

    `fresh` works it out again whatever was held: for the sweep, which deletes.
    """
    try:
        root = Path(root).resolve()
        if not root.is_dir():
            return frozenset()
        signature = _signature(root)
        with _LOCK:
            held = _HELD.get(str(root))
        if not fresh and held and held[0] == signature and time.monotonic() - held[1] < _HELD_FOR_SECONDS:
            return held[2]
        answer = _worked_out(root)
        with _LOCK:
            _HELD[str(root)] = (signature, time.monotonic(), answer)
        return answer
    except Exception:  # noqa: BLE001 - when in doubt a file is the product's
        logger.debug("Could not work out the stages' scratch files", exc_info=True)
        return frozenset()


def _as_workspace_relative(root: Path, path: str) -> list[str]:
    """The spellings a caller's path may mean: workspace-relative, or relative to the project."""
    shown = str(path or "").replace("\\", "/").strip()
    try:
        if Path(shown).is_absolute():
            shown = Path(shown).resolve().relative_to(root).as_posix()
    except (OSError, ValueError):
        return []
    shown = shown.removeprefix("./").lstrip("/")
    pinned = _pinned(root)
    return [shown, f"{pinned}/{shown}"] if pinned and not shown.startswith(pinned + "/") else [shown]


def is_a_stage_s_scratch(root: str | Path, path: str) -> bool:
    """Whether this file is a fix or testing stage's scratch by the structural rule. Never raises."""
    try:
        resolved = Path(root).resolve()
        scratch = found(resolved)
        return bool(scratch) and any(spelling in scratch for spelling in _as_workspace_relative(resolved, path))
    except Exception:  # noqa: BLE001
        return False


def files_before_a_command(root: str | Path, stage: str) -> set[str] | None:
    """The files in the workspace's top folder and the project's, before a scratch-making stage's command; else None.

    Only the top: that is the only place the structural rule looks, so a deeper walk would buy nothing.
    """
    if not makes_scratch(stage):
        return None
    try:
        root = Path(root)
        pinned = _pinned(root)
        here = {p.name for p in root.iterdir() if p.is_file()}
        if pinned and (root / pinned).is_dir():
            here |= {f"{pinned}/{p.name}" for p in (root / pinned).iterdir() if p.is_file()}
        return here
    except OSError:
        return None


def record_what_a_command_created(root: str | Path, before: set[str] | None, outcome: Any, stage: str) -> None:
    """Record, as `stage`'s, each code file at the top that a command created. Never raises.

    The write tools record what they write (`project_memory.record`); a command that wrote a file - a probe saved by
    `cat`, a script that writes a script - did not, so no one was known to have created it.
    """
    if before is None or not isinstance(outcome, dict):
        return
    try:
        from app.analysis import project_memory
        from app.analysis.file_kinds import BEHAVIOUR_SUFFIXES, classify_file

        root = Path(root)
        pinned = _pinned(root)
        for path in outcome.get("files_changed") or ():
            path = str(path)
            if path in before or path.startswith("...") or not _at_the_top(path, pinned):
                continue
            if PurePosixPath(path).suffix.lower() not in BEHAVIOUR_SUFFIXES or classify_file(path) != "application":
                continue
            if project_memory.who_created(root, path) or not (root / path).is_file():
                continue
            project_memory.record(root, path, stage)
    except Exception:  # noqa: BLE001 - bookkeeping must never fail a command
        logger.debug("Could not record the files a command created", exc_info=True)


def note_for_a_write(root: str | Path, relative_path: str, created: bool, stage: str) -> str:
    """What a write's reply says, once per stage, when it created a file that reads as its scratch; else ""."""
    try:
        if not created or not makes_scratch(stage):
            return ""
        from app.analysis.file_kinds import SCRATCH_NAME

        resolved = Path(root).resolve()
        shown = str(relative_path).replace("\\", "/")
        if SCRATCH_NAME.search(PurePosixPath(shown).name) or (str(resolved), stage) in _TOLD:
            return ""
        if shown not in found(resolved, fresh=True):
            return ""
        with _LOCK:
            _TOLD.add((str(resolved), stage))
        return (
            f"`{shown}` is a new file outside the plan that nothing in the product imports or names, so it reads "
            "as a throwaway probe. Name a throwaway probe `tmp-<what it checks>`, or delete it before you answer: "
            "left where it is, it is checked and reviewed as the product. If the product is to use it, import it "
            "where it is needed."
        )
    except Exception:  # noqa: BLE001 - a note never fails a write
        return ""
