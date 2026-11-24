"""A group of values compared in a normal form is reported in that form (LF.1317).

Measured on two runs of one brief: it said words are "compared in lower case"; the products counted words case-
insensitively and printed each as first read ("The 3"), the hidden tests expecting "the 3" failed (2 of 8 each), and
the runs' own locked suites passed. The architect's comparison rule and the suite writer's rule had not reached the
code that groups the values, and the suite checked that two spellings were counted together, not the spelling shown.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
_START = "Where the product groups or counts values that are compared in a normal form"


def _flat(text: str) -> str:
    return " ".join(str(text).split())


def _the_sentence(text: str) -> str:
    flat = _flat(text)
    start = flat.index(_START)
    end = flat.index("is that one shown.", start) + len("is that one shown.")
    return flat[start:end]


def _says_a_group_is_reported_in_its_normal_form(text: str) -> bool:
    sentence = _the_sentence(text)
    return ("reports each group in that normal form" in sentence
            and "a group has no single original spelling" in sentence
            and "Only where the brief says which spelling to show" in sentence)


def test_the_architect_is_told_a_group_is_reported_in_its_normal_form():
    from app.agents import principal_architect

    assert _says_a_group_is_reported_in_its_normal_form(principal_architect._SYSTEM_PROMPT)


@pytest.mark.parametrize("role", ["backend", "ui_ux"])
def test_the_builders_of_product_code_are_told_it(role):
    from app.agents.specialists import _system_prompt

    assert _says_a_group_is_reported_in_its_normal_form(_system_prompt(role))


def test_a_product_file_s_draft_is_told_it_and_a_test_file_s_is_not(tmp_path):
    from app.graph import drafting

    order = SimpleNamespace(task_description="Count the words of a text")

    code_draft = drafting.draft_request(tmp_path, "wordcount/src/counter.py", order, None, None)
    test_draft = drafting.draft_request(tmp_path, "wordcount/tests/test_counter.py", order, None, None)

    assert _says_a_group_is_reported_in_its_normal_form(code_draft)
    assert _START not in _flat(test_draft)


def test_the_suite_s_writer_and_reviewer_check_the_reported_key_not_only_the_merged_count():
    from app.acceptance.requests import TESTS_ASSUME_ONLY_WHAT_THEY_MADE
    from app.agents import acceptance_reviewer

    for told in (_flat(TESTS_ASSUME_ONLY_WHAT_THEY_MADE), _flat(acceptance_reviewer._SYSTEM_PROMPT)):
        assert "feeds two spellings of one value" in told
        assert "checks that the key it reports is the normal form" in told
        assert "not only that the two were counted together" in told


def test_the_new_sentences_ban_the_product_words():
    from app.acceptance.requests import TESTS_ASSUME_ONLY_WHAT_THEY_MADE
    from app.agents import principal_architect

    rule = _flat(TESTS_ASSUME_ONLY_WHAT_THEY_MADE)
    suite_sentence = rule[rule.index("A test of a group or count of such values"):]
    suite_sentence = suite_sentence[:suite_sentence.index(".") + 1]

    assert not BANNED.search(_the_sentence(principal_architect._SYSTEM_PROMPT))
    assert not BANNED.search(suite_sentence)
