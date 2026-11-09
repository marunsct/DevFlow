"""A rule the specification adds beyond the brief, on a subject the brief covers (behind `BRIEF_OVER_SPEC_ADDITIONS`).

Measured on one run: the architect added a rule about what a command prints, on a subject the brief had spoken to. The
review saw only the brief's constraint lines, so it had nothing to compare with; the tests followed the specification,
the code followed the tests, and a green suite held a product the brief's plain reading rejects. Each stage below the
specification treats it as the requirement, so this is the last place the addition can be seen as one.

So the design review is given the brief's text and asked to raise such an addition, which reaches the architect's
revision as any finding does, and QA is told a test of one is a choice. These are prompt rules: no unit test can show
a model obeys them, so this stays off until runs have measured it.
"""

from __future__ import annotations

from app.switches import is_on

#: `BRIEF_OVER_SPEC_ADDITIONS` set to on or off overrides this; off until measured.
ON_BY_DEFAULT = False
#: What the admin page says this switch does.
explanation = (
    "The design review is given the brief's text and raises any rule the specification adds to observable behaviour on "
    "a subject the brief covers; QA is told a test of such a rule is a choice, and that the brief's plainer reading stands."
)

#: The most of the brief the review is handed. Briefs are short; this is a ceiling.
MOST_BRIEF_CHARS = 12_000

HEADING = "--- What the specification adds beyond the brief ---"

QA_RULE = (
    "- A test that asserts something the brief does not say, about a subject the brief does cover, is a choice, even "
    "where the specification says it. Where the brief's own words suggest a plainer reading, the plainer reading stands: "
    "the test holds the product to that, and leaves out what the specification added.\n"
)


def enabled() -> bool:
    return is_on("BRIEF_OVER_SPEC_ADDITIONS", ON_BY_DEFAULT)


def review_section(brief: str) -> str:
    """What the design review is given to compare the specification with; "" when off or there is no brief."""
    text = str(brief or "").strip()
    if not enabled() or not text:
        return ""
    return (
        f"\n{HEADING}\n"
        f"The brief, as the customer wrote it:\n{text[:MOST_BRIEF_CHARS]}\n\n"
        "Where the brief speaks to a subject - what the user is shown, in what form, what an action does - read what the "
        "specification says of that same subject. A rule it adds there, one that changes what can be observed beyond what "
        "the brief says, is a major finding: quote the brief's line and the specification's rule, and the remediation is "
        "to drop the rule or to state it as the brief does. Where the brief's own words suggest a plainer reading, the "
        "plainer reading stands, however reasonable the addition looks; every later stage treats the specification as the "
        "requirement, so nothing after this review will question it.\n"
        "A rule on a subject the brief does not speak to is a design choice and no finding. So is the detail needed to "
        "carry out what the brief says, and anything the setup decides.\n"
    )


def qa_rule() -> str:
    """The line in QA's rules; "" when off."""
    return QA_RULE if enabled() else ""


__all__ = ["HEADING", "ON_BY_DEFAULT", "QA_RULE", "enabled", "explanation", "qa_rule", "review_section"]
