"""An edge-probe defect for a request at a huge id says that a number beyond the store's integer range must be checked.

Measured on two Flask runs: `DELETE /items/99999999999999999999` answered 500; where the service's error handler printed
nothing the defect carried only the generic body, and a fixer searched the routing, the handler and the signup route
for hours before the store's integer range came up.
"""
from __future__ import annotations

import re

from app.acceptance import edge_probe


def _found(shown: str, what: str = "at an id that is huge"):
    case = {"method": "DELETE", "shown": shown, "what": what, "path": "/items/{id}"}
    return [(case, {"kind": "server_error", "status": 500})]


def test_a_huge_id_defect_names_the_range_rule():
    said = edge_probe.edge_description(_found("/items/99999999999999999999"))

    assert "integer type" in said and "fits the store's range" in said


def test_a_defect_whose_path_is_a_template_and_whose_id_is_in_its_words_carries_it():
    """The real shape: `DELETE /items/{id}` at id `99999999999999999999`."""
    said = edge_probe.edge_description(_found("/items/{id}", "at id `99999999999999999999`"))

    assert "integer type" in said


def test_a_defect_at_another_id_does_not_carry_it():
    said = edge_probe.edge_description(_found("/items/not-a-number", "at an id that is not a number"))

    assert "integer type" not in said


def test_the_added_words_use_none_of_the_banned_ones():
    added = edge_probe._A_HUGE_NUMBER

    assert not re.search(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", added, re.I)
