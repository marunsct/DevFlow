"""A product that stores data runs on an embedded database by default (plan item K.2, owner decision 2026-10-18).

Owner's choice: an embedded database first, no compose change. Every stage was
told there is no database server, and only that data access belongs behind an
adapter - so a product built for a server the brief named had nothing real to
store into when the acceptance suite started it. The default is now an
embedded database kept in a file under `DATA_DIR`, which the harness sets
fresh for every acceptance run; the brief's server stays the production
target behind one connection setting.
"""
from __future__ import annotations

import re

from app.agents.environment_contract import describe_execution_environment

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _paragraph() -> str:
    text = describe_execution_environment()
    start = text.index("- A PRODUCT THAT STORES DATA RUNS ON AN EMBEDDED DATABASE")
    end = text.index("\n- ", start + 3)
    return text[start:end]


def test_every_stage_is_told_the_default_is_an_embedded_file_under_data_dir():
    paragraph = _paragraph()

    assert "`DATA_DIR`" in paragraph
    assert "no server" in paragraph
    assert "production target" in paragraph and "one connection setting" in paragraph


def test_the_rule_uses_none_of_the_banned_words():
    assert not BANNED.search(_paragraph())


def test_the_acceptance_server_is_given_a_fresh_data_dir():
    from app.stacks.packs import _javascript as js

    config = js.playwright_config("node server.js")

    assert "DATA_DIR: `test-results/acceptance-data-" in config


def test_every_stage_is_told_the_product_must_start_from_port_and_data_dir_alone():
    text = " ".join(describe_execution_environment().split())

    assert "STARTS FROM `PORT` AND `DATA_DIR` ALONE" in text
    assert "generated at its first start and kept under `DATA_DIR`" in text
    assert not BANNED.search(text[text.index("STARTS FROM"):text.index("STARTS FROM") + 500])
