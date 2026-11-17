"""A control disabled on load is a defect whose fix must also change the project's own unit tests asserting it.

Measured on one run: each fix that kept "Add" usable was reverted for breaking unit tests that asserted it was
disabled, and the defect stayed open into a third attempt, while a hidden test of the refusal clicks the control.
"""
import json
import re
from types import SimpleNamespace

from app.acceptance import suite
from app.graph import acceptance_nodes

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def test_the_defect_tells_the_fixer_to_change_those_unit_tests(tmp_path):
    path = tmp_path / suite.RESULT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"ran": True, "shows": '- textbox "Title"\n- button "Add" [disabled]'}))

    defects = acceptance_nodes.interface_defects({"repository": SimpleNamespace(root_path=str(tmp_path)),
                                                  "document": SimpleNamespace(text='A control named "Add".')})

    [said] = [d.expected_behavior for d in defects if "disabled when the page loads" in d.description]
    assert "unit test" in said and "in the same fix" in said
    assert not BANNED.search(said)
