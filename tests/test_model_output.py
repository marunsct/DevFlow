"""Delimiters a chat template wraps a turn in, and what to do about them.

Across five models in one session they reached content three ways:
`<|END_THINKING|><|START_ACTION|>` written into a source file (finding 93,
one run); `<tools>{...}</tools>` returned as message content with
`tool_calls` empty (run 40); a trailing `</tool_call>` on an otherwise valid
structured answer (run 31).

Two callers want opposite treatments, and that asymmetry is the point of this
module: a write is refused, an answer is stripped.
"""

from __future__ import annotations

from app.agents.model_output import find_leaked_marker, strip_reasoning


def test_the_token_that_broke_a_test_suite_is_found() -> None:
    """One run's Task.test.mjs, line 963."""
    assert find_leaked_marker('});\n\n");<|END_THINKING|><|START_ACTION|>[{') == "<|END_THINKING|>"


def test_tag_style_wrappers_are_found_too() -> None:
    """The half finding 93 did not cover. `<|name|>` was refused; these were not."""
    assert find_leaked_marker('<tools>{"name": "ls"}</tools>') == "<tools>"
    assert find_leaked_marker("done</tool_call>") == "</tool_call>"
    assert find_leaked_marker("<think>hmm</think>") == "<think>"


def test_ordinary_code_is_not_a_leak() -> None:
    """The comparison operators and generics this would wrongly catch."""
    for text in (
        "const c = a || b;\nif (x <| y) {}",
        "function f<T>(x: T): T { return x; }",
        "<div class='think'>not a tag</div>",
        "if (a < b && c > d) {}",
    ):
        assert find_leaked_marker(text) is None, text


def test_a_reasoning_block_is_stripped_with_its_contents() -> None:
    """A model that reasons about the schema leaves an example object inside
    `<think>`, and the first JSON object in the raw text is then the example
    rather than the answer."""
    text = '<think>the shape is {"wrong": 1}</think>\n{"right": 2}'

    assert '"wrong"' not in strip_reasoning(text)
    assert '"right"' in strip_reasoning(text)


def test_stripping_survives_an_unclosed_block() -> None:
    """A truncated turn leaves one half of a pair."""
    assert "<think" not in strip_reasoning('<think>cut off {"a": 1}')
    assert "</tool_call>" not in strip_reasoning('{"a": 1}</tool_call>')


def test_stripping_leaves_text_with_no_delimiters_alone() -> None:
    assert strip_reasoning('{"a": 1}') == '{"a": 1}'


def test_a_write_carrying_a_leaked_token_is_refused(tmp_path) -> None:
    """Two callers, one definition - the B17 lesson applied before it bites. The write is refused..."""
    import pytest

    from app.tools.repository import RepositoryToolError, write_approved_artifact

    with pytest.raises(RepositoryToolError, match="END_THINKING"):
        write_approved_artifact(str(tmp_path), "notes/README.md", "# Notes\nKept until deleted.<|END_THINKING|>\n")

    assert not (tmp_path / "notes" / "README.md").exists()


def test_a_stage_s_answer_is_read_past_its_reasoning() -> None:
    """...and the answer is stripped: the schema example inside `<think>` is not taken for the answer."""
    from types import SimpleNamespace

    from pydantic import BaseModel

    from app.agents.settled_answer import _answer_in

    class Verdict(BaseModel):
        status: str

    message = SimpleNamespace(content='<think>the shape is {"status": "example"}</think>\n{"status": "approved"}')

    assert _answer_in(message, Verdict).status == "approved"
