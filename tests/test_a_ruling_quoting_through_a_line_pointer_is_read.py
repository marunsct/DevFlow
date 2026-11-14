"""A specification ruling that quotes the words inside a pointer to where they are is read for those words.

Measured on one run: three right rulings each quoted as `File Plan (line 138: 'Exports: generateId(): string')`, all
three were rejected as "not in the specification word for word", and the contradiction stayed open.
"""
from app.agents import specification_rulings as sr

SPEC = ("## File Plan\n- utils.ts. Exports: generateId(): string\n## Component Boundaries\n"
        "- utils.ts exports generateTaskId(): string\n")


def test_the_words_inside_the_pointer_are_what_is_quoted():
    text = sr._plain(SPEC)
    for said in ("File Plan (line 138: 'Exports: generateId(): string')", 'line 2: "Exports: generateId(): string"'):
        assert sr._as_quoted(said, text) == "Exports: generateId(): string", said


def test_a_ruling_quoted_so_is_kept():
    answer = sr.Rulings(rulings=[sr.Ruling(
        finding=1, first_statement="File Plan (line 2: 'Exports: generateId(): string')",
        second_statement="utils.ts exports generateTaskId(): string", stands="second", why="The boundary names it.")])
    [kept] = sr.verified(answer, SPEC, ["generateId and generateTaskId disagree"])
    assert kept.first_statement == "Exports: generateId(): string"


def test_a_pointer_to_words_not_there_is_still_rejected():
    rejected: list[str] = []
    answer = sr.Rulings(rulings=[sr.Ruling(
        finding=1, first_statement="File Plan (line 2: 'Exports: makeId(): string')",
        second_statement="utils.ts exports generateTaskId(): string", stands="second", why="x")])
    assert sr.verified(answer, SPEC, ["f"], rejected=rejected) == [] and rejected
