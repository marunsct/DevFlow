"""The brief's own technical constraints, for the stage that chooses the stack.

Run 0c5aabdb chose `Express` with `JSON File Storage` for a brief whose
Technical Constraints section reads, in full:

    - Single-page application
    - No external dependencies beyond basic HTML/CSS/JS

Its rationale argued for `node --test` because it "does not add external
packages", in the same paragraph that added Express. The technical lead then
delegated "Create package.json ... add minimal dependencies: express", and the
backend specialist built a server, all of it correct work downstream of a
decision that had already contradicted the brief.

Nothing in the workflow was wrong except what the stage could see.
`stack_selector_node` is given `product_intake` and `tools_models` - both
derived - and `ProductManagerOutput.constraints` came back empty, as it may:
the field exists and the model simply did not fill it. The brief itself was
never in the room when the stack was chosen.

So the constraints travel separately, taken from the document rather than from
a model's summary of it, and they are short: a handful of lines that would
otherwise be paraphrased away.

Nothing here decides anything. It selects text and hands it over, because a
constraint the deciding stage never reads cannot be honoured by any prompt
written for it. `app.analysis.integration_checks` catches what is built
against a stack; this is about the stack itself.
"""

from __future__ import annotations

import re

#: Headings whose body states what the product may and may not be built with.
#: Matched on the heading text, so any level of `#` and any trailing colon.
_CONSTRAINT_HEADINGS = (
    "technical constraints",
    "constraints",
    "non-functional requirements",
    "technical requirements",
    "out of scope",
    "restrictions",
    "limitations",
)

#: A markdown heading, with its level and its text.
_HEADING = re.compile(r"^(#{1,6})\s*(.+?)\s*:?\s*$", re.M)

#: Lines that state a restriction even outside a constraints heading. Kept
#: narrow deliberately: a sentence about what the product must NOT use is the
#: one a stack decision can contradict, and anything broader sweeps in the
#: feature list.
_A_RESTRICTION = re.compile(
    r"""^\s*[-*]?\s*([^\n]*\b(?:no|without|avoid|must not|do not|don't|"""
    r"""zero|none|only|single|plain|vanilla)\b[^\n]*"""
    r"""\b(?:dependenc|framework|librar|package|server|backend|build|"""
    r"""bundler|database|tooling|npm|install|runtime)[^\n]*)$""",
    re.M | re.I,
)

#: How much to carry. The point is the constraints, not the brief.
MAX_CONSTRAINT_LINES = 12


def _section_under(text: str, heading: re.Match[str]) -> str:
    """The body below `heading`, ending at the next heading of the same level."""
    level = len(heading.group(1))
    start = heading.end()
    for following in _HEADING.finditer(text, start):
        if len(following.group(1)) <= level:
            return text[start : following.start()]
    return text[start:]


def constraint_lines(document_text: str) -> list[str]:
    """The brief's technical constraints, as the lines that state them.

    Sections first, because a brief that has a constraints heading has said
    where they are. The loose pattern then adds restrictions stated elsewhere -
    run 0c5aabdb's brief also says "Single-page application" under a heading
    this would find, but other briefs bury the same thing in an overview.
    """
    if not document_text:
        return []

    found: list[str] = []
    seen: set[str] = set()

    def keep(line: str) -> None:
        cleaned = line.strip().lstrip("-*").strip()
        if not cleaned or len(cleaned) > 300:
            return
        key = cleaned.lower()
        if key in seen:
            return
        seen.add(key)
        found.append(cleaned)

    for heading in _HEADING.finditer(document_text):
        if heading.group(2).strip().lower().rstrip(":") not in _CONSTRAINT_HEADINGS:
            continue
        for line in _section_under(document_text, heading).splitlines():
            keep(line)

    for match in _A_RESTRICTION.finditer(document_text):
        keep(match.group(1))

    return found[:MAX_CONSTRAINT_LINES]


#: What to do about a conflict, which differs by who is reading. The stage
#: choosing picks again; the stage reviewing blocks. A single sentence telling
#: a reviewer to "pick the one it leaves" would be telling it to do the job of
#: the stage it is reviewing.
_REMEDY = {
    "choosing": (
        "If a constraint rules out the technology you would otherwise pick, "
        "pick the one it leaves."
    ),
    "reviewing": (
        "A specification that contradicts one of these is a blocking finding, "
        "however well argued it is - say which constraint and require the "
        "change. You are the last gate before anything is built."
    ),
}


def constraints_note(document_text: str, reader: str = "choosing") -> str:
    """The constraints as a block for a prompt, or "" when the brief states none.

    `reader` is "choosing" for the stage picking the stack and "reviewing" for
    the one reviewing what it produced; it selects the closing sentence only.
    """
    lines = constraint_lines(document_text)
    if not lines:
        return ""
    body = "\n".join(f"- {line}" for line in lines)
    return (
        "--- Technical constraints, quoted from the brief ---\n"
        f"{body}\n\n"
        "These are the author's words, not a summary of them. A decision that "
        "contradicts one of these is the wrong decision however good it would "
        "otherwise be: every later stage builds what it allows, and none of "
        f"them reads the brief again. {_REMEDY.get(reader, _REMEDY['choosing'])}\n\n"
    )




#: Phrases that mean the product is meant to be opened in a browser. Narrow
#: deliberately: this drives a blocking finding, and a brief that never says
#: any of these must produce none.
_WANTS_A_PAGE = (
    "html",
    "web-based interface",
    "web interface",
    "single-page",
    "single page application",
    "in the browser",
    "modern browsers",
    "web page",
    "webpage",
    "front-end",
    "frontend",
)

#: And that it is meant to be styled.
_WANTS_STYLING = ("css", "responsive", "styling", "stylesheet")


def what_the_brief_asked_for_that_is_missing(
    document_text: str, project_files: list[str]
) -> list[str]:
    """Requirements the brief states plainly that the product does not have.

    Run 0c5aabdb completed. Its architecture review returned "approved" with no
    findings, both security reviews "passed", and the milestone review raised
    one blocking finding - a missing npm test script - then "accepted". What it
    delivered was:

        simple-to-do-list-app/index.js            616 bytes, an Express server
        simple-to-do-list-app/app.test.js
        simple-to-do-list-app/index.test.js
        simple-to-do-list-app/package-lock.json   32,693 bytes

    No HTML. No CSS. No front-end JavaScript. The brief's first requirement is
    "Simple web-based interface with HTML/CSS/JavaScript" and its constraints
    are "Single-page application" and "No external dependencies beyond basic
    HTML/CSS/JS".

    Every gate passed because every gate reviews the artifacts against each
    other and against the milestone's own goal. The brief enters at the product
    manager and is never read again, so nothing in the run was in a position to
    notice that the product it accepted has no user interface.

    Only the two requirements that can be checked without judgement: a brief
    that asks for a page, and a product with no page in it; a brief that asks
    for styling, and nothing that styles. Everything else about "does this meet
    the brief" is a reading, and belongs to the reviewer that now gets the text.
    """
    low = (document_text or "").lower()
    names = [name.lower() for name in project_files]
    missing: list[str] = []

    if any(phrase in low for phrase in _WANTS_A_PAGE):
        if not any(name.endswith((".html", ".htm")) for name in names):
            missing.append(
                "The brief asks for a web interface, and the product contains no "
                "HTML file. There is nothing for a user to open. Whatever else "
                "works, the product described has not been built."
            )
        elif any(phrase in low for phrase in _WANTS_STYLING) and not any(
            name.endswith(".css") for name in names
        ):
            missing.append(
                "The brief asks for styling, and the product contains no "
                "stylesheet. Check that the page carries its own `<style>`; if "
                "it does not, the interface is unstyled."
            )
    return missing


__all__ = [
    "MAX_CONSTRAINT_LINES",
    "constraint_lines",
    "constraints_note",
    "what_the_brief_asked_for_that_is_missing",
]
