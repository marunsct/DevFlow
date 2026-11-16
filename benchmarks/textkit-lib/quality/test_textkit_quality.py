"""Quality tests for the textkit-lib benchmark: the brief's interface at its edges (LR.25).

Scored apart from the hidden tests. Each holds the library to something the brief already says that the hidden tests
do not reach; the benchmark's reference passes every one.
"""

import pytest

import textkit


def test_slugify_of_nothing_to_keep_is_empty():
    assert textkit.slugify("") == ""
    assert textkit.slugify("!!! ---") == ""


def test_slugify_keeps_digits_and_lowers_letters():
    assert textkit.slugify("ABC123def") == "abc123def"
    assert textkit.slugify("a_b") == "a-b"


def test_word_count_counts_tabs_and_mixed_whitespace_as_separators():
    assert textkit.word_count("a\tb \r\n c") == 3
    assert textkit.word_count("\n\n\t") == 0


def test_truncate_at_exactly_the_limit_is_unchanged():
    assert textkit.truncate("12345", 5) == "12345"


def test_truncate_is_exactly_the_limit_long_with_any_suffix():
    for limit in range(3, 12):
        assert len(textkit.truncate("x" * 40, limit)) == limit
    assert textkit.truncate("abcdefgh", 5, suffix="~") == "abcd~"
    assert textkit.truncate("abcdefgh", 3, suffix="") == "abc"


def test_truncate_with_a_limit_below_the_suffix_raises():
    with pytest.raises(ValueError):
        textkit.truncate("abcdefgh", 1, suffix="...")


def test_title_case_keeps_every_whitespace_character_where_it_was():
    text = "  hello\tWORLD \n again  "
    result = textkit.title_case(text)
    assert [c for c in result if c.isspace()] == [c for c in text if c.isspace()]
    assert result.split() == ["Hello", "World", "Again"]
