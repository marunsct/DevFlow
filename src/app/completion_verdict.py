"""Which of a release's completion gaps mean the product may not work, and which a reader should simply know.

Every gap used to make a finished run "non-deliverable", so every run with a gap read the same whether it
scored full marks or almost nothing, and the verdict said nothing. A gap is one of two things:

- **Blocking:** evidence the product fails, or a thing it promised that has no proof at all: a deferred criterion, a
  failing unit test, a broken contract line, code that does not start, no suite, no way for someone else to run it.
- **A note:** the proof was weaker than it could be, or a worry was set aside, and every later measurement went on to
  pass: an unchecked contract line says nothing against the product, a design point is about a document, a change
  the suite did not notice may behave the same, a problem the suite was locked with was followed by a green suite.

Only the kinds listed here are notes; **a gap of any other kind blocks**, a new one included, because a false "not
deliverable" costs a reader a look and a false "deliverable" costs them a product that does not work. The split
changes what the verdict says and nothing the release checks or holds back. Notes stay in every record of the run.
"""
from __future__ import annotations

import re

#: The start of a gap saying a design review finding has a decision. It is not left open.
SETTLED_DESIGN_FINDING = "Design review finding settled by "

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
        r"No review read the product's code:",
        # About the documents the product was built from, not the product.
        r"The plan was dispatched with this noted against it:",
        r"(An escalation left this open: )?" + re.escape(SETTLED_DESIGN_FINDING),
        r"An escalation left this open: Design review left open:",
        r"An escalation left this open: The sprint plan is ",
        # Worth knowing about what ships beside the product, or who judged it.
        r"Code the product does not run:",
        r"Ships \d+ dependenc(y|ies) under a strong-copyleft licence",
        r"The judgement model .* could not be built ",
    ))
)


def is_blocking(gap: str) -> bool:
    """Whether this gap means the product may not work. An unknown kind does."""
    text = str(gap).lstrip()
    if text.startswith(_A_MILESTONE_RISK):
        return bool(_BLOCKING_FINDING.search(text))
    return _NOTES.match(text) is None


def split(gaps: list[str] | None) -> tuple[list[str], list[str]]:
    """(the gaps that block, the notes), each in the order given; none is lost."""
    texts = [str(gap) for gap in gaps or []]
    return [gap for gap in texts if is_blocking(gap)], [gap for gap in texts if not is_blocking(gap)]


__all__ = ["SETTLED_DESIGN_FINDING", "is_blocking", "split"]
