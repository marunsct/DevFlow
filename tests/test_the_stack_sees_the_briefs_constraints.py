"""The stage that picks the stack reads the brief's constraints.

One run chose `Express` with `JSON File Storage` for a brief whose
Technical Constraints section reads, in full:

    - Single-page application
    - No external dependencies beyond basic HTML/CSS/JS

Its rationale argued for `node --test` because it "does not add external
packages", in the same paragraph that added Express. The technical lead then
delegated "Create package.json ... add minimal dependencies: express", and the
backend specialist built a server - all correct work downstream of a decision
that had already contradicted the brief.

Nothing was wrong except what the stage could see. `stack_selector_node` was
given `product_intake` and `tools_models`, both derived, and that run's
`ProductManagerOutput.constraints` came back empty - the field exists and the
model simply did not fill it. The brief was never in the room.
"""

import inspect

from app.agents.brief_constraints import (
    MAX_CONSTRAINT_LINES,
    constraint_lines,
    constraints_note,
)

BRIEF_LOW = """# Product Brief: Simple To-Do List App

## Requirements
1. **User Interface**: Simple web-based interface
2. **Data Storage**: Local storage or simple JSON file

## Technical Constraints
- Single-page application
- No external dependencies beyond basic HTML/CSS/JS
- Should work in modern browsers
- Maximum 500 lines of code
"""


def test_the_measured_constraint_is_found():
    lines = constraint_lines(BRIEF_LOW)

    assert "No external dependencies beyond basic HTML/CSS/JS" in lines
    assert "Single-page application" in lines


def test_the_requirements_are_not_swept_in():
    """The feature list is not a constraint; carrying it would drown them."""
    lines = constraint_lines(BRIEF_LOW)

    assert not any("User Interface" in line for line in lines)


def test_a_brief_with_no_constraints_section_says_nothing():
    assert constraint_lines("# A Brief\n\nBuild a thing.\n") == []
    assert constraints_note("# A Brief\n\nBuild a thing.\n") == ""


def test_a_restriction_outside_a_constraints_heading_is_found():
    """Not every brief puts them under a heading."""
    lines = constraint_lines("# Brief\n\nBuild it with no external dependencies at all.\n")

    assert any("no external dependencies" in line.lower() for line in lines)


def test_a_permissive_technical_section_is_carried_as_written():
    """The medium brief NAMES Express as allowed; the note must not invert that."""
    brief = "# Brief\n\n## Technical Requirements\n- Backend: Python/FastAPI or Node.js/Express\n"

    lines = constraint_lines(brief)

    assert lines == ["Backend: Python/FastAPI or Node.js/Express"]


def test_the_note_is_bounded():
    brief = "## Constraints\n" + "".join(f"- rule {i}\n" for i in range(40))

    assert len(constraint_lines(brief)) <= MAX_CONSTRAINT_LINES


def test_the_note_says_these_are_the_authors_words():
    """A summary is what was already failing; the point is that these are not."""
    note = constraints_note(BRIEF_LOW)

    assert "quoted from the brief" in note
    assert "not a summary" in note


def test_the_note_tells_the_choosing_stage_to_choose_again():
    assert "pick the one it leaves" in constraints_note(BRIEF_LOW)


def test_the_note_tells_the_reviewing_stage_to_block():
    """A reviewer told to "pick the one it leaves" would be doing the job of
    the stage it is reviewing."""
    note = constraints_note(BRIEF_LOW, reader="reviewing")

    assert "blocking finding" in note
    assert "pick the one it leaves" not in note


def test_an_unknown_reader_gets_the_choosing_wording():
    assert "pick the one it leaves" in constraints_note(BRIEF_LOW, reader="nonsense")


def test_the_architecture_reviewer_is_given_them():
    """The last gate before anything is built, which could not see the brief."""
    from app.agents.architecture_reviewer import build_architecture_review_request

    content = build_architecture_review_request("SPEC", "/repo", BRIEF_LOW)["messages"][0][
        "content"
    ]

    assert "No external dependencies beyond basic HTML/CSS/JS" in content
    assert "blocking finding" in content


def test_the_reviewer_without_a_brief_is_unchanged():
    content = build_architecture_review_request_content()

    assert "Technical constraints" not in content


def build_architecture_review_request_content():
    from app.agents.architecture_reviewer import build_architecture_review_request

    return build_architecture_review_request("SPEC", "/repo")["messages"][0]["content"]


def test_a_heading_ends_at_the_next_one_of_the_same_level():
    brief = "## Constraints\n- only vanilla JS\n\n## Features\n- add tasks\n- delete tasks\n"

    lines = constraint_lines(brief)

    assert "only vanilla JS" in lines
    assert not any("add tasks" in line for line in lines)


def test_the_stack_selector_is_given_them():
    """The check that matters: the text reaches the stage that decides."""
    from app.graph import workflow

    source = inspect.getsource(workflow.build_workflow_graph)
    assert "constraints_note" in source, "the stack selector must read the brief's constraints"
