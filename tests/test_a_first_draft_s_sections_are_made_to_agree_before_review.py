"""A specification's first draft is checked for values its sections repeat differently, and one call settles only
the lines that disagree, before its first review (plan PA.7).

Measured: 9 of 11 small runs' first drafts went back, mostly for contradictions between sections written in separate
calls - "entry file name inconsistent across the specification", "advice marked declined but its limit still
specified" - and 9 of 11 designs reached the escalation.
"""
from __future__ import annotations

import json
import re

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from workflow_nodes import a_specification, an_architect, an_architect_state

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

#: Two sections naming different entry files, and an advice item declined in one section and cited in another.
DISAGREEING = dict(
    file_plan=["notes-api/src/index.js: starts the service", "notes-api/src/app.js: the routes"],
    configuration=["Command: node src/index.js starts the service on PORT."],
    implementation_order=["File: start.sh | Action: exec node src/app.js to start the service."],
    specialist_advice_decisions=["BE-1: adopted - api_and_event_contracts", "BE-2: declined - the brief sets no limit"],
    error_catalogue=["Condition: too many requests. Response: HTTP 429. Reference: BE-2"],
    api_and_event_contracts=["POST /notes -> 201 Created with the note, or 422 when the title is empty"],
    function_contracts=["createNote(req, res): handles POST /notes; responds 200 with the stored note"],
)


def _kinds(found):
    return sorted({entry.kind for entry in found})


def test_sections_that_repeat_a_value_differently_are_found():
    from app.graph.specification_consistency import disagreements

    found = disagreements(a_specification(**DISAGREEING))

    assert _kinds(found) == ["advice decision", "start command", "status code"]
    lines = {line for entry in found for _, line in entry.lines}
    assert "File: start.sh | Action: exec node src/app.js to start the service." in lines
    assert "Condition: too many requests. Response: HTTP 429. Reference: BE-2" in lines
    assert "createNote(req, res): handles POST /notes; responds 200 with the stored note" in lines


def test_sections_that_agree_are_left_alone():
    from app.graph.specification_consistency import disagreements

    agreeing = {**DISAGREEING,
                "implementation_order": ["File: start.sh | Action: exec node src/index.js to start the service."],
                "error_catalogue": ["Condition: the title is empty. Response: HTTP 422."],
                "function_contracts": ["createNote(req, res): handles POST /notes; responds 201 with the note"]}

    assert disagreements(a_specification(**agreeing)) == []


def test_a_limit_given_twice_with_different_numbers_is_found():
    from app.graph.specification_consistency import disagreements

    found = disagreements(a_specification(
        domain_model=["Note: title is a string of at most 200 characters"],
        error_catalogue=["The title may be up to 120 characters; a longer one is refused with 422"],
    ))

    assert [(entry.kind, entry.subject) for entry in found] == [("limit", "title (character)")]


class _Settler(BaseChatModel):
    """The model endpoint: records what it is asked, and rewrites the two lines that disagree."""

    asked: list = []

    @property
    def _llm_type(self) -> str:
        return "stand-in"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.asked.append(str(messages[-1].content))
        reply = {"lines": [
            {"section": "implementation_order",
             "old": "File: start.sh | Action: exec node src/app.js to start the service.",
             "new": "File: start.sh | Action: exec node src/index.js to start the service."},
            {"section": "function_contracts",
             "old": "createNote(req, res): handles POST /notes; responds 200 with the stored note",
             "new": "createNote(req, res): handles POST /notes; responds 201 with the stored note"},
            # A line that does not disagree is never rewritten, whatever the reply says.
            {"section": "testing", "old": "written", "new": "rewritten"},
        ]}
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=json.dumps(reply)))])


def test_the_first_draft_is_settled_by_one_call_shown_only_the_lines_that_disagree(tmp_path):
    settler = _Settler()
    settler.asked = []
    draft = a_specification(**DISAGREEING)

    update, _, _ = an_architect(an_architect_state(tmp_path), draft, patches={
        "app.models.build_default_chat_model": lambda *args, **kwargs: settler,
    })

    specification = update["technical_specification"]
    assert specification.implementation_order == ["File: start.sh | Action: exec node src/index.js to start the service."]
    assert specification.function_contracts == [
        "createNote(req, res): handles POST /notes; responds 201 with the stored note"]
    assert specification.testing == ["written"]
    assert len(settler.asked) == 1
    asked = settler.asked[0]
    assert "exec node src/app.js" in asked and "Reference: BE-2" in asked
    assert "the routes" not in asked  # a line that agrees is not sent


def test_a_revision_is_not_settled_again_here(tmp_path):
    settler = _Settler()
    settler.asked = []
    state = an_architect_state(tmp_path, technical_specification=a_specification(**DISAGREEING),
                               revision_comments=["Fix the port."])

    an_architect(state, a_specification(**DISAGREEING), patches={
        "app.models.build_default_chat_model": lambda *args, **kwargs: settler,
    })

    assert not any("written in separate parts" in text for text in settler.asked)


def test_the_settling_request_uses_none_of_the_banned_words():
    from app.graph.specification_consistency import Disagreement, settle_request

    request = settle_request([Disagreement("file", "src/app.js", "named twice", [("testing", "a line")])])

    assert "rewrite only the lines that must change" in request
    assert not BANNED.search(request.replace("a line", ""))
