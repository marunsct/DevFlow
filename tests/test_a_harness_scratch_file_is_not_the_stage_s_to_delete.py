"""A stage is not sent to delete the files the harness saves command-line code to, and a delete of one is not a refusal.

Measured over 30 runs: stages tried to delete `tmp-inline-` files 67 times - 25 in one run, 23 in another - many while
the delete tool was withheld, each answered as a refusal and sent again.
"""
from app.agents import settled_answer
from app.tools import agent_toolkit


def test_the_saved_code_note_says_the_harness_removes_it():
    assert "do not delete" in agent_toolkit.SAVED_CODE_NOTE


def test_a_delete_of_a_scratch_file_is_answered_as_nothing_to_do():
    answer = settled_answer.a_harness_scratch_delete({"name": "delete_artifact", "id": "c1",
                                                      "args": {"relative_path": "api/tmp-inline-4ba5a8fd.py"}})
    assert answer is not None and answer.status != "error" and "nothing to delete" in answer.content


def test_a_delete_of_a_product_file_is_left_to_the_tool():
    assert settled_answer.a_harness_scratch_delete({"name": "delete_artifact", "id": "c1",
                                                    "args": {"relative_path": "api/tmp-notes.py"}}) is None
