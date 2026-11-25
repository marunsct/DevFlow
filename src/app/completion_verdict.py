"""Which of a release's completion gaps mean the product may not work, and which a reader should simply know.

Every gap used to make a finished run "non-deliverable", so every run with a gap read the same whether it
scored full marks or almost nothing, and the verdict said nothing. A gap is one of two things:

- **Blocking:** evidence the product fails, or a thing it promised that has no proof at all: a
  broken contract line, a defect a harness probe still finds, code that does not start, no suite, no way for someone
  else to run it. Which kinds block is calibrated on the hidden and quality tests (see `_NOTES`): a failing unit test
  of the product's own and a sprint an escalation accepted unfinished lost no more often than any run: notes.
- **A note:** the proof was weaker than it could be, or a worry was set aside, and every later measurement went on to
  pass: an unchecked contract line says nothing against the product, a design point is about a document, a change
  the suite did not notice may behave the same, a problem the suite was locked with was followed by a green suite.

- **A cut:** a criterion shipped deferred, unproven by the suite: stated to the reader as a scope cut (LR.21).
- **A known defect:** a major finding of the code review run after a sprint was accepted at an escalation, still open
  after its one fix pass (PQ.4): the product is delivered with known defects, not plain delivered.

Only the kinds listed here are notes or cuts; **a gap of any other kind blocks**, a new one included, because a false "not
deliverable" costs a reader a look and a false "deliverable" costs them a product that does not work. The split
changes what the verdict says and nothing the release checks or holds back. Notes stay in every record of the run.
"""
from __future__ import annotations

import re

#: The start of a gap saying a design review finding has a decision. It is not left open.
SETTLED_DESIGN_FINDING = "Design review finding settled by "

#: The start of a known issue for a code review's major finding still open after a sprint accepted at an escalation
#: had its one fix pass (PQ.4, `app.graph.review_after_escalation`), and of one that fix pass changed the code for.
OPEN_REVIEW_FINDING = "A code review's major finding is still open after the escalation:"
REVIEW_FINDING_GIVEN_A_FIX = "A code review's major finding had one fix pass after the escalation, not reviewed again:"
_AT_AN_ESCALATION = r"(?:An escalation left this open(?: \(DR-\d+\))?: )?"
_KNOWN_DEFECT = re.compile(_AT_AN_ESCALATION + re.escape(OPEN_REVIEW_FINDING))

#: Severity a milestone review gives a defect it says must not ship.
_BLOCKING_FINDING = re.compile(r"\[blocking\]", re.IGNORECASE)
_A_MILESTONE_RISK = "A milestone review's findings were recorded as risks"

_NOTES = re.compile(
    "|".join((
        # About the suite's own strength or history. The suite ran again at release and passed.
        r"\d+ locked test\(s\) were reclassified under dispute",  # a criterion left with no test is deferred, and blocks
        r"The suite was locked with this still open:",
        r"The locked suite did not notice the product changed:",
        r"No test holds the product to a behaviour a deliberate change showed:",
        # What was not checked: no reading against the product.
        r"\d+ line\(s\) of the interface contract were not checked at release",
        r"\d+ write line\(s\) of the interface contract were not asked with an unparsable body",
        r"The product ships no unit tests:",
        # Unit tests that kept failing beside a green locked suite, set aside and named (B6).
        r"\d+ unit test\(s\) were set aside, not raised as defects:",
        r"No review read the product's code:",
        # About the documents the product was built from, not the product.
        r"The plan was dispatched with this noted against it:",
        r"(An escalation left this open(?: \(DR-\d+\))?: )?" + re.escape(SETTLED_DESIGN_FINDING),
        r"An escalation left this open(?: \(DR-\d+\))?: Design review left open:",
        r"An escalation left this open(?: \(DR-\d+\))?: The sprint plan is ",
        # A major review finding the one fix pass after an escalation changed the code for (PQ.4): no review read it
        # again, so the reader is told, and the suite measured at release says whether the product works.
        _AT_AN_ESCALATION + re.escape(REVIEW_FINDING_GIVEN_A_FIX),
        # A sprint accepted unfinished whose tests the locked suite passes in full at release (LR.21).
        r"An escalation left this open(?: \(DR-\d+\))?: every locked test passes at release: ",
        # Worth knowing about what ships beside the product, or who judged it.
        r"Code the product does not run:",
        r"The product serves through a development server:",
        r"AC-\d+ was deferred during the run; its own locked tests pass at release:",
        r"CR-\d+ was deferred during the run; its own locked tests pass at release:",
        r"Ships \d+ dependenc(y|ies) under a strong-copyleft licence",
        # What the stack facts hold against what ships (HK.1): the suite that passed at release ran on it.
        r"A dependency its registry marks withdrawn ships:",
        r"A resolved package needs a newer toolchain than the one here:",
        # Advisories and support dates (HK.6, `app.stacks.advisories`): a package for development only does not ship;
        # a support window and a check that could not be made are for the reader. A shipped advisory blocks.
        r"A development-only dependency has a known advisory; it does not ship:",
        r"What the product runs on is past its end of support:",
        r"Advisories for what ships are not known:",
        r"The judgement model .* could not be built ",
        # What the intake assumed where the brief does not say (deep review C8): the reader is told, nothing failed.
        r"Assumed at intake where the brief does not say:",
        # A specialist's adopted item still not built after its one send-back (SP.1): the specification's promise is
        # stated unkept, but a specialist's reading of the code is no measure that the product fails - the suite,
        # measured at release, is. Not yet calibrated on the hidden tests; a note until it is.
        r"Adopted specialist advice still not built after its one send-back",
        # Calibrated on the hidden and quality tests (deep review 2026-11-18, item B4): 427 scored runs, 92 of them
        # (22%) lost a hidden or quality test, and a "not deliverable" verdict lost no more often than "delivered"
        # (39 of 181 against 53 of 246). Each kind of gap that blocked, the runs it was in, and how many lost one:
        #   kind                                                   runs  lost
        #   An escalation left a sprint open (re-planned, or its     105    18   (17%)  -> a note
        #     suite still failing), the locked suite green later
        #   An escalation left a brief requirement unbuilt            2     0          blocks (too few)
        #   N of the project's own unit tests still fail             94    22   (23%)  -> a note
        #   At release the product does not keep its contract        63    14   (22%; 5 of 9 with quality tests) blocks
        #   At release, reading the files still finds               19     4   (21%)  -> a note
        #   A milestone review's [blocking] finding as a risk        12     4   (33%)  blocks
        #   The project setup was never proven                       10     4   (40%)  blocks
        #   The product changed at release, the suite failed          3     1          blocks
        #   N write lines were not sent creates at once               1     0          -> a note (what went unasked)
        # A kind seen in 15 runs or more that lost no more often than all runs did predicts nothing and is a note; a
        # kind seen too seldom to say keeps blocking. A loss the verdict did not foresee is the probes' to find.
        r"An escalation left this open(?: \(DR-\d+\))?: (?:Sprint ['\"]|The sprint's own test suite was still failing)",
        r"\d+ of the project's own unit tests still fail and ship failing",
        r"At release, reading the files still finds:",
        r"\d+ write line\(s\) of the interface contract were not sent \d+ creates at once",
    ))
)


#: A criterion the release ships without proof, stated: a scope cut the reader is told about, not a sign the product
#: fails. Measured over the last 150 scored runs (LR.22): 29 runs shipped one or more deferred criteria, and none of
#: them lost a hidden test, while every one was marked non-deliverable beside runs that did lose one.
_CUTS = re.compile(r"(?:AC|CR)-\d+ ships deferred, unproven by the suite:")

#: The things a finished run can say about its product (LR.21; known defects PQ.4).
DELIVERED, DELIVERED_WITH_CUTS, NOT_DELIVERABLE = "delivered", "delivered_with_cuts", "not_deliverable"
DELIVERED_WITH_KNOWN_DEFECTS = "delivered_with_known_defects"


def is_a_cut(gap: str) -> bool:
    """Whether this gap is a stated scope cut: a criterion shipped deferred, unproven by the suite."""
    return _CUTS.match(str(gap).lstrip()) is not None


def is_a_known_defect(gap: str) -> bool:
    """Whether this gap is a code review's major finding still open after an escalation's one fix pass (PQ.4)."""
    return _KNOWN_DEFECT.match(str(gap).lstrip()) is not None


def verdict(gaps: list[str] | None) -> str:
    """What a finished run's gaps say about its product: not deliverable, delivered with known defects, delivered with
    cuts, or delivered."""
    texts = [str(gap) for gap in gaps or []]
    if any(is_blocking(gap) for gap in texts):
        return NOT_DELIVERABLE
    if any(is_a_known_defect(gap) for gap in texts):
        return DELIVERED_WITH_KNOWN_DEFECTS
    return DELIVERED_WITH_CUTS if any(is_a_cut(gap) for gap in texts) else DELIVERED


def is_blocking(gap: str) -> bool:
    """Whether this gap means the product may not work. An unknown kind does; a stated scope cut or a known defect,
    named to the reader as such, does not."""
    text = str(gap).lstrip()
    if is_a_cut(text) or is_a_known_defect(text):
        return False
    if text.startswith(_A_MILESTONE_RISK):
        return bool(_BLOCKING_FINDING.search(text))
    return _NOTES.match(text) is None


def split(gaps: list[str] | None) -> tuple[list[str], list[str]]:
    """(the gaps that block, the notes), each in the order given; none is lost."""
    texts = [str(gap) for gap in gaps or []]
    return [gap for gap in texts if is_blocking(gap)], [gap for gap in texts if not is_blocking(gap)]


__all__ = ["DELIVERED", "DELIVERED_WITH_CUTS", "DELIVERED_WITH_KNOWN_DEFECTS", "NOT_DELIVERABLE", "OPEN_REVIEW_FINDING",
           "REVIEW_FINDING_GIVEN_A_FIX", "SETTLED_DESIGN_FINDING", "is_a_cut", "is_a_known_defect", "is_blocking", "split",
           "verdict"]
