"""One severity ladder behind four disagreeing vocabularies.

run-0deeb8bf's `defect_fix_2_0` wrote a complete, correct defect report and
typed `"severity": "High"`. `High` is not in the Testing specialist's
`Literal["blocking", "major", "minor"]` - though it is in the security
reviewer's, and the same model plays both roles in one run. The whole answer
was rejected, `settled_answer` could not recognise it, and the stage rewrote it
five times until the repeat guard stopped the run.
"""

from __future__ import annotations

import pytest

from app.agents.severity import normalise, rank_of

DEFECT = ("blocking", "major", "minor")
MILESTONE = ("blocking", "major", "minor", "suggestion")
ARCHITECTURE = ("blocking", "major", "minor", "informational")
SECURITY = ("critical", "high", "medium", "low", "info")


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        ("High", "major"),
        ("high", "major"),
        ("critical", "blocking"),
        ("Critical", "blocking"),
        ("blocker", "blocking"),
        ("medium", "major"),
        ("low", "minor"),
        ("info", "minor"),
        ("suggestion", "minor"),
    ],
)
def test_the_defect_vocabulary_reads_the_others(written: str, expected: str) -> None:
    assert normalise(written, DEFECT) == expected


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        ("blocking", "critical"),
        ("major", "high"),
        ("minor", "low"),
        ("suggestion", "info"),
        ("informational", "info"),
    ],
)
def test_the_security_vocabulary_reads_the_others(written: str, expected: str) -> None:
    assert normalise(written, SECURITY) == expected


def test_each_vocabulary_keeps_its_own_words() -> None:
    for allowed in (DEFECT, MILESTONE, ARCHITECTURE, SECURITY):
        for word in allowed:
            assert normalise(word, allowed) == word


def test_case_and_padding_do_not_matter() -> None:
    assert normalise("  BLOCKING  ", DEFECT) == "blocking"
    assert normalise("Minor.", DEFECT) == "minor"


@pytest.mark.parametrize("written", ["P0", "p-1", "Sev 2", "sev4", "S 3"])
def test_the_ladders_models_bring_with_them_are_read(written: str) -> None:
    assert normalise(written, DEFECT) in DEFECT


def test_a_severity_in_a_sentence_is_found() -> None:
    assert normalise("High severity", DEFECT) == "major"
    assert normalise("blocking issue", DEFECT) == "blocking"
    assert normalise("urgent-ish", DEFECT) == "blocking"


@pytest.mark.parametrize("written", ["banana", "", "   ", "as discussed"])
def test_a_word_that_is_not_a_severity_is_left_for_the_schema(written: str) -> None:
    """Untouched, so the schema rejects it and the model is told which field.

    Guessing here would record a severity nobody wrote, which is worse than a
    validation error the model can act on.
    """
    assert normalise(written, DEFECT) == written


def test_a_non_string_is_left_alone() -> None:
    assert normalise(3, DEFECT) == 3
    assert normalise(None, DEFECT) is None
    assert rank_of(None) is None


def test_a_tie_goes_to_the_more_severe_word() -> None:
    """`medium` sits between `major` and `minor`, one rung from each.

    Calling it `major` costs a reviewer a second look. Calling it `minor` loses
    it, so the tie must not break that way.
    """
    assert normalise("medium", DEFECT) == "major"
