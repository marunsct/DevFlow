"""A control disabled on load is a defect whose fix must also change the project's own unit tests asserting it.

Measured on one run: each fix that kept "Add" usable was reverted for breaking unit tests that asserted it was
disabled, and the defect stayed open into a third attempt, while a hidden test of the refusal clicks the control.
"""
import inspect
import re

from app.graph import acceptance_nodes

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_the_defect_tells_the_fixer_to_change_those_unit_tests():
    said = acceptance_nodes.DISABLED_CONTROL_UNIT_TESTS
    assert "unit test" in said and "in the same fix" in said
    assert not BANNED.search(said)
    assert "+ DISABLED_CONTROL_UNIT_TESTS" in inspect.getsource(acceptance_nodes)
