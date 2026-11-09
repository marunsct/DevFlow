"""A file's draft has its own reply limit, and a draft that is mostly the same lines over again is drafted once more.

Measured on one run: a unit-test file's draft wrote a 415 test for every content type it could name - 2,321 lines,
74 distinct - for about 25 minutes, up to the whole reply limit of the model.
"""
from types import SimpleNamespace

from app.graph import drafting

GOOD = "def test_one():\n    assert 1\n"
LOOPING = "def test_x(client):\n" + "".join(f"    response = client.post('/n', content_type='text/x{i % 3}')\n    assert response.status_code == 415\n" for i in range(400))


class Model:
    def __init__(self, replies):
        self.replies, self.bound, self.asked = list(replies), [], []

    def bind(self, **kwargs):
        self.bound.append(kwargs)
        return self

    def invoke(self, messages, **_):
        self.asked.append(messages[-1].content)
        return SimpleNamespace(content=f"```python\n{self.replies.pop(0)}```")


def _draft(monkeypatch, model):
    monkeypatch.setattr(drafting, "draft_request", lambda *a, **k: "Write the file.")
    monkeypatch.setattr("app.observability.direct_calls.config_for_this_run", lambda stage: {})
    return drafting._draft_one(model, None, "tests/test_notes.py", SimpleNamespace(), None, None)


def test_each_draft_has_its_own_reply_limit(monkeypatch):
    model = Model([GOOD])
    _draft(monkeypatch, model)
    assert model.bound and model.bound[0]["max_tokens"] == drafting.MOST_DRAFT_TOKENS


def test_a_looping_draft_is_drafted_again_with_why(monkeypatch):
    model = Model([LOOPING, GOOD])

    content = _draft(monkeypatch, model)

    assert content.strip() == GOOD.strip()
    assert len(model.asked) == 2 and "repeats" in model.asked[1]


def test_a_draft_that_still_repeats_is_given_up(monkeypatch):
    model = Model([LOOPING, LOOPING])
    assert _draft(monkeypatch, model) == ""


def test_the_note_uses_none_of_the_banned_words():
    import re

    assert not re.search(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", drafting.DRAFT_REPEATS, re.I)
