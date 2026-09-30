"""A structured answer that carries the model's next turn is cleaned, not kept.

One run's `openai/gpt-oss-20b` specialist, near its model-call budget, ended a
`blockers` item with `<|end|><|start|>assistant<|channel|>final<|message|>{`.
The answer was accepted as it was, and its stage summary was refused as a file
carrying a delimiter; the Sprint Record, rendered from the same answers, would
have been refused whole. An answer is cleaned and a file is refused - see
`app.agents.model_output`.
"""
from __future__ import annotations

from pydantic import BaseModel

from app.agents.model_output import answer_without_leaked_turns, without_a_leaked_turn

LEAK = '<|end|><|start|>assistant<|channel|>final<|message|>{'


class _Item(BaseModel):
    text: str


class _Answer(BaseModel):
    summary: str
    blockers: list[str] = []
    items: list[_Item] = []


def test_a_string_is_cut_where_the_next_turn_begins() -> None:
    assert without_a_leaked_turn(f"Playwright could not open the page.\n{LEAK}") == (
        "Playwright could not open the page."
    )


def test_nested_values_are_cleaned_and_others_kept() -> None:
    assert without_a_leaked_turn({"a": [f"x{LEAK}", 3], "b": ("y", None)}) == {"a": ["x", 3], "b": ("y", None)}


def test_an_answer_is_cleaned_field_by_field() -> None:
    answer = _Answer(summary="done", blockers=[f"page denied{LEAK}"], items=[_Item(text=f"a{LEAK}")])

    cleaned = answer_without_leaked_turns(answer)

    assert cleaned.blockers == ["page denied"]
    assert cleaned.items == [_Item(text="a")]
    assert cleaned.summary == "done"


def test_a_clean_answer_is_the_same_object() -> None:
    answer = _Answer(summary="done", blockers=["none"])

    assert answer_without_leaked_turns(answer) is answer


def test_anything_that_is_not_an_answer_passes_through() -> None:
    assert answer_without_leaked_turns(None) is None
    assert answer_without_leaked_turns({"summary": f"x{LEAK}"}) == {"summary": f"x{LEAK}"}


def test_a_workflow_document_drops_a_stray_delimiter_instead_of_being_lost(tmp_path) -> None:
    from types import SimpleNamespace

    from app.graph.workflow import _record_document

    state = {"repository": SimpleNamespace(root_path=str(tmp_path))}

    _record_document(state, "docs/stage_summaries/specialist_ui_ux_0.md", "# Summary\n\nBlocked<|end|> here.\n")

    written = (tmp_path / "docs" / "stage_summaries" / "specialist_ui_ux_0.md").read_text(encoding="utf-8")
    assert "<|" not in written and "Blocked here." in written
