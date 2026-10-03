"""Hidden acceptance tests for the textkit-lib benchmark, written from brief.md's Interface."""

import pytest

import textkit


def test_slugify_example():
    assert textkit.slugify("Hello, World!") == "hello-world"


def test_slugify_collapses_and_trims_separators():
    assert textkit.slugify("  --Rock & Roll 2024--  ") == "rock-roll-2024"


def test_word_count():
    assert textkit.word_count("a  b\nc") == 3
    assert textkit.word_count("") == 0
    assert textkit.word_count("   ") == 0


def test_truncate_leaves_short_text_alone():
    assert textkit.truncate("short", 10) == "short"
    assert textkit.truncate("exactly", 7) == "exactly"


def test_truncate_shortens_to_the_limit():
    assert textkit.truncate("Hello, World!", 8) == "Hello..."
    assert len(textkit.truncate("x" * 50, 20)) == 20


def test_truncate_with_its_own_suffix():
    assert textkit.truncate("abcdefghij", 5, suffix="~") == "abcd~"


def test_truncate_refuses_a_limit_below_the_suffix():
    with pytest.raises(ValueError):
        textkit.truncate("abcdef", 2)
    with pytest.raises(ValueError):
        textkit.truncate("abcdef", -1, suffix="")


def test_title_case_keeps_whitespace():
    assert textkit.title_case("hELLO   wORLD\tagain") == "Hello   World\tAgain"
