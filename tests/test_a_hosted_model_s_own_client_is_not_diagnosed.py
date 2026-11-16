"""A model whose client is not OpenAI-style is not put through the checks that call one (LR.16).

Measured on a hosted model's runs: every check called `root_client.chat.completions.create`, failed with "object has
no attribute 'root_client'" three times per segment, and was logged as "the model server does not answer" on a model
that answered every stage.
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace

from app.models import diagnostics


def test_only_an_openai_style_client_is_diagnosed():
    openai_style = SimpleNamespace(root_client=SimpleNamespace(chat=SimpleNamespace(
        completions=SimpleNamespace(create=lambda **kw: None))))
    assert diagnostics.speaks_chat_completions(openai_style) is True
    assert diagnostics.speaks_chat_completions(SimpleNamespace(model="claude-x")) is False


def test_the_segment_skips_the_checks_for_any_other_client():
    from app.server import tasks

    source = inspect.getsource(tasks.execute_workflow_run)
    skip = source.index("if not speaks_chat_completions(served):")
    assert skip < source.index("diagnose_if_new(served)")
    assert "raise _NotDiagnosed" in source[skip:skip + 700]
