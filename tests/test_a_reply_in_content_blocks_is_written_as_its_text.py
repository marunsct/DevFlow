"""A reply whose content is a list of blocks - a hosted model's thinking block and its text - is read as its text.

Measured on one hosted run: every source file but one was written as the Python form of the reply's block list,
`[{'signature': 'CAQS...', 'thinking': ..., 'type': 'thinking'}, {'type': 'text', 'text': '```csharp ...'}]`, on one
line. The build failed with 81 syntax errors on line 1, no fixer could repair a file that was not code, and the
sprint was planned again. The readers took `str(reply.content)`, which is that form for a list.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.graph import drafting, rewritten_fixes
from app.models.reply_text import reply_text

CODE = "using System;\n\npublic static class Note\n{\n}\n"
BLOCKS = [
    {"type": "thinking", "thinking": "The file needs a class.", "signature": "CAQSsgsKEAgTGAI4AUIIdGhpbmtpbmc"},
    {"type": "text", "text": f"Here it is.\n\n```csharp\n{CODE}```\n"},
]


def test_a_block_list_is_its_text_blocks_only():
    text = reply_text(SimpleNamespace(content=BLOCKS))

    assert "signature" not in text and "The file needs a class." not in text
    assert CODE in text


def test_plain_text_and_strings_are_kept_as_they_are():
    assert reply_text("plain") == "plain"
    assert reply_text(SimpleNamespace(content="plain")) == "plain"
    assert reply_text(SimpleNamespace(content=["a", {"type": "text", "text": "b"}, {"type": "tool_use", "id": "x"}])) == "ab"
    assert reply_text(None) == ""


def test_a_drafted_file_from_a_block_list_is_the_code():
    assert drafting.the_content_in(SimpleNamespace(content=BLOCKS).content) == CODE


def test_a_rewritten_file_from_a_block_list_is_the_code():
    written = rewritten_fixes._the_reply_s_file("src/App/Note.cs", "// was\n", SimpleNamespace(content=BLOCKS))  # noqa: SLF001

    assert written == CODE
