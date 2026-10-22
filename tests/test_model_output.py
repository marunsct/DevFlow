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


def test_the_write_guard_and_the_answer_parser_both_use_it() -> None:
    """Two callers, one definition - the B17 lesson applied before it bites."""
    import inspect

    from app.agents import settled_answer
    from app.tools import repository

    assert "find_leaked_marker" in inspect.getsource(repository)
    assert "strip_reasoning" in inspect.getsource(settled_answer)
