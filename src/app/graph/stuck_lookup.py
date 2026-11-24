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
  toolchain and the version this project runs.

Each distinct cleaned error is looked up once per run, whichever trigger meets it (`app.tools.lookups` - free official
sources first, a week's cache, only the cleaned error sent), and what was found goes into the request as quoted
leads. Each lookup is a ledger record naming its trigger, so the audit can say whether it fired and helped.
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

#: (workspace, cleaned error) already looked up in this process - one lookup per error per run - and (the section it
#: gave, the query it searched).
_DONE: dict[tuple[str, str], tuple[str, str]] = {}


def enabled() -> bool:
    return is_on("WEB_LOOKUP_WHEN_STUCK", ON_BY_DEFAULT)


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
               defect: Any = None) -> str:
    """`error` looked up once per run - the same cleaned error met by any trigger is asked once - as the section a
    request carries; "" when nothing was found. Each note shown is a ledger record with its id and the defect it was
    for, the first as a lookup, each later one as shown again (`app.observability.lookup_notes`, HK.4)."""
    from app.observability import lookup_notes
    from app.tools import lookups

    private = _the_private_words(repo_root)
    key = (str(repo_root), lookups.cleaned(error, private))
    if not key[1]:
        return ""
    if key in _DONE:
        shown, query = _DONE[key]
        if shown:
            lookup_notes.record(stage_name, {"query": query}, trigger=trigger, defect=defect, again=True)
        return shown
    answer = lookups.look_up(error, stack_words, private, repo_root=repo_root)
    shown = lookups.as_a_section(answer)
    shown = ("\n" + shown) if shown else ""
    _DONE[key] = (shown, str(answer.get("query") or ""))
    lookup_notes.record(stage_name, answer, trigger=trigger, defect=defect)
    return shown


def section(repo_root: str | Path, defect: Any, stack: Any, stage_name: str = "defect_fix") -> str:
    """T1: what others found for this stuck defect's error, as its fixer's request carries it; "" when off, not stuck,
    with no concrete error, or when nothing was found. Never raises."""
    try:
        if not enabled() or not _stuck(repo_root, defect):
            return ""
        from app.acceptance import mutation_guided

        if mutation_guided.is_a_finding(defect):
            return ""
        error = _the_error_line(defect)
        if not error:
            return ""
        return _looked_up(repo_root, error, _the_stack_s_words(stack), trigger=TRIGGER_STUCK, stage_name=stage_name,
                          defect=defect)
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


def for_an_install_that_failed(repo_root: str | Path, defect: Any, stack: Any, stage_name: str = "defect_fix") -> str:
    """T2: for the defect saying the project's dependencies do not install, what others found for the installer's
    error, from its first fix - unless the registry already explains it (a version or a feature that does not exist,
    for which the note carries the registry's answer). "" when off or not such a defect. Never raises."""
    try:
        if not enabled():
            return ""
        from app.stacks import contract

        said = str(getattr(defect, "actual_behavior", "") or "")
        if contract.INSTALL_FAILED not in said or contract.the_registry_explains(said):
            return ""
        error = _the_installer_s_error(said)
        if not error:
            return ""
        return _looked_up(repo_root, error, _the_installer_words(repo_root, stack), trigger=TRIGGER_INSTALL,
                          stage_name=stage_name, defect=defect)
    except Exception:  # noqa: BLE001 - the fix goes on without it
        logger.debug("Could not look up an install's error", exc_info=True)
        return ""


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
                          stage_name=stage_name)
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
                                sprint: int = 0, stage_name: str = "defect_fix", look_up: bool = True) -> str:
    """T3: when this defect reports a build or compile error the round before reported too, what others found for it,
    looked up with the stack's toolchain and version; "" when off, when the error is new this round, for a mutation
    finding, or with `look_up` false. Keeps this round's errors (of all `defects`) for the next round. Never raises."""
    try:
        if not enabled():
            return ""
        from app.acceptance import mutation_guided

        this_round = list(dict.fromkeys(
            signature for one in (defects or [defect]) if not mutation_guided.is_a_finding(one)
            for signature, _ in build_errors_in(_the_text_of(one))))
        before = set(_the_rounds(repo_root).get(f"{sprint}:{int(round_) - 1}") or [])
        _keep_the_round(repo_root, f"{sprint}:{int(round_)}", this_round)
        if not look_up or mutation_guided.is_a_finding(defect):
            return ""
        for signature, line in build_errors_in(_the_text_of(defect)):
            if signature in before:
                return _looked_up(repo_root, line, _the_toolchain_words(repo_root, stack), trigger=TRIGGER_RECURRING,
                                  stage_name=stage_name, defect=defect)
        return ""
    except Exception:  # noqa: BLE001 - the fix goes on without it
        logger.debug("Could not look up a recurring build error", exc_info=True)
        return ""


def for_a_fixer(repo_root: str | Path, defect: Any, defects: list[Any], stack: Any, *, round_: int, sprint: int = 0,
                stage_name: str = "defect_fix") -> str:
    """What others found for one fixer's defect, from the first trigger that applies: an install's error (T2), a build
    error the round before had too (T3), then the error of a defect an attempt left open (T1). One block, so a request
    carries one; "" when none applies or nothing was found. Never raises."""
    installing = for_an_install_that_failed(repo_root, defect, stack, stage_name)
    # Called whatever T2 found: it keeps this round's build errors for the next round.
    recurring = for_a_recurring_build_error(repo_root, defect, defects, stack, round_=round_, sprint=sprint,
                                            stage_name=stage_name, look_up=not installing)
    return installing or recurring or section(repo_root, defect, stack, stage_name)


__all__ = ["LOOKUP_EVENT", "ON_BY_DEFAULT", "ROUNDS_FILE", "TRIGGER_INSTALL", "TRIGGER_RECURRING", "TRIGGER_STUCK",
           "build_errors_in", "enabled", "for_a_failed_setup", "for_a_fixer", "for_a_recurring_build_error",
           "for_an_install_that_failed", "section"]
