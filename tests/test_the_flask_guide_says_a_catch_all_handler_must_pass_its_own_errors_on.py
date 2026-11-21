"""The Flask pack's guide warns that a catch-all error handler turns Flask's own 404 and 405 into 500.

Measured on one Flask run: `PATCH /items/not-a-number` answered 500 where the route's `<int:...>` converter gives 404;
the product's catch-all handler answered every `HTTPException`, the server printed nothing, and three sprint attempts
searched for the cause elsewhere.
"""
from __future__ import annotations

import re

from app.stacks.packs import python_flask_api as flask_pack


def test_the_guide_names_the_catch_all_handler_and_its_remedy():
    guide = flask_pack.GUIDE

    assert "errorhandler(Exception)" in guide and "HTTPException" in guide and "404" in guide


def test_the_new_guide_lines_use_none_of_the_banned_words():
    added = flask_pack.GUIDE[flask_pack.GUIDE.index("A catch-all"):]

    assert not re.search(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", added, re.I)
