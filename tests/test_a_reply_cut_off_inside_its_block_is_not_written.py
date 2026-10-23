"""A reply that ends inside its fenced block - cut off by the reply cap - is no file.

It was taken as a reply with no fence: the whole of it, the opening
```` ```python ```` line included, became the file and was written over the
one there; with a short block before it, the short block was. A rewrite of a
file longer than the cap allows always ends this way.
"""
from __future__ import annotations

from app.graph.drafting import the_content_in


def test_a_reply_with_no_closing_fence_is_no_file():
    assert the_content_in("Here it is:\n```python\ndef a():\n    return 1\n\ndef b(") == ""


def test_a_short_block_before_a_cut_off_one_is_not_taken_for_the_file():
    reply = "First the import:\n```python\nimport os\n```\nThen the file:\n```python\nimport os\n\ndef main(\n"
    assert the_content_in(reply) == ""


def test_a_whole_reply_is_read_as_before():
    assert the_content_in("intro\n```ts\nexport const a = 1;\n```\n") == "export const a = 1;\n"
    assert the_content_in("plain text file") == "plain text file\n"
    nested = "```markdown\n# Readme\n\n```bash\nmake\n```\n\nDone.\n```\n"
    assert the_content_in(nested)
