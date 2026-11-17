"""Behind `STRUCTURED_DISPUTE_VERDICT` (off until measured), the dispute is read by one ruling per test, not its prose.

Plan item 19. The prose reading (`judged_by_the_code`) needed four patches, the last after "its own steps never set up"
was filed as a reason about the product and a test no product could pass stayed locked.
"""
from __future__ import annotations

import re
from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel

from app.agents import suite_dispute
from app.agents.suite_dispute import DisputeRuling, SuiteDisputeWithRulings

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
FAILING = ["[AC-2][AC-9] list notes returns 200 with a JSON array", "[AC-4] updates a note"]
QUOTE = "AC-2 List all notes: GET /notes answers 200 with every note"


class _Asked(BaseChatModel):
    """The model: records the tools it is offered and answers nothing."""

    class Stopped(Exception):
        pass

    offered_tools: list = []

    @property
    def _llm_type(self) -> str:
        return "asked"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "_Asked":
        self.offered_tools.append(list(tools))
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise _Asked.Stopped()


def _answer(*rulings, prose=()):
    return SuiteDisputeWithRulings(cannot_pass=list(prose), rulings=list(rulings))


def test_a_ruling_that_the_test_is_wrong_with_a_quote_reopens_it_whatever_its_words(monkeypatch):
    monkeypatch.setenv("STRUCTURED_DISPUTE_VERDICT", "on")
    ruling = DisputeRuling(test=FAILING[0], the_test_is_wrong=True,
                           the_test_asserts="titles starting `list-${slug}-` number two, though it sent `list-a-${slug}`",
                           the_standard_says=QUOTE)
    named = suite_dispute.tests_it_names(_answer(ruling), FAILING)
    assert len(named) == 1 and named[0].startswith(f"`{FAILING[0]}`") and QUOTE in named[0]
    assert not BANNED.search(named[0])


def test_a_ruling_for_the_product_or_without_a_quote_reopens_nothing(monkeypatch):
    monkeypatch.setenv("STRUCTURED_DISPUTE_VERDICT", "on")
    right = DisputeRuling(test=FAILING[1], the_test_is_wrong=False, the_test_asserts="the title changes",
                          the_standard_says="AC-4 Update a note's title and body")
    unquoted = DisputeRuling(test=FAILING[0], the_test_is_wrong=True, the_test_asserts="two notes", the_standard_says="")
    assert suite_dispute.tests_it_names(_answer(right, unquoted), FAILING) == []


def test_off_the_prose_is_read_and_a_ruling_reopens_nothing(monkeypatch):
    monkeypatch.setenv("STRUCTURED_DISPUTE_VERDICT", "off")
    ruling = DisputeRuling(test=FAILING[0], the_test_is_wrong=True, the_test_asserts="two notes", the_standard_says=QUOTE)
    assert suite_dispute.tests_it_names(_answer(ruling), FAILING) == []


@pytest.mark.parametrize("switch, offered", [("on", True), ("off", False)])
def test_the_model_is_asked_for_rulings_only_with_the_switch_on(monkeypatch, tmp_path, switch, offered):
    from langgraph.checkpoint.memory import InMemorySaver

    monkeypatch.setenv("STRUCTURED_DISPUTE_VERDICT", switch)
    monkeypatch.setattr("app.plugins.middleware.get_plugin_instructions", lambda keys, role: "")
    model = _Asked(offered_tools=[])
    agent = suite_dispute.create_suite_dispute_agent(model=model, repo_root=str(tmp_path), checkpointer=InMemorySaver())

    with pytest.raises(_Asked.Stopped):
        agent.invoke({"messages": [{"role": "user", "content": "go"}]}, {"configurable": {"thread_id": "t"}})

    [answer] = [tool for tool in model.offered_tools[0] if "cannot_pass" in getattr(tool, "args", {})]
    assert ("rulings" in answer.args) is offered


def test_what_the_model_is_told_of_a_ruling_uses_none_of_the_banned_words():
    for field in DisputeRuling.model_fields.values():
        assert not BANNED.search(field.description or "")


def test_an_answer_without_rulings_does_not_satisfy_the_schema():
    """Measured on one run: both disputes under the switch returned no rulings, so the field taught nothing."""
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        SuiteDisputeWithRulings(cannot_pass=[], rulings=[])
    with pytest.raises(pydantic.ValidationError):
        SuiteDisputeWithRulings(cannot_pass=[])
    right = DisputeRuling(test=FAILING[1], the_test_is_wrong=False, the_test_asserts="the title changes",
                          the_standard_says="AC-4 Update a note's title and body")
    assert SuiteDisputeWithRulings(rulings=[right]).rulings == [right]


def _ruling(quote):
    return DisputeRuling(test=FAILING[0], the_test_is_wrong=True, the_test_asserts="it asserts a thing", the_standard_says=quote)


def test_a_quote_that_is_not_in_the_standard_reopens_nothing(monkeypatch):
    # Measured on one run: the ruling's "standard" was a sentence of the harness's own instructions to it.
    monkeypatch.setenv("STRUCTURED_DISPUTE_VERDICT", "on")
    answer = _answer(_ruling("A line with no reason is not counted."))
    assert suite_dispute.tests_it_names(answer, FAILING, standard="AC-4 Update a note's title and body.") == []


def test_a_quote_from_the_standard_reopens_the_test_whatever_its_case_and_spacing(monkeypatch):
    monkeypatch.setenv("STRUCTURED_DISPUTE_VERDICT", "on")
    answer = _answer(_ruling("update a note's  title and body"))
    assert len(suite_dispute.tests_it_names(answer, FAILING, standard="AC-4 Update a note's\ntitle and body.")) == 1


def test_the_node_gives_the_standard_to_the_reading_of_the_dispute(tmp_path):
    """The ruling is read against the brief, the specification and the failing tests' criteria."""
    from workflow_nodes import a_dispute

    failing = [("[AC-4] updates a note", "AC-4 PUT /notes/:id answers 200 with the changed note", "expected 200")]

    _, asked = a_dispute(tmp_path, failing, [])

    (reading,) = asked["rulings"]
    assert "The brief: notes are kept until deleted." in reading["standard"]
    assert "AC-4 PUT /notes/:id answers 200 with the changed note" in reading["standard"]
    assert reading["names"] == ["[AC-4] updates a note"]


STANDARD = (
    "`textkit.truncate(text, limit, suffix='...')` takes a string `text`, an integer `limit`, and an optional string "
    "`suffix` (default '...'). Returns the original text if its length is at most limit. Otherwise returns the first "
    "(limit - len(suffix)) characters of text followed by suffix, producing exactly limit characters total."
)


def _named_quoting(monkeypatch, quoted):
    """The tests the dispute reopens when its one ruling quotes `quoted` as the standard."""
    monkeypatch.setenv("STRUCTURED_DISPUTE_VERDICT", "on")
    ruling = DisputeRuling(test=FAILING[0], the_test_is_wrong=True, the_test_asserts="it asks for six characters",
                           the_standard_says=quoted)
    return suite_dispute.tests_it_names(_answer(ruling), FAILING, standard=STANDARD)


def test_a_quote_of_several_sentences_without_the_marks_still_counts(monkeypatch):
    # Measured on one run: a right ruling joined two sentences of the specification and left out its backticks, the
    # whole-string match refused it, and fixers went after a product doing what the standard says.
    quoted = (
        "textkit.truncate(text, limit, suffix='...') takes a string text, an integer limit, and an optional string "
        "suffix (default '...'). Otherwise returns the first (limit - len(suffix)) characters of text followed by "
        "suffix, producing exactly limit characters total."
    )
    assert _named_quoting(monkeypatch, quoted)


def test_a_quote_with_any_sentence_the_standard_does_not_hold_is_refused(monkeypatch):
    made_up = "Otherwise returns the first characters of text. The result must never be shorter than ten characters."
    assert _named_quoting(monkeypatch, made_up) == []


def test_a_true_sentence_with_a_signature_put_before_it_still_counts(monkeypatch):
    # Measured on the same run: the next ruling put the function's signature before the specification's own sentence.
    quoted = (
        "textkit.truncate(text, limit, suffix='...') returns the original text if its length is at most limit. "
        "Otherwise returns the first (limit - len(suffix)) characters of text followed by suffix, producing exactly "
        "limit characters total."
    )
    assert _named_quoting(monkeypatch, quoted)


def test_a_sentence_sharing_only_a_few_words_with_the_standard_is_refused(monkeypatch):
    quoted = "Returns the first characters unless the caller asks for a shorter result of any length at all."
    assert _named_quoting(monkeypatch, quoted) == []
