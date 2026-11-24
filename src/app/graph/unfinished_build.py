"""An unfinished build goes back to its builders, not to fixers (LF.1299).

Measured on a medium run in thorough delivery: sprint 2's builders handed over
unfinished work - one wrote a single file, another made one edit - and the
first test round raised eleven defects, most of them saying the feature was
not built ("No ..._service.py exists", "POST .../assign returns 404", "the
router's endpoints are all stubs returning empty results"). The first fix
stage, bounded for a fault and not for building a feature, read seventy times,
edited one file four times and left its defect open; the run recovered only
after three exhausted rounds, by planning the whole sprint again.

Fast delivery already holds its drafts to this (`drafting._promised_but_not_written`:
a work order is done when what it promised is there). Here the same rule is
applied to the agent builders of thorough delivery, at two points, each once a
sprint attempt (the lead's next plan starts them again):

1. `after_the_build`: when every builder of the sprint has finished and before
   CI and the test round, each work order is checked against what it promised -
   its files exist and are not the scaffold's stub or a file whose every answer
   is an empty value, the names its interfaces promise are defined somewhere in
   the product, and the contract routes it promised are served by some code. An
   order not done goes back to its builder once, on its normal budget, told what
   is missing.
2. `at_a_round`: when half or more of a test round's defects say the work is not
   built - a 404 on a contract route the sprint owns that no code serves, a file a
   work order named that does not exist, a stub a work order's file still is - and
   the sprint's work orders cover them, those defects go to the builder of the
   order (closed as `superseded`; the next round measures them again) instead of
   to the fix loop; the rest stay open for the fix loop after the next round.

Both are recorded in the defect ledger (`loop.sh effects`). Nothing here names
a language, a framework or a kind of product.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Sequence

logger = logging.getLogger(__name__)

#: `builders_sent_back` entries: which of the two checks has acted in this attempt.
AFTER_THE_BUILD = "after the build"
AFTER_A_ROUND = "after a test round"

#: What a ledger record's detail opens with (`loop.sh effects`).
SENT_BACK_SAID = "Sent back to its builder before the test round: the work order is not finished"
ROUTED_SAID = "Not built: sent to the builder of its work order, not to a fixer"
#: The ledger events.
SENT_BACK_EVENT = "sent back to its builder"
ROUTED_EVENT = "sent to its builder"

#: A test round's defects that say "not built", as a share of all it raised, at or above which they go to builders.
NOT_BUILT_SHARE = 0.5

#: How much of the product is read to answer "is it built": files and bytes a file.
MOST_FILES = 3000
MOST_BYTES = 300_000

_SKIPPED_FOLDERS = ("node_modules", ".git", ".harness", ".venv", "venv", "__pycache__", "dist", "build", "target",
                    "vendor", "coverage")

#: One answer a handler gives: what follows `return`, or what a response call is handed.
_A_RETURN = re.compile(r"(?m)\breturn[ \t]+([^\n;]+)")
_A_RESPONSE = re.compile(r"\.(?:json|send)\(\s*([^\n)]*)\)")
#: An empty value in any of the languages the harness builds in.
_EMPTY = re.compile(r"^\s*(?:\[\s*\]|\{\s*\}|\(\s*\)|None|null|nil|undefined|''|\"\"|``)\s*;?\s*$")
#: Words a file says it is not built with.
_NOT_BUILT_MARK = re.compile(r"\braise\s+NotImplementedError\b|\bnot\s+implemented\b|\bunimplemented!", re.I)
_ABSTRACT = re.compile(r"\babstract", re.I)

#: A request path written in a defect or a work order.
_A_PATH = re.compile(r"(?<![\w.])(/[A-Za-z0-9_\-{}:<>\[\].*/]+)")
_A_PARAMETER = re.compile(r"^(?:\{.*\}|:.+|<.+>|\[.+\]|\*.*)$")
_A_CRITERION_ID = re.compile(r"\b(?:AC|CR)-\d+\b")
_404 = re.compile(r"\b404\b")


def applies() -> bool:
    """Thorough delivery only: fast delivery checks its own drafts (`drafting._promised_but_not_written`)."""
    from app import delivery

    return not delivery.fast()


def pending(state: Any) -> set[str]:
    """The builder stages sent back and not yet built again."""
    return {stage for stage, note in (state.get("unfinished_orders") or {}).items() if note}


# -- what the product holds -------------------------------------------------------------------------------------------


def answers_only_empty(text: str) -> bool:
    """Whether a code file is a stub: it says it is not built, or every answer it gives (two at least) is empty."""
    if _NOT_BUILT_MARK.search(text) and not _ABSTRACT.search(text):
        return True
    answers = [m.group(1).strip() for m in _A_RESPONSE.finditer(text)]
    answers += [value.strip() for value in (m.group(1) for m in _A_RETURN.finditer(text))
                if value.strip() and not _A_RESPONSE.search(value)]
    return len(answers) >= 2 and all(_EMPTY.match(answer) for answer in answers)


def _is_code(relative: str) -> bool:
    from app.analysis.file_kinds import BEHAVIOUR_SUFFIXES, SCRIPTED_MARKUP_SUFFIXES, classify_file

    suffix = PurePosixPath(relative).suffix.lower()
    return (suffix in BEHAVIOUR_SUFFIXES or suffix in SCRIPTED_MARKUP_SUFFIXES) and classify_file(relative) == "application"


def product_sources(root: str | Path) -> dict[str, str]:
    """The product's own code, by workspace-relative path: no tests, no locked suite, no installs. Never raises."""
    found: dict[str, str] = {}
    try:
        from app.acceptance import suite
        from app.analysis.walk import files_under

        base = Path(root)
        locked = (suite.relative_directory(root) or "").strip("/")
        for path in files_under(base, _SKIPPED_FOLDERS, skip_hidden=True):
            relative = path.relative_to(base).as_posix()
            if locked and (relative == locked or relative.startswith(locked + "/")):
                continue
            if not _is_code(relative):
                continue
            try:
                if path.stat().st_size > MOST_BYTES:
                    continue
                found[relative] = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if len(found) >= MOST_FILES:
                break
    except Exception:  # noqa: BLE001 - nothing read: nothing is said to be missing
        logger.debug("Could not read the product's code", exc_info=True)
    return found


def _literal_segments(path: str) -> list[str]:
    clean = str(path or "").split("?", 1)[0].strip().strip("/")
    return [segment for segment in clean.split("/") if segment and not _A_PARAMETER.match(segment)
            and "{" not in segment]


def served_by_the_code(path: str, sources: dict[str, str]) -> bool:
    """Whether some code could serve this route: its last fixed segment is in a quoted string, or names a file or
    folder (routing by files). Lenient on purpose: a route said to be missing goes back to a builder."""
    segments = _literal_segments(path)
    if not segments:
        return True
    last = segments[-1]
    word = re.escape(last)
    quoted = re.compile(r"[\"'`][^\"'`\n]*(?<![\w-])" + word + r"(?![\w-])[^\"'`\n]*[\"'`]|:" + word + r"\b")
    for relative, text in sources.items():
        if last in PurePosixPath(relative).parts or PurePosixPath(relative).stem == last:
            return True
        if quoted.search(text):
            return True
    return False


def _route_pattern(path: str) -> re.Pattern[str]:
    parts = []
    for segment in str(path or "").split("?", 1)[0].strip().strip("/").split("/"):
        if not segment:
            continue
        parts.append(r"[^/\s]+" if _A_PARAMETER.match(segment) or "{" in segment else re.escape(segment))
    return re.compile(r"^/" + "/".join(parts) + r"/?$", re.I)


def _same_route(written: str, contract_path: str) -> bool:
    """Whether a path written in a defect or an order is the contract's route (its parameters filled in or not)."""
    clean = written.rstrip(".,:;)'\"`").split("?", 1)[0]
    if _route_pattern(contract_path).match(clean):
        return True
    shape = [("*" if _A_PARAMETER.match(s) or "{" in s else s.lower()) for s in clean.strip("/").split("/") if s]
    wanted = [("*" if _A_PARAMETER.match(s) or "{" in s else s.lower())
              for s in contract_path.split("?", 1)[0].strip("/").split("/") if s]
    return bool(shape) and shape == wanted


# -- what a work order promised -------------------------------------------------------------------------------------


def _text_of(task: Any) -> str:
    fields = ("title", "task_description")
    lists = ("interfaces", "steps", "acceptance_criteria", "test_cases", "verification")
    return "\n".join([*(str(getattr(task, f, "") or "") for f in fields),
                      *(str(line) for f in lists for line in (getattr(task, f, None) or []))])


def _normal(text: str) -> str:
    return " ".join(str(text or "").lower().split())


def criteria_it_names(task: Any, criteria: Sequence[Any]) -> set[str]:
    """The criteria ids a work order names: by id, or by quoting the criterion's text."""
    lines = [str(line) for line in getattr(task, "acceptance_criteria", None) or []]
    named = {found for line in lines for found in _A_CRITERION_ID.findall(line)}
    for criterion in criteria:
        text = _normal(getattr(criterion, "text", ""))
        if not text:
            continue
        for line in (_normal(line) for line in lines):
            if text[:60] in line or (len(line) >= 20 and line in text):
                named.add(str(getattr(criterion, "id", "")))
    return {item for item in named if item}


def routes_promised(task: Any, checks: Sequence[Any], owned: set[str], criteria: Sequence[Any] = ()) -> list[Any]:
    """The contract's HTTP routes this work order promised: those its own words name, and those of the sprint's
    criteria it names when it builds the server's side (`backend`)."""
    text = _text_of(task)
    written = [match.group(1) for match in _A_PATH.finditer(text)]
    named = criteria_it_names(task, criteria) if str(getattr(task, "specialist_role", "")) == "backend" else set()
    if owned:
        named &= owned
    promised = []
    for check in checks:
        if getattr(check, "kind", "") != "http" or not getattr(check, "path", ""):
            continue
        if getattr(check, "criterion", "") and owned and check.criterion not in owned:
            continue
        if check.criterion in named or any(_same_route(path, check.path) for path in written):
            if all(check.path != other.path for other in promised):
                promised.append(check)
    return promised


def _its_files(task: Any, root: Path) -> list[str]:
    from app.stacks.contract import owned_by_the_harness
    from app.tools.repository import is_secret_path

    files = []
    for path in getattr(task, "files", None) or []:
        path = str(path).strip()
        if not path or path.endswith("/") or "*" in path or is_secret_path(Path(path)):
            continue
        if owned_by_the_harness(str(root), path):
            continue
        files.append(path)
    return files


def what_is_missing(task: Any, root: str | Path, *, sources: dict[str, str], stubs: Iterable[str] = (),
                    checks: Sequence[Any] = (), owned: set[str] | None = None,
                    criteria: Sequence[Any] = ()) -> list[str]:
    """One line for each thing a work order promised that the workspace does not hold; [] when it is done."""
    from app.graph.drafting import not_defined_in, promised_names

    base = Path(root)
    stubbed = set(stubs)
    missing: list[str] = []
    # Its own files too, tests among them: a testing order promises the tests it defines.
    own: dict[str, str] = {}
    for path in _its_files(task, base):
        file = base / path
        if not file.is_file():
            missing.append(f"`{path}` does not exist")
            continue
        try:
            own[path] = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if path in stubbed:
            missing.append(f"`{path}` is still the file the scaffold wrote")
        elif _is_code(path) and answers_only_empty(own[path]):
            missing.append(f"`{path}` answers every request with an empty value or says it is not built")
    for name in not_defined_in(promised_names(task), {**sources, **own}):
        missing.append(f"`{name}`, which its interfaces promise, is defined nowhere in the product")
    for check in routes_promised(task, checks, set(owned or ()), criteria):
        if not served_by_the_code(check.path, sources):
            missing.append(f"`{check.method} {check.path}` ({check.criterion or 'the contract'}) is served by no code")
    return missing


# -- the sprint's side ----------------------------------------------------------------------------------------------


def _root(state: Any) -> str:
    return str(getattr(state.get("repository"), "root_path", "") or "")


def _tasks(state: Any) -> list[Any]:
    return list(getattr(state.get("milestone_plan"), "delegated_tasks", None) or [])


def _stage_name(task: Any, index: int) -> str:
    from app.graph.workflow import _specialist_stage_name

    return _specialist_stage_name(task, index)


def the_sprint_s_criteria(state: Any) -> set[str]:
    """This sprint's own criteria; every criterion due when the plan assigned none."""
    sprints = list(getattr(state.get("sprint_plan"), "sprints", None) or [])
    index = int(state.get("current_sprint_index") or 0)
    own = list(getattr(sprints[index], "criteria", None) or []) if 0 <= index < len(sprints) else []
    if own:
        return {str(item) for item in own}
    try:
        from app.graph.acceptance_nodes import criteria_due

        return {str(item) for item in criteria_due(state) or []}
    except Exception:  # noqa: BLE001 - none known: every route the orders name counts
        return set()


def _what_the_contract_says(root: str) -> tuple[list[Any], list[Any]]:
    try:
        from app.acceptance import interface_contract, suite

        return interface_contract.the_locked_contract(root), suite.criteria(root)
    except Exception:  # noqa: BLE001 - no contract: no route is checked
        return [], []


def _stubs(root: str) -> frozenset[str]:
    from app.stacks.scaffold import files_still_as_the_scaffold_wrote_them

    return files_still_as_the_scaffold_wrote_them(root)


def _the_note(lines: list[str], heading: str, opening: str) -> str:
    return (
        f"\n\n--- {heading} ---\n{opening}\n"
        + "\n".join(f"- {line}" for line in lines)
        + "\nBuild what is missing now, in the files the work order names, and check it as the work order says. "
        "Where something listed is already built under another name or in another file, say where in your report "
        "and leave it as it is."
    )


BUILD_HEADING = "Your work order is not finished"
BUILD_OPENING = ("Every builder of this sprint has handed over, and the harness checked each work order against what "
                 "it promised. Before any test runs, this one is yours again. Missing:")
ROUND_HEADING = "What the test round found not built in your work order"
ROUND_OPENING = ("The test round after the build measured the following. Each is this work order's to build, not a "
                 "fault for a fixer:")


def after_the_build(state: Any) -> dict[str, Any] | None:
    """The update that sends every unfinished work order back to its builder, once an attempt; None to go on to CI.

    Never raises: a check that cannot answer goes on as before.
    """
    try:
        if not applies() or AFTER_THE_BUILD in (state.get("builders_sent_back") or []):
            return None
        root = _root(state)
        tasks = _tasks(state)
        if not root or not tasks:
            return None
        sources = product_sources(root)
        stubs = _stubs(root)
        checks, criteria = _what_the_contract_says(root)
        owned = the_sprint_s_criteria(state)
        notes: dict[str, str] = {}
        for index, task in enumerate(tasks):
            missing = what_is_missing(task, root, sources=sources, stubs=stubs, checks=checks, owned=owned,
                                      criteria=criteria)
            if missing:
                stage = _stage_name(task, index)
                notes[stage] = _the_note(missing, BUILD_HEADING, BUILD_OPENING)
                logger.warning("Work order %d (%s) is not finished; back to its builder: %s", index, stage,
                               "; ".join(missing))
                _noted(SENT_BACK_EVENT, stage, state, detail=f"{SENT_BACK_SAID}: " + "; ".join(missing))
        if not notes:
            return None
        return {"unfinished_orders": notes,
                "builders_sent_back": [*(state.get("builders_sent_back") or []), AFTER_THE_BUILD]}
    except Exception:  # noqa: BLE001 - the build goes on to CI as before
        logger.warning("Could not check the work orders against what they promised", exc_info=True)
        return None


def _noted(event: str, stage: str, state: Any, *, defect: Any = None, round_: int | None = None,
           detail: str = "") -> None:
    from app.observability import defect_ledger

    defect_ledger.note(event, stage, defect=defect, round_=round_, sprint=state.get("current_sprint_index", 0),
                       detail=detail)


def with_what_is_missing(request: dict[str, Any], state: Any, stage_name: str) -> dict[str, Any]:
    """`request` with what its work order was sent back for; as it was when it was not sent back."""
    note = (state.get("unfinished_orders") or {}).get(stage_name)
    if note and request.get("messages") and isinstance(request["messages"][-1].get("content"), str):
        request["messages"][-1]["content"] += note
    return request


def built_again(state: Any, stage_name: str, output: Any) -> tuple[Any, dict[str, Any]]:
    """A sent-back builder's output with the files its first visit changed kept, and the update that marks it built
    again; `output` and {} for any other builder."""
    if stage_name not in pending(state):
        return output, {}
    earlier = (state.get("specialist_outputs") or {}).get(stage_name)
    try:
        if earlier is not None:
            output = output.model_copy(update={
                "changed_files": list(dict.fromkeys([*earlier.changed_files, *output.changed_files])),
                "tests": list(dict.fromkeys([*earlier.tests, *output.tests])),
            })
    except Exception:  # noqa: BLE001 - its own output stands
        logger.debug("Could not keep the first visit's files", exc_info=True)
    return output, {"unfinished_orders": {stage_name: ""}}


# -- a test round's defects -----------------------------------------------------------------------------------------


def _said(defect: Any) -> str:
    import json

    parts = [str(getattr(defect, field, "") or "") for field in
             ("description", "actual_behavior", "reproduction_steps", "expected_behavior")]
    evidence = getattr(defect, "evidence", None) or []
    if evidence:
        parts.append(json.dumps(evidence, default=str))
    return "\n".join(parts)


def _names_the_file(defect: Any, said: str, path: str) -> bool:
    named = {str(f).strip().lstrip("./") for f in getattr(defect, "affected_files", None) or []}
    if path in named or any(path.endswith("/" + f) or f.endswith("/" + path) for f in named if f):
        return True
    name = PurePosixPath(path).name
    return bool(re.search(r"(?<![\w.-])" + re.escape(path) + r"(?![\w-])", said)
                or re.search(r"(?<![\w.-])" + re.escape(name) + r"(?![\w-])", said))


def not_built(defects: Sequence[Any], tasks: Sequence[Any], root: str | Path, *, sources: dict[str, str],
              stubs: Iterable[str] = (), checks: Sequence[Any] = (), owned: set[str] | None = None,
              criteria: Sequence[Any] = ()) -> dict[int, list[Any]]:
    """Work order index -> the defects that say its work is not built: a 404 on a contract route it promised that no
    code serves, a file it named that does not exist, or a file of it that is still a stub."""
    base = Path(root)
    stubbed = set(stubs)
    owned = set(owned or ())
    unbuilt_files: list[tuple[int, str]] = []
    for index, task in enumerate(tasks):
        for path in _its_files(task, base):
            file = base / path
            if not file.is_file() or path in stubbed:
                unbuilt_files.append((index, path))
            elif _is_code(path):
                try:
                    if answers_only_empty(file.read_text(encoding="utf-8", errors="replace")):
                        unbuilt_files.append((index, path))
                except OSError:
                    continue
    promised = [(index, check) for index, task in enumerate(tasks)
                for check in routes_promised(task, checks, owned, criteria)]
    unserved = [(index, check) for index, check in promised if not served_by_the_code(check.path, sources)]
    found: dict[int, list[Any]] = {}
    for defect in defects:
        said = _said(defect)
        owner = next((index for index, path in unbuilt_files if _names_the_file(defect, said, path)), None)
        if owner is None and _404.search(said):
            written = [match.group(1) for match in _A_PATH.finditer(said)]
            owner = next((index for index, check in unserved if any(_same_route(p, check.path) for p in written)),
                         None)
        if owner is not None:
            found.setdefault(owner, []).append(defect)
    return found


def at_a_round(state: Any, measured: Sequence[Any]) -> dict[str, list[Any]]:
    """Builder stage -> the defects of a test round that say its work order is not built, when they go to it.

    {} - the round goes to the fix loop as before - in fast delivery, once this attempt has done it, when fewer than
    half the round's defects say "not built", or when nothing can be read. Never raises.
    """
    try:
        if not applies() or not measured or AFTER_A_ROUND in (state.get("builders_sent_back") or []):
            return {}
        root = _root(state)
        tasks = _tasks(state)
        if not root or not tasks:
            return {}
        # Far past the sprint's time budget no more is started: the attempt ends as the fix round would.
        from app.graph import sprint_time_budget

        budget = sprint_time_budget.measure(state)
        if budget is not None and budget.ends_the_fix_round():
            return {}
        checks, criteria = _what_the_contract_says(root)
        found = not_built(measured, tasks, root, sources=product_sources(root), stubs=_stubs(root), checks=checks,
                          owned=the_sprint_s_criteria(state), criteria=criteria)
        taken = sum(len(defects) for defects in found.values())
        if not taken or taken < NOT_BUILT_SHARE * len(measured):
            return {}
        return {_stage_name(tasks[index], index): defects for index, defects in found.items()}
    except Exception:  # noqa: BLE001 - the fix loop takes the round as before
        logger.warning("Could not read whether the round's defects are work not built", exc_info=True)
        return {}


def sent_to_the_builders(state: Any, taken: dict[str, list[Any]], test_round: int) -> dict[str, Any]:
    """The fields that send a round's not-built defects to their builders, each told what the round found; recorded
    in the ledger."""
    notes: dict[str, str] = {}
    for stage, defects in taken.items():
        notes[stage] = _the_note([" ".join(str(getattr(d, "description", "")).split())[:400] for d in defects],
                                 ROUND_HEADING, ROUND_OPENING)
        logger.warning("test_round_%d: %d defect(s) are work not built; back to %s", test_round, len(defects), stage)
        for defect in defects:
            _noted(ROUTED_EVENT, f"test_round_{test_round}", state, defect=defect, round_=test_round,
                   detail=f"{ROUTED_SAID}: {stage}")
    return {
        "stage": "specialist_dispatch",
        "specialist_task_index": 0,
        "unfinished_orders": notes,
        "builders_sent_back": [*(state.get("builders_sent_back") or []), AFTER_A_ROUND],
    }


def superseded(cycle: Any, taken: dict[str, list[Any]]) -> Any:
    """`cycle` with the defects sent to builders closed as `superseded`: the next round measures them again."""
    taken = [defect for defects in taken.values() for defect in defects]
    if not taken:
        return cycle
    defects = [
        defect.model_copy(update={"status": "superseded"})
        if getattr(defect, "status", "") == "open" and any(defect is t or defect == t for t in taken) else defect
        for defect in getattr(cycle, "defects", None) or []
    ]
    return cycle.model_copy(update={"defects": defects})


__all__ = [
    "AFTER_A_ROUND", "AFTER_THE_BUILD", "NOT_BUILT_SHARE", "ROUTED_EVENT", "ROUTED_SAID", "SENT_BACK_EVENT",
    "SENT_BACK_SAID", "after_the_build", "answers_only_empty", "applies", "at_a_round", "built_again",
    "criteria_it_names", "not_built", "pending", "product_sources", "routes_promised", "sent_to_the_builders",
    "served_by_the_code", "superseded", "what_is_missing", "with_what_is_missing",
]
