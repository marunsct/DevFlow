"""The Go pack's guide says a service this size keeps its code in the top folder as one package.

Measured on three Go runs of one brief: the model put the store in its own `package store` beside `package main` files,
or imported a folder that did not exist, the product did not start for the acceptance suite, and each fix round rewrote
some files and left the layout; the same model delivered the brief twice with a flat layout.
"""
from __future__ import annotations

import re

from app.stacks.packs import go_http_api


def test_the_guide_says_one_package_in_the_top_folder():
    guide = go_http_api.GUIDE

    assert "one package" in guide and "top folder" in guide and "package main" in guide


def test_the_new_guide_lines_use_none_of_the_banned_words():
    added = go_http_api.GUIDE[go_http_api.GUIDE.index("A service this size"):]

    assert not re.search(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", added, re.I)
