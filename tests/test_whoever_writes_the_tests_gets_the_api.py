"""Whoever writes the tests is handed the product's API as the specification decides it (owner's idea, 2026-10-19).

A large specification is held in the project memory only as its outline:
measured on a medium brief, 71,537 characters, of which the acceptance author
saw the headings and none of the endpoints, data shapes or error messages. Tests
written against guessed shapes fail a right product, and disputes then rewrote
the suite to match the code. The endpoints, data shapes, errors and interface
now go to the acceptance author and the testing work order whole, within a bound.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from app.acceptance import api_reference as ref
from app.acceptance import requests as acceptance_requests
from app.agents import specialists

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

SPEC = SimpleNamespace(
    api_and_event_contracts=["POST /api/auth/register {email, password, full_name} -> 201 {id, email, full_name}"],
    data_contracts=["User: {id: int, email: str, full_name: str}"],
    error_catalogue=["409 'Email already registered' when the email is taken"],
    interface_design=["/register: textbox 'Full Name', textbox 'Email', control 'Create account'"],
)


def test_the_reference_carries_every_api_section():
    text = ref.api_reference(SPEC)

    for field, heading in ref.API_FIELDS:
        assert heading in text and getattr(SPEC, field)[0] in text
    assert not BANNED.search(text.split("\n", 2)[1])


def test_the_reference_is_bounded():
    big = SimpleNamespace(api_and_event_contracts=[f"GET /api/item/{n} -> 200 " + "x" * 200 for n in range(200)])

    assert len(ref.api_reference(big)) < ref.MOST_REFERENCE_CHARS + 600


def test_the_acceptance_author_is_given_it(tmp_path):
    request = acceptance_requests.build_author_request(tmp_path, [], specification=SPEC)

    assert "--- The product's API, as the specification decides it ---" in request["messages"][-1]["content"]
    assert "full_name" in request["messages"][-1]["content"]


def test_every_work_order_is_given_it():
    for role, files in (("testing", ["tests/test_auth.py"]), ("backend", ["app/auth.py"]), ("ui_ux", ["src/App.tsx"])):
        order = SimpleNamespace(specialist_role=role, files=files, interfaces=[])
        assert "The product's API" in specialists.specification_for_the_work_order(SPEC, order), role


def _asked(asked: list[str], output_key_answer):
    """A stand-in for the stage's agent: records what it was asked, answers with `output_key_answer`."""
    def gated(state, config, *, initial_request, output_key, next_stage="", **kwargs):
        asked.append(initial_request["messages"][-1]["content"])
        return {output_key: output_key_answer, "stage": next_stage}
    return gated


def test_the_milestone_reviewer_is_given_it(tmp_path):
    from workflow_nodes import a_milestone_review, a_milestone_verdict

    asked: list[str] = []

    a_milestone_review(tmp_path, None, state={"technical_specification": SPEC},
                       patches={"app.graph.workflow._run_gated_agent": _asked(asked, a_milestone_verdict("accepted"))})

    assert len(asked) == 1 and "The product's API" in asked[0] and "full_name" in asked[0]


def test_a_fixer_is_given_it():
    from app.graph import workflow

    fix = workflow._the_specification_for_the_fix(
        {"technical_specification": SPEC}, SimpleNamespace(affected_files=["app/auth.py"], description="x"), [])
    assert "The product's API" in fix


EVERY_CRITERION = ("test('[AC-1] adds', async () => {});\ntest('[AC-2] deletes', async () => {});\n"
                   "test('[AC-3] persists', async () => {});\n")


def test_the_qa_lead_s_review_is_given_it_with_the_brief_s_names(tmp_path):
    from workflow_nodes import an_acceptance_review

    brief = 'Three buttons named "All", "Active" and "Completed" filter the list.'
    spec = SimpleNamespace(**{**vars(SPEC), "interface_design": [
        'Filters: control "All (0)", control "Active (0)", control "Completed"']})
    asked: list[str] = []

    an_acceptance_review(tmp_path, EVERY_CRITERION, failed=["[AC-1] adds", "[AC-2] deletes", "[AC-3] persists"],
                         state={"technical_specification": spec, "document": SimpleNamespace(text=brief)},
                         patches={"app.graph.workflow._run_gated_agent":
                                  _asked(asked, SimpleNamespace(approved=True, findings=[]))})

    assert len(asked) == 1 and "The product's API" in asked[0] and "full_name" in asked[0]
    assert 'the brief says "All"; the specification has "All (0)": use "All"' in asked[0]


def test_the_qa_lead_s_dispute_is_given_it(tmp_path):
    from workflow_nodes import a_dispute

    asked: list[str] = []

    def gated(state, config, *, initial_request, **kwargs):
        asked.append(initial_request["messages"][-1]["content"])
        return {"__suite_dispute__": object()}

    a_dispute(tmp_path, [("test_register [AC-1]", "AC-1 a user registers", "409 instead of 201")], [],
              state={"technical_specification": SPEC}, patches={"app.graph.workflow._run_gated_agent": gated})

    assert len(asked) == 1 and "The product's API" in asked[0]


# Measured over 30 runs: all four false acceptances came from the brief's wording overridden on the way to the suite;
# one specification wrote the brief's "All" filter as "All (0)", and this block told the suite writer to test the
# specification's labels word for word, beside a rule that the brief's words stand.
def test_the_brief_s_quoted_names_win_over_the_specification_s():
    brief = 'Three buttons named "All", "Active" and "Completed" filter the list.'
    spec = SimpleNamespace(interface_design=['Filters: control "All (0)", control "Active (0)", control "Completed"'])
    text = ref.api_reference(spec, brief)
    assert "the brief's words are the ones to use" in text
    assert 'the brief says "All"; the specification has "All (0)": use "All"' in text
    assert 'the brief says "Active"; the specification has "Active (0)"' in text
    assert '"Completed"; the specification' not in text, "the same name: no difference to list"
    assert ref.names_the_specification_changes("", "anything") == []
    harness_words = text.split("\n", 2)[1] + "Where the brief and this list differ, the brief's words"
    assert not BANNED.search(harness_words)


def test_the_author_and_the_judges_are_given_the_brief_s_names(tmp_path):
    from app.graph import workflow

    brief = 'Three buttons named "All", "Active" and "Completed" filter the list.'
    spec = SimpleNamespace(interface_design=['Filters: control "All (0)", control "Active (0)", control "Completed"'])
    the_brief_wins = 'the brief says "All"; the specification has "All (0)": use "All"'

    author = acceptance_requests.build_author_request(tmp_path, [], specification=spec, brief=brief)
    judged = workflow._with_the_api({"messages": [{"role": "user", "content": "judge these"}]},
                                    {"technical_specification": spec, "document": SimpleNamespace(text=brief)})

    assert the_brief_wins in author["messages"][-1]["content"]
    assert the_brief_wins in judged["messages"][-1]["content"]
