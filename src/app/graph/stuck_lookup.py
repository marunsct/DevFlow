"""A stuck fixer is shown what others found for its error: the harness looks it up, not the model (plan WL.4).

Behind `WEB_LOOKUP_WHEN_STUCK` (off in code; the compose file and each run's own setting say whether it is on - the
user's control). Measured the night it was built: the local model, offered search tools in about 3,500 requests,
never called them, and every open-source harness researched leaves that decision to the model. So the harness decides,
on three triggers:

- T1: a defect shown to a fixer again after a fix of its problem did not close it - in this attempt or an earlier one
  of the run - whose text states a concrete error;
- T2: an install or a setup that failed with an error the registry note does not explain (a version or a feature that
  does not exist is answered from the registry instead, `contract._the_versions_that_exist`);
- T3: a build or compile error the round before reported too (`build_errors_in`), looked up with the stack's
  toolchain and the version this project runs;
- T4, behind `LOOKUP_AT_FIRST_SIGHT` (off until measured, FX.9): a defect's error whose line or trace names an
  installed third-party package, looked up for the defect's first fixer instead of after a failed fix. Measured: on a
  medium run no fixer met T1 with an error to search, and a library's error (`'SQLiteTypeCompiler' object has no
  attribute 'visit_ARRAY'`) that a search answers in seconds was never looked up.

Every fixer shown gets one ledger record of what became of its lookup (FX.11, always on): looked up, or the gate that
stopped it - switched off, not stuck, no error line, mutation finding, product's own name, nothing found, refused.
Measured before it: on a medium run none of eight fixer briefs had an error line, every lookup returned silently at
its gates, and the audit could only say "not reached".

Each distinct cleaned error is looked up once per run, whichever trigger meets it, the way a person does it
(`app.graph.stuck_research`, plan HK.3): the installed package's own files first, then several short queries to the
library's own tracker and the free official sources (`app.tools.lookups`), the resolution read rather than the
question, ranked by source, version and recency - and, behind `STUCK_LOOKUP_CONDENSED`, one note condensed and
checked against the project's versions instead of raw leads. Each lookup is a note with an id, a ledger record naming
its trigger, its sources and its defect, so the audit can say whether it fired and helped.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Any

from app.switches import is_on

logger = logging.getLogger(__name__)

#: `WEB_LOOKUP_WHEN_STUCK` set to on or off overrides this.
ON_BY_DEFAULT = False
#: The ledger's event for a lookup made.
LOOKUP_EVENT = "lookup"
#: The ledger's names for each trigger, so the audit can count them apart.
TRIGGER_STUCK = "T1 stuck"
TRIGGER_INSTALL = "T2 install"
TRIGGER_RECURRING = "T3 recurring build error"
TRIGGER_FIRST_SIGHT = "T4 first sight"
#: What a T4 note opens with: the fixer is told whose error it is; the audit's switch-firing check reads it.
FIRST_SIGHT_SAYS = ("Looked up when first seen: this error comes from the installed package `{library}`, so others "
                    "have met it too.")

#: What stopped a fixer's lookup, as its ledger record names it (FX.11).
LOOKED_UP = "looked up"
SWITCHED_OFF = "switched off"
NOT_STUCK = "not stuck"
NO_ERROR_LINE = "no error line"
MUTATION_FINDING = "mutation finding"
PRODUCT_S_OWN_NAME = "product's own name"
NOTHING_FOUND = "nothing found"
REFUSED = "refused"


def enabled() -> bool:
    return is_on("WEB_LOOKUP_WHEN_STUCK", ON_BY_DEFAULT)


class _FirstSight:
    """`LOOKUP_AT_FIRST_SIGHT` as the switch registry reads one: off in code until measured (FX.9)."""

    ON_BY_DEFAULT = False
    #: What the admin page says this switch does.
    explanation = ("A defect whose error line or trace names an installed third-party package has that error looked "
                   "up for its first fixer, not only after a fix failed; still once per distinct error per run, and "
                   "only where stuck lookups are on for the run.")

    @staticmethod
    def enabled() -> bool:
        return is_on("LOOKUP_AT_FIRST_SIGHT", _FirstSight.ON_BY_DEFAULT)


first_sight_switch = _FirstSight()


class _Tried:
    """One trigger's try for a fixer: the block shown ("" for none), the gate that ended it, the trigger's name."""

    __slots__ = ("gate", "shown", "trigger")

    def __init__(self, shown: str, gate: str, trigger: str) -> None:
        self.shown, self.gate, self.trigger = shown, gate, trigger


def _stuck(repo_root: str | Path, defect: Any) -> bool:
    """Whether an earlier fix of this defect's problem ended without closing it: in this cycle, or anywhere in the run.

    The defect's own attempts live on its remediation cycle, and a re-planned sprint starts a new one; measured, the
    same criterion left open in one sprint attempt came back in the next with no attempt of its own, so its first
    fixer there was not stuck. The fix journal counts the problem's failed fixes over the whole run.
    """
    if any(isinstance(a, dict) and str(a.get("outcome") or "") not in {"", "fixed"}
           for a in getattr(defect, "attempts", None) or []):
        return True
    from app.graph import cause_journal

    return cause_journal.failed_fixes_in_the_run(repo_root, defect) > 0


#: The place a defect gives after what the server printed: `(File "...", line 12, in f)` or `(at f (/app/x.js:3:5))`.
_A_PLACE_GIVEN = re.compile(r"\s*\((?:File\s|at\s)[^()]*(?:\([^()]*\)[^()]*)*\)\s*$")


def _what_the_server_printed(text: str) -> str:
    """The server's own error line a defect quotes after "the server printed:" - the last it gives for the first
    request, its place left out - or "" when it quotes none."""
    from app.acceptance.what_went_wrong import THE_SERVER_PRINTED

    _, marked, after = str(text or "").partition(THE_SERVER_PRINTED)
    if not marked:
        return ""
    depth, end = 0, len(after)
    for at, char in enumerate(after):
        if char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                end = at
                break
            depth -= 1
        elif char == "\n" or (depth == 0 and after.startswith("; `", at)):
            end = at
            break
    said = [part.strip() for part in after[:end].split(" / ") if part.strip()]
    return " ".join(_A_PLACE_GIVEN.sub("", said[-1]).split()) if said else ""


def _the_error_line(defect: Any) -> str:
    """The error to look up for the defect, or "": the server's own error line where the defect quotes what the server
    printed, else the last error its text states - a criterion's prose ("does not work yet") is not searchable.

    Measured on one run: an edge probe's defect was searched as its whole first sentence - the harness's own wording
    and the product's route ("Requests at the edges of the interface contract are not handled: `GET /notes/{id}` ...")
    - where the server had printed the error others would have written about.
    """
    from app.acceptance.what_went_wrong import the_errors_stated

    text = f"{getattr(defect, 'actual_behavior', '') or ''}\n{getattr(defect, 'description', '')}"
    if printed := _what_the_server_printed(text):
        return printed
    # The product's own error, never the harness's wording or the test runner's: measured over three days of runs, a
    # third of the searches were "Requests at the edges of the interface contract ...", "A fix was tried and
    # reverted ..." or Playwright's "Process from config.webServer was not able to start", which no one else wrote
    # about. The last such line the defect states, cut to where its error begins; "" when it states none.
    stated = [_from_the_error_on(line) for line in the_errors_stated(text)]
    own = [line for line in stated if not _NOT_THE_PRODUCT_S_WORDS.search(line)]
    return own[-1] if own else ""


#: Wording that is the harness's or the test runner's, not an error the product raised: a search for it finds nothing.
_NOT_THE_PRODUCT_S_WORDS = re.compile(
    r"config\.webServer|Requests at the edges of the interface contract|A fix was tried and reverted"
    r"|The product does not start|The product did not start|the acceptance suite says|Distinct causes, most failing first"
    r"|The unit tests fail\b|The server fails on a request it should|^\s*-\s*\[|^\s*Expected\b|^\s*assert\b"
    # A line that counts the errors is a build's summary, not an error: measured on one run, a stuck Rust fix was
    # searched as "error: could not compile `notes_api` (lib) due to 17 previous errors", the last line stated.
    r"|\b\d+ (?:previous )?errors?\b",
    re.I)


#: Where an error proper begins in a stated line: a dotted exception or error name and its colon
#: (`sqlite3.OperationalError:`, `TypeError:`, `java.lang.IllegalStateException:`), or a compiler's error code.
_THE_ERROR_BEGINS = re.compile(r"(?<![\w.])(?:[A-Za-z_][\w]*\.)*[A-Za-z_]\w*(?:Error|Exception|Fault)\b:|\berror[: ]+[A-Z]+\d+\b")


def _from_the_error_on(line: str) -> str:
    """The stated line from where its error begins: the harness's own words before it ("The unit tests fail. It says:
    Distinct causes, ...") are not what anyone else wrote about. Measured on one run: a unit-test defect was searched
    with that whole preamble ahead of `sqlite3.OperationalError: ...`. The line as it is when no error name is found."""
    found = _THE_ERROR_BEGINS.search(line)
    return line[found.start():] if found else line


def _the_stack_s_words(stack: Any) -> str:
    return " ".join(str(getattr(stack, field, "") or "") for field in ("language", "framework") if getattr(stack, field, ""))


def _the_private_words(repo_root: str | Path) -> list[str]:
    """Names that are the product's, never sent: the project's folder and the workspace's name, the contract's project,
    package and title, the product's name from the intake and the nouns its routes are named by (the one outbound gate's
    words, `app.tools.outbound.private_words`)."""
    words = [Path(repo_root).name]
    try:
        from app.tools import outbound

        words += [w for w in outbound.private_words(repo_root) if w not in words]
    except Exception:  # noqa: BLE001 - the folder's name alone
        pass
    return [w for w in words if w]


def _once_each(words: str) -> str:
    seen: set[str] = set()
    kept = []
    for word in words.split():
        if word.lower() not in seen:
            seen.add(word.lower())
            kept.append(word)
    return " ".join(kept)


def _the_toolchain_words(repo_root: str | Path, stack: Any) -> str:
    """The stack's language and framework, its toolchain's name and, where it is known, the version this project runs:
    a compiler's message means different things in different releases. From the language table and the runtime the
    project pinned, else the version this environment has; never a guess."""
    words = [_the_stack_s_words(stack)]
    try:
        from app.stacks import languages
        from app.tools import package_registry, runtimes

        said = str(getattr(stack, "language", "") or "").strip().lower()
        row = languages.language(said) or languages.language(said.replace("#", "sharp").replace(" ", ""))
        toolchain = row.sandbox_toolchain if row is not None and isinstance(row.sandbox_toolchain, str) else ""
        version = ""
        if row is not None and isinstance(row.runtime_version, str):
            version = str((runtimes.recorded(repo_root).get(row.runtime_version) or {}).get("version") or "")
        ecosystem = package_registry.ecosystem_named(row.name if row is not None else said)
        if not version and ecosystem:
            here = package_registry.runtime_here(ecosystem)
            numbers = package_registry._numbers(here) if "not installed" not in here else ()  # noqa: SLF001
            version = ".".join(str(n) for n in numbers[:3])
        words.append(" ".join(part for part in (toolchain, version) if part))
    except Exception:  # noqa: BLE001 - the language and framework alone
        pass
    return _once_each(" ".join(words))


def _the_installer_words(repo_root: str | Path, stack: Any) -> str:
    """The stack's language and framework and the tool its install runs (the contract's first install command)."""
    tool = ""
    try:
        from app.stacks import contract

        commands = (contract.read(repo_root) or {}).get("install") or []
        tool = Path(str(commands[0][0])).name if commands and commands[0] else ""
    except Exception:  # noqa: BLE001 - the stack's names alone
        tool = ""
    return _once_each(" ".join(part for part in (_the_stack_s_words(stack), tool) if part))


def _looked_up(repo_root: str | Path, error: str, stack_words: str, *, trigger: str, stage_name: str,
               defect: Any = None, stack: Any = None, model: Any = None, library: tuple[str, str] = ("", ""),
               noted: bool = True) -> _Tried:
    """`error` looked up once per run - the same cleaned error met by any trigger is asked once - as the section a
    request carries (`stuck_research.researched`, plan HK.3), with the gate that ended it: looked up, the product's
    own name (nothing of the error may leave), nothing found or refused. Each note shown is a ledger record with its
    id and the defect it was for, the first as a lookup, each later one as shown again
    (`app.observability.lookup_notes`, HK.4). `library`: the installed package a trace named (T4). `noted` false: a
    resume of the stage that was shown it already - the note is shown, not recorded again."""
    from app.graph import stuck_research
    from app.observability import lookup_notes
    from app.tools import lookups

    from app.tools import lookup_service

    private = _the_private_words(repo_root)
    cleaned = lookups.cleaned(error, private)
    if not cleaned:
        return _Tried("", PRODUCT_S_OWN_NAME, trigger)

    def research() -> list[str]:
        shown, query, verdict = stuck_research.researched(
            repo_root, error, stack_words, private, stack=stack, defect=defect, trigger=trigger,
            stage_name=stage_name, model=model, library=library)
        return [("\n" + shown) if shown else "", query, verdict]

    # The run's own record in the shared store (plan HK.12): kept across a deploy, a restart and every worker of the
    # run, where a module dictionary was lost with its process and never emptied.
    kept, again = lookup_service.once_per_run("stuck lookup", repo_root, cleaned, research)
    shown, query, verdict = [*(kept if isinstance(kept, (list, tuple)) else []), "", "", ""][:3]
    if again and shown and noted:
        lookup_notes.record(stage_name, {"query": query}, trigger=trigger, defect=defect, again=True)
    if shown:
        return _Tried(shown, LOOKED_UP, trigger)
    return _Tried("", REFUSED if verdict == "refused" else NOTHING_FOUND, trigger)


def _the_stuck_or_first_sight(repo_root: str | Path, defect: Any, stack: Any, stage_name: str,
                              model: Any = None, noted: bool = True) -> _Tried:
    """T1 for a stuck defect; T4, behind its switch, for one not stuck whose error line or trace names an installed
    third-party package; else the gate that stopped both."""
    if not enabled():
        return _Tried("", SWITCHED_OFF, "")
    stuck = _stuck(repo_root, defect)
    trigger = TRIGGER_STUCK if stuck else TRIGGER_FIRST_SIGHT
    if not stuck and not first_sight_switch.enabled():
        return _Tried("", NOT_STUCK, TRIGGER_STUCK)
    from app.acceptance import mutation_guided

    if mutation_guided.is_a_finding(defect):
        return _Tried("", MUTATION_FINDING, trigger)
    error = _the_error_line(defect)
    if not error:
        return _Tried("", NO_ERROR_LINE, trigger)
    library = ("", "")
    if not stuck:
        from app.graph import stuck_research

        library = stuck_research.installed_package_named(repo_root, error, _the_text_of(defect))
        if not library[0]:
            return _Tried("", NOT_STUCK, TRIGGER_STUCK)
    tried = _looked_up(repo_root, error, _the_stack_s_words(stack), trigger=trigger, stage_name=stage_name,
                       defect=defect, stack=stack, model=model, library=library, noted=noted)
    if tried.shown and not stuck:
        tried.shown = f"\n{FIRST_SIGHT_SAYS.format(library=library[0])}{tried.shown}"
    return tried


def section(repo_root: str | Path, defect: Any, stack: Any, stage_name: str = "defect_fix", model: Any = None) -> str:
    """T1: what others found for this stuck defect's error, as its fixer's request carries it - or T4's for a defect
    not yet stuck whose error is an installed package's (`LOOKUP_AT_FIRST_SIGHT`); "" when off, not stuck, with no
    concrete error, or when nothing was found. Never raises."""
    try:
        return _the_stuck_or_first_sight(repo_root, defect, stack, stage_name, model).shown
    except Exception:  # noqa: BLE001 - the fix goes on without it
        logger.debug("Could not look up a stuck defect's error", exc_info=True)
        return ""


# --- T2: an install or a setup that failed with an error the registry does not explain ------------------------------

#: A line naming an error outright, preferred over one that only says something failed or could not be done.
_SAYS_ERROR = re.compile(r"\berror\b|\bERR!", re.I)


def _the_installer_s_error(said: str) -> str:
    """The line of what an installer or a setup printed that says what went wrong, or "": of the lines stating an
    error, the longest of those that name one outright (a tool's generic lines are short, the one with the cause is
    not); only the installer's own words, after "it said:", where the harness's note quotes them."""
    from app.stacks import contract

    text = str(said or "")
    if "it said:" in text:
        text = text.partition("it said:")[2].partition("; it ended")[0]
    stated = [line for line in contract._what_the_installer_said_went_wrong(text).splitlines()  # noqa: SLF001
              if line.strip() and contract.INSTALL_FAILED not in line]
    outright = [line for line in stated if _SAYS_ERROR.search(line)] or stated
    return max(outright, key=len)[:300] if outright else ""


def for_an_install_that_failed(repo_root: str | Path, defect: Any, stack: Any, stage_name: str = "defect_fix",
                               model: Any = None) -> str:
    """T2: for the defect saying the project's dependencies do not install, what others found for the installer's
    error, from its first fix - unless the registry already explains it (a version or a feature that does not exist,
    for which the note carries the registry's answer). "" when off or not such a defect. Never raises."""
    tried = _the_install_s_error_looked_up(repo_root, defect, stack, stage_name, model)
    return tried.shown if tried is not None else ""


def _the_install_s_error_looked_up(repo_root: str | Path, defect: Any, stack: Any, stage_name: str,
                                   model: Any = None, noted: bool = True) -> _Tried | None:
    """T2's try, or None when it does not apply (off, not an install that failed, or one the registry explains)."""
    try:
        if not enabled():
            return None
        from app.stacks import contract

        said = str(getattr(defect, "actual_behavior", "") or "")
        if contract.INSTALL_FAILED not in said or contract.the_registry_explains(said):
            return None
        error = _the_installer_s_error(said)
        if not error:
            return _Tried("", NO_ERROR_LINE, TRIGGER_INSTALL)
        return _looked_up(repo_root, error, _the_installer_words(repo_root, stack), trigger=TRIGGER_INSTALL,
                          stage_name=stage_name, defect=defect, stack=stack, model=model, noted=noted)
    except Exception:  # noqa: BLE001 - the fix goes on without it
        logger.debug("Could not look up an install's error", exc_info=True)
        return None


def for_a_failed_setup(repo_root: str | Path, problem: str, stack: Any, stage_name: str = "stack_setup") -> str:
    """T2, for the setup stage sent back: what others found for the error its last setup failed on; "" when off, with
    no stated error, or with one the registry explains. Never raises."""
    try:
        if not enabled() or not str(problem or "").strip():
            return ""
        from app.stacks import contract

        if contract.the_registry_explains(problem):
            return ""
        error = _the_installer_s_error(problem)
        if not error:
            return ""
        return _looked_up(repo_root, error, _the_installer_words(repo_root, stack), trigger=TRIGGER_INSTALL,
                          stage_name=stage_name, stack=stack).shown
    except Exception:  # noqa: BLE001 - the setup is asked again without it
        logger.debug("Could not look up a setup's error", exc_info=True)
        return ""


# --- T3: a build or compile error that recurs across rounds ---------------------------------------------------------

#: Each round's build and compile errors, by sprint and round, kept in the workspace so a resumed run still has them.
ROUNDS_FILE = ".harness/build-errors-by-round.json"
#: Rounds kept in the file.
MOST_ROUNDS_KEPT = 12
#: A compiler's code beside the word "error" (`error CS1503:`, `error[E0502]:`, `error TS2345:`), or a tool's code
#: before a colon (`NU1102:`).
_A_CODE = re.compile(r"\berror\s*\[?\s*([A-Z]{1,4}\d{3,5})\b\]?|\b([A-Z]{2,4}\d{4}):")
#: A compiler's located error that has no code: `Main.java:12: error: incompatible types`, `main.c:3:5: error: ...`.
_A_LOCATED_ERROR = re.compile(r"\S+\.\w+(?::\d+(?::\d+)?|\(\d+(?:,\d+)?\)):?\s*(?:fatal\s+)?error:\s*(\S.*)$", re.I)
#: What changes between two reports of one error: quoted names and numbers.
_VARYING = re.compile(r"\"[^\"]*\"|'[^']*'|`[^`]*`|\d+")
#: The project a build tool names at the end of an error line, in brackets: `... [/src/app/app.proj]`.
_A_TRAILING_PROJECT = re.compile(r"\s*\[[^\]]*\]\s*$")

_WRITING = threading.Lock()


def build_errors_in(text: str) -> list[tuple[str, str]]:
    """(signature, the line to look up) for each build or compile error `text` reports, each signature once: the code
    where the compiler gives one, else its message without the values that change from round to round."""
    found: dict[str, str] = {}
    for line in str(text or "").splitlines():
        line = " ".join(line.split())
        code = _A_CODE.search(line)
        if code:
            # From the code on: not the file and line before it, nor the project a build tool names after it.
            found.setdefault(code.group(1) or code.group(2), _A_TRAILING_PROJECT.sub("", line[code.start():]))
            continue
        located = _A_LOCATED_ERROR.search(line)
        if located:
            message = located.group(1)
            found.setdefault("error: " + " ".join(_VARYING.sub("_", message).split()).lower()[:120],
                             "error: " + message)
    return list(found.items())


def _the_rounds(repo_root: str | Path) -> dict[str, list[str]]:
    try:
        data = json.loads((Path(repo_root) / ROUNDS_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): [str(s) for s in value] for key, value in data.items() if isinstance(value, list)}


def _keep_the_round(repo_root: str | Path, round_key: str, signatures: list[str]) -> None:
    with _WRITING:
        rounds = _the_rounds(repo_root)
        if rounds.get(round_key) == signatures:
            return
        rounds.pop(round_key, None)
        rounds[round_key] = signatures
        path = Path(repo_root) / ROUNDS_FILE
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(dict(list(rounds.items())[-MOST_ROUNDS_KEPT:])) + "\n", encoding="utf-8")
        except OSError:
            pass


def _the_text_of(defect: Any) -> str:
    return f"{getattr(defect, 'description', '') or ''}\n{getattr(defect, 'actual_behavior', '') or ''}"


def for_a_recurring_build_error(repo_root: str | Path, defect: Any, defects: list[Any], stack: Any, *, round_: int,
                                sprint: int = 0, stage_name: str = "defect_fix", look_up: bool = True,
                                model: Any = None) -> str:
    """T3: when this defect reports a build or compile error the round before reported too, what others found for it,
    looked up with the stack's toolchain and version; "" when off, when the error is new this round, for a mutation
    finding, or with `look_up` false. Keeps this round's errors (of all `defects`) for the next round. Never raises."""
    tried = _a_recurring_build_error_looked_up(repo_root, defect, defects, stack, round_=round_, sprint=sprint,
                                               stage_name=stage_name, look_up=look_up, model=model)
    return tried.shown if tried is not None else ""


def _a_recurring_build_error_looked_up(repo_root: str | Path, defect: Any, defects: list[Any], stack: Any, *,
                                       round_: int, sprint: int, stage_name: str, look_up: bool,
                                       model: Any = None, noted: bool = True) -> _Tried | None:
    """T3's try, or None when it does not apply (off, no build error the round before had too, `look_up` false)."""
    try:
        if not enabled():
            return None
        from app.acceptance import mutation_guided

        this_round = list(dict.fromkeys(
            signature for one in (defects or [defect]) if not mutation_guided.is_a_finding(one)
            for signature, _ in build_errors_in(_the_text_of(one))))
        before = set(_the_rounds(repo_root).get(f"{sprint}:{int(round_) - 1}") or [])
        _keep_the_round(repo_root, f"{sprint}:{int(round_)}", this_round)
        if not look_up or mutation_guided.is_a_finding(defect):
            return None
        for signature, line in build_errors_in(_the_text_of(defect)):
            if signature in before:
                return _looked_up(repo_root, line, _the_toolchain_words(repo_root, stack), trigger=TRIGGER_RECURRING,
                                  stage_name=stage_name, defect=defect, stack=stack, model=model, noted=noted)
        return None
    except Exception:  # noqa: BLE001 - the fix goes on without it
        logger.debug("Could not look up a recurring build error", exc_info=True)
        return None


def for_a_fixer(repo_root: str | Path, defect: Any, defects: list[Any], stack: Any, *, round_: int, sprint: int = 0,
                stage_name: str = "defect_fix", model: Any = None, first_visit: bool = True) -> str:
    """What others found for one fixer's defect, from the first trigger that applies: an install's error (T2), a build
    error the round before had too (T3), then the error of a defect an attempt left open (T1) - or, behind
    `LOOKUP_AT_FIRST_SIGHT`, of one not yet stuck whose error is an installed package's (T4). One block, so a request
    carries one; "" when none applies or nothing was found. `model` is the fixer's, for the one condensing call
    (`STUCK_LOOKUP_CONDENSED`). One ledger record says what became of it: looked up, or the gate that stopped it
    (FX.11). `first_visit` false: a resume of the fixer's stage after a gated tool call, which builds its request
    again - the same block is given (each lookup is the run's once, `lookup_service.once_per_run`) and nothing is
    recorded again. Measured on a live run: one fixer's stage resumed ten times in eleven minutes and the ledger had
    ten `lookup gate` records for it (LF.1506). Never raises."""
    installing = _the_install_s_error_looked_up(repo_root, defect, stack, stage_name, model, noted=first_visit)
    # Called whatever T2 found: it keeps this round's build errors for the next round.
    recurring = _a_recurring_build_error_looked_up(
        repo_root, defect, defects, stack, round_=round_, sprint=sprint, stage_name=stage_name,
        look_up=not (installing is not None and installing.shown), model=model, noted=first_visit)
    tried = [one for one in (installing, recurring) if one is not None]
    if not any(one.shown for one in tried):
        try:
            tried.append(_the_stuck_or_first_sight(repo_root, defect, stack, stage_name, model, noted=first_visit))
        except Exception:  # noqa: BLE001 - the fix goes on without it
            logger.debug("Could not look up a stuck defect's error", exc_info=True)
    chosen = next((one for one in tried if one.shown), None) or (tried[0] if tried else None)
    if chosen is None or not first_visit:
        return chosen.shown if chosen is not None else ""
    from app.observability import lookup_notes

    lookup_notes.gate_seen(stage_name, defect, chosen.gate, trigger=chosen.trigger)
    return chosen.shown


__all__ = ["LOOKED_UP", "LOOKUP_EVENT", "MUTATION_FINDING", "NOTHING_FOUND", "NOT_STUCK", "NO_ERROR_LINE",
           "ON_BY_DEFAULT", "PRODUCT_S_OWN_NAME", "REFUSED", "ROUNDS_FILE", "SWITCHED_OFF", "TRIGGER_FIRST_SIGHT",
           "TRIGGER_INSTALL", "TRIGGER_RECURRING", "TRIGGER_STUCK", "build_errors_in", "enabled", "first_sight_switch",
           "for_a_failed_setup", "for_a_fixer", "for_a_recurring_build_error", "for_an_install_that_failed",
           "section"]
