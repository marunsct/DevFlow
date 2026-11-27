"""Review findings survive an escalation (PQ.4, always on).

A sprint the escalation accepts as it stands, or with its failing criteria deferred, goes straight to the next sprint
or the release: the security, specialist and milestone reviews come after a green suite, and fast delivery leaves the
code review out. Measured across 146 scored runs, 82 sprints accepted at an escalation shipped code no review read
("No review read the product's code ... accepted at an escalation"), and on the 2026-11-25 product-quality audit
(cause C3) the code review's major findings on such a sprint reached neither a fixer nor the release.

So when a sprint is accepted at an escalation, the code review is still asked, once and bounded:

- **one review call**, with no tools and no say over the run: the sprint's diff since the last accepted sprint (at
  most `DIFF_CHARACTERS`), its work orders and criteria, and what the specification adopted (`code_reviewer`);
- **one fix pass** on its blocking and major findings that name a file (at most `MOST_FINDINGS` findings in
  `MOST_FILES` files): one rewrite per file (`rewritten_fixes.fix_by_rewriting`), measured once with the harness's
  usual guard (`engineering.after_a_fix`), which puts the whole pass back if it broke what passed;
- **the delivery notes**: each major finding becomes a known issue - "given one fix pass, not reviewed again" when the
  pass changed its file and was kept, "still open" otherwise - and a product with one still open is delivered with
  known defects (`completion_verdict.DELIVERED_WITH_KNOWN_DEFECTS`), not plain delivered.

Its findings rest on the product, not on what the diff happens to show (LF.1645). The ordinary code review has tools
and its project memory holds the changed files whole; this one call has neither. Measured on its first live review: a
"blocking" finding said a stylesheet's import was "not present in the provided changes" while an unchanged entry file
imported it; the fix pass added a second import, and a finding about a unit test file's strength made a product whose
hidden tests all passed "delivered with known defects". So:

- the request carries every line of the product's code that names a changed file (`uses_of_the_changed_files`, at most
  `USES_CHARACTERS`), and the review is told that absence from the diff is not absence from the product;
- a finding that a named file is not imported, included, linked or referenced, where the product's code does name it,
  is set aside before the fix pass (`contradicted`), and the decision says which line contradicts it;
- a finding in one of the product's test files is a note for the reader (`completion_verdict.REVIEW_FINDING_ON_TESTS`),
  not a known defect and not given the fix pass: the suite measured at release says whether the product works.

What it costs, only on a sprint accepted at an escalation: one judgement-model call; and, only when it finds a major
finding in a named file, at most three build-model rewrite calls and the two measurements every fix has. Never raises:
a review that cannot be asked leaves the acceptance as it was.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Mapping

from app.completion_verdict import OPEN_REVIEW_FINDING, REVIEW_FINDING_GIVEN_A_FIX, REVIEW_FINDING_ON_TESTS
from app.observability.degraded import degraded

logger = logging.getLogger(__name__)

#: The decision the review is recorded under; `delivery._code_no_review_read` reads it as a review having read the code.
DECISION_POINT = "code_review_after_escalation"
#: The fix pass's stage name, for its measurement and its commit.
FIX_STAGE = "defect_fix_after_escalation"
#: The most of the sprint's diff the one review call reads.
DIFF_CHARACTERS = 40_000
#: The most the review's reply may run.
REPLY_TOKENS = 16_000
#: Blocking or major findings carried, and files the one fix pass rewrites, at most.
MOST_FINDINGS = 6
MOST_FILES = 3
#: The most characters of the lines that name a changed file the request carries (`uses_of_the_changed_files`).
USES_CHARACTERS = 6_000
#: How the request heads those lines.
USES_HEADING = ("--- Where the product's code names the changed files, as the files are now (file:line), changed or "
                "not ---")


@dataclass
class Outcome:
    """What the review after an escalation found and what became of it.

    `findings` are the product's major findings (the fix pass and the known defects); `on_tests` the major findings in
    the product's own test files (notes); `set_aside` each finding the product's files contradict, with the line that
    does."""

    findings: list[Any] = field(default_factory=list)
    fixed_files: list[str] = field(default_factory=list)
    put_back: list[str] = field(default_factory=list)
    on_tests: list[Any] = field(default_factory=list)
    set_aside: list[tuple[Any, str]] = field(default_factory=list)

    def known_issues(self) -> list[str]:
        return known_issues(self.findings, self.fixed_files) + known_issues(self.on_tests, [], on_tests=True)

    def decision(self) -> str:
        said = []
        if self.on_tests:
            said.append(f"{len(self.on_tests)} about the product's own tests, a note")
        if self.set_aside:
            said.append(f"{len(self.set_aside)} set aside, the product's files contradict it")
        if not self.findings:
            return "; ".join(["reviewed after the escalation: no major finding in the product", *said])
        open_ = len(self.findings) - sum(1 for f in self.findings if _the_file(f) in self.fixed_files)
        return "; ".join([f"reviewed after the escalation: {len(self.findings)} major finding(s), "
                          f"{len(self.findings) - open_} given one fix pass, {open_} still open", *said])


def _the_file(finding: Any) -> str:
    return str(getattr(finding, "file", "") or "").strip().lstrip("/")


def major_findings(review: Any, later: Callable[[str], Any] = lambda text: []) -> list[Any]:
    """The review's blocking and major findings, less those about a later sprint's criteria; at most `MOST_FINDINGS`."""
    found = [finding for finding in getattr(review, "findings", None) or []
             if str(getattr(finding, "severity", "")) in ("blocking", "major")
             and not later(f"{getattr(finding, 'problem', '')} {getattr(finding, 'fix', '') or ''}")]
    return found[:MOST_FINDINGS]


def known_issues(findings: list[Any], fixed_files: list[str], on_tests: bool = False) -> list[str]:
    """One known issue per major finding: given one fix pass when its file was rewritten and kept, else still open;
    with `on_tests`, a note about the product's own tests."""
    lines = []
    for finding in findings:
        where = _the_file(finding) or "no file named"
        said = " ".join(str(getattr(finding, "problem", "") or "").split())[:400]
        order = str(getattr(finding, "work_order", "") or "").strip()
        prefix = REVIEW_FINDING_ON_TESTS if on_tests else REVIEW_FINDING_GIVEN_A_FIX \
            if _the_file(finding) and _the_file(finding) in fixed_files else OPEN_REVIEW_FINDING
        lines.append(f"{prefix} `{where}`{f' ({order})' if order else ''}: {said}")
    return lines


def on_the_tests(finding: Any) -> bool:
    """Whether the finding is in one of the product's own test files: about the suite's strength, not the product."""
    from app.analysis.file_kinds import is_test

    return bool(_the_file(finding)) and is_test(_the_file(finding))


def _references(changed: Iterable[str]) -> list[tuple[str, re.Pattern[str]]]:
    """For each changed file, what names it in code: its file name, or its stem written as a path or module part
    (`./App.js`, `'./App'`, `app.store`)."""
    found = []
    for path in changed:
        name = PurePosixPath(str(path or "").strip().lstrip("/")).name
        if not name:
            continue
        stem = PurePosixPath(name).stem
        forms = [re.escape(name)]
        if len(stem) >= 3 and stem != name:
            forms.append(rf"(?<=[/.'\"]){re.escape(stem)}(?=['\"/.;)\s]|$)")
        found.append((str(path).strip().lstrip("/"), re.compile(rf"(?<![\w-])(?:{'|'.join(forms)})(?![\w-])")))
    return found


def uses_of_the_changed_files(changed: Iterable[str], sources: Mapping[str, str],
                              most: int = USES_CHARACTERS) -> str:
    """Each line of the product's code (`sources`, path to text) that names a changed file, as `file:line: text`; at
    most `most` characters; "" when none does. A file naming itself is not a use."""
    named = _references(changed)
    if not named:
        return ""
    lines: list[str] = []
    size = 0
    for path in sorted(sources):
        for number, line in enumerate(str(sources[path]).splitlines(), start=1):
            if len(line) > 400 or not any(pattern.search(line) for changed_path, pattern in named
                                          if changed_path != path):
                continue
            entry = f"{path}:{number}: {line.strip()}"
            if size + len(entry) + 1 > most:
                lines.append("... (more lines name the changed files; not shown)")
                return "\n".join(lines)
            lines.append(entry)
            size += len(entry) + 1
    return "\n".join(lines)


#: A file named in prose, as `names_a_file` reads one: a name with an extension.
_A_FILE_NAMED = re.compile(r"(?<![\w@-])[\w@.-]*[\w-]\.[A-Za-z][A-Za-z0-9]{0,5}(?![\w-])")
#: Words for how code takes in, includes or links a file.
_TAKEN_IN = r"(?:import(?:s|ed|ing)?|includ(?:e|es|ed|ing)|link(?:s|ed|ing)?|referenc(?:e|es|ed|ing))"
#: A claim that a file is not taken in: "is not imported", "does not import", "never linked", "missing import of";
#: or "the import of X ... is not present", "... is missing", "absent".
_NOT_TAKEN_IN = re.compile(
    rf"(?:\b(?:not|never|no|missing|without)|n't)\s+(?:\w+\s+){{0,2}}?(?P<word>{_TAKEN_IN})\b"
    rf"|\b(?P<noun>{_TAKEN_IN})\s+(?:of|for|to)\b[^;]*?\b(?:not present|missing|absent|not found|nowhere)\b",
    re.I)


def contradicted(finding: Any, sources: Mapping[str, str]) -> str:
    """The product's line that contradicts a finding's claim that a named file is not imported, included, linked or
    referenced, as `file:line`; "" when the finding claims no such absence or nothing in `sources` names that file.

    The file a claim is about is the named file nearest its word for taking a file in, in the same sentence. Only the
    finding's problem is read: its fix says what to add, not what is missing."""
    from app.analysis.file_kinds import names_a_file

    problem = " ".join(str(getattr(finding, "problem", "") or "").split())
    for sentence in re.split(r"(?<=[.;!?])\s+", problem):
        taken_in = [match.span("word") if match.group("word") else match.span("noun")
                    for match in _NOT_TAKEN_IN.finditer(sentence)]
        if not taken_in:
            continue
        files = [match for match in _A_FILE_NAMED.finditer(sentence) if names_a_file(match.group(0).rstrip("."))]
        if not files:
            continue
        nearest = min(files, key=lambda match: min(max(start - match.end(), match.start() - end, 0)
                                                   for start, end in taken_in))
        name = nearest.group(0).rstrip(".")
        use = uses_of_the_changed_files([name], {path: text for path, text in sources.items()
                                                 if PurePosixPath(path).name != PurePosixPath(name).name}, most=400)
        if use:
            return use.splitlines()[0].split(": ", 1)[0]
    return ""


def files_to_fix(findings: list[Any], root: str | Path) -> list[str]:
    """The files the findings name that are in the workspace, in the order first named; at most `MOST_FILES`."""
    files: list[str] = []
    for finding in findings:
        name = _the_file(finding)
        if name and name not in files and (Path(root) / name).is_file():
            files.append(name)
    return files[:MOST_FILES]


def the_review(model: Any, request: str) -> Any:
    """The code review asked in one call with no tools; its `CodeReviewOutput`, or None when the reply holds none."""
    from langchain_core.messages import HumanMessage, SystemMessage

    from app.agents.answered_in_parts import _read
    from app.agents.code_reviewer import ONE_CALL_SYSTEM_PROMPT, CodeReviewOutput
    from app.models.reply_text import reply_text
    from app.observability.direct_calls import config_for_this_run

    reply = model.invoke([SystemMessage(content=ONE_CALL_SYSTEM_PROMPT), HumanMessage(content=request)],
                         max_tokens=REPLY_TOKENS, **config_for_this_run(DECISION_POINT))
    return _read(reply_text(reply), CodeReviewOutput)


def with_the_uses(request: str, uses: str) -> str:
    """The request with the lines that name the changed files, ahead of its closing line; as it was when none."""
    if not uses.strip():
        return request
    section, closing = f"{USES_HEADING}\n{uses}\n\n", "Review the batch."
    if request.endswith(closing):
        return request[:-len(closing)] + section + closing
    return f"{request}\n\n{section}".rstrip()


def _the_request(state: Any, root: str, diff: str, uses: str = "") -> str:
    from app.acceptance import suite
    from app.acceptance.requests import criteria_text
    from app.agents.code_reviewer import build_code_review_request, the_standards
    from app.agents.shared_facts import with_the_facts
    from app.graph import engineering
    from app.graph.acceptance_nodes import criteria_due

    due = set(criteria_due(state) or [])
    criteria = criteria_text([c for c in suite.criteria(root) if not due or c.id in due])
    orders = "\n".join(
        f"- {engineering._title(order)} ({order.specialist_role}): {getattr(order, 'task_description', '')[:400]}"
        for order in engineering._tasks(state)
    )
    request = build_code_review_request(
        diff, orders, criteria,
        "The sprint was accepted at an escalation: its fixes and re-plans ran out with this still failing. "
        + str(state.get("ci_report") or ""),
        engineering._later_sprints(state), standards=the_standards(state.get("technical_specification")))
    request["messages"][-1]["content"] = with_the_uses(request["messages"][-1]["content"], uses)
    return str(with_the_facts(request, root)["messages"][-1]["content"])


def _a_rewrite(state: Any, root: str, model: Any) -> Callable[[Any, str], list[str]]:
    from app.graph.rewritten_fixes import fix_by_rewriting

    def rewrite(defect: Any, path: str) -> list[str]:
        output = fix_by_rewriting(
            defect, root, model, specification=state.get("technical_specification"),
            stack=getattr(state.get("stack_selection"), "technology_stack", None), files=[path])
        return list(getattr(output, "changed_files", None) or [])

    return rewrite


def _the_defect(state: Any, path: str, findings: list[Any]) -> Any:
    from app.agents.specialists import ReportedDefect
    from app.graph import engineering

    problems = "; ".join(" ".join(str(f.problem).split()) for f in findings)
    fixes = "; ".join(" ".join(str(f.fix).split()) for f in findings if str(f.fix or "").strip())
    return ReportedDefect(
        description=f"Code review after the escalation, in {path}: {problems}"[:1_500],
        severity="major",
        reproduction_steps=f"Read {path}: the code review found this in the sprint the escalation accepted.",
        expected_behavior=fixes or "What the work order asked for.",
        actual_behavior=problems,
        affected_files=[path],
        owner=engineering._owner_of(state, str(findings[0].work_order or "")),
    )


def fix_pass(state: Any, root: str, findings: list[Any], rewrite: Callable[[Any, str], list[str]],
             measure: tuple[Callable[[], str], Callable[[str], list[str]]] | None = None) -> tuple[list[str], list[str]]:
    """One rewrite per file the findings name, measured once; (the files it changed and kept, what it broke).

    `measure` is (before, after) of the harness's fix guard (`engineering.before_a_fix` / `after_a_fix`): a pass that
    broke what passed before it is put back whole, and its findings stay open.
    """
    files = files_to_fix(findings, root)
    if not files:
        return [], []
    if measure is None:
        from app.graph import engineering

        measure = (lambda: engineering.before_a_fix(root, FIX_STAGE),
                   lambda base: engineering.after_a_fix(root, base, FIX_STAGE,
                                                        "major code review findings after an escalation"))
    base = measure[0]()
    changed: list[str] = []
    for path in files:
        for name in rewrite(_the_defect(state, path, [f for f in findings if _the_file(f) == path]), path):
            if name not in changed:
                changed.append(name)
    if not changed:
        return [], []
    broken = measure[1](base)
    if broken:
        logger.warning("The fix pass after the escalation broke %d test(s); put back", len(broken))
        return [], broken
    return changed, []


def sorted_out(findings: list[Any], sources: Mapping[str, str]) -> Outcome:
    """The major findings as the fix pass and the release take them: each the product's code contradicts set aside,
    each in a test file a note, the rest the product's."""
    outcome = Outcome()
    for finding in findings:
        against = contradicted(finding, sources)
        if against:
            outcome.set_aside.append((finding, against))
        elif on_the_tests(finding):
            outcome.on_tests.append(finding)
        else:
            outcome.findings.append(finding)
    return outcome


def review_and_fix(state: Any, judge: Any, builder: Any) -> Outcome | None:
    """The review after a sprint accepted at an escalation, and its one fix pass; None when no review could be asked."""
    if judge is None or not hasattr(judge, "invoke"):
        # Said, not silent (LF.1644): no stored transcript held this review's call while the release blamed routing.
        degraded("review_after_escalation", None, why="no model to ask")
        return None
    try:
        from app import ci

        root = state["repository"].root_path
        accepted = ci.load(root, "accepted")
        since = (accepted.commit if accepted else "") or ci.first_commit(root)
        ci.commit(root, "The sprint as the escalation accepted it")
        diff = ci.diff_since(root, since, max_chars=DIFF_CHARACTERS)
        if not diff.strip():
            return None
        from app.graph.unfinished_build import product_sources

        sources = product_sources(root)
        uses = uses_of_the_changed_files(ci.changed_since(root, since), sources)
        review = the_review(judge, _the_request(state, root, diff, uses))
        if review is None:
            logger.warning("The code review after the escalation gave no readable answer")
            degraded("review_after_escalation", None, why="no readable answer")
            return None
        from app.graph.acceptance_nodes import criteria_only_later

        outcome = sorted_out(major_findings(review, lambda text: criteria_only_later(state, text)), sources)
        if outcome.findings and builder is not None:
            outcome.fixed_files, outcome.put_back = fix_pass(state, root, outcome.findings,
                                                             _a_rewrite(state, root, builder))
        logger.info("Code review after the escalation: %s", outcome.decision())
        return outcome
    except Exception as error:  # noqa: BLE001 - the acceptance stands as it was
        from app.models.call_gate import raise_if_the_run_stopped

        raise_if_the_run_stopped(error)
        degraded("review_after_escalation", error)
        return None


def recorded(state: Any, update: dict[str, Any], outcome: Outcome | None) -> list[str]:
    """Record the review's decision on `update`; the known issues it leaves for the release. [] when none ran."""
    if outcome is None:
        return []
    from app.decisions import record_decision

    lines = outcome.known_issues()
    set_aside = [f"Set aside, `{against}` contradicts it: `{_the_file(finding) or 'no file named'}`: "
                 + " ".join(str(getattr(finding, "problem", "") or "").split())[:400]
                 for finding, against in outcome.set_aside]
    record_decision(
        state, update, point=DECISION_POINT,
        question="The escalation accepted the sprint: what does a code review find in it?",
        options=["fix the major findings once and name them at release"],
        decision=outcome.decision(),
        rationale=("\n".join([*lines, *set_aside]) or "The review found no blocking or major problem.")
        + (f"\nThe fix pass was put back: it broke {'; '.join(outcome.put_back[:3])}" if outcome.put_back else ""),
    )
    return lines


__all__ = ["DECISION_POINT", "DIFF_CHARACTERS", "FIX_STAGE", "MOST_FILES", "MOST_FINDINGS", "USES_CHARACTERS",
           "USES_HEADING", "Outcome", "contradicted", "files_to_fix", "fix_pass", "known_issues", "major_findings",
           "on_the_tests", "recorded", "review_and_fix", "sorted_out", "the_review", "uses_of_the_changed_files",
           "with_the_uses"]
