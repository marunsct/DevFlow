"""A browser product's screenshots are scored on a fixed checklist at release, as a number, never a gate (plan EV.2).

Behind `SCREENSHOT_RUBRIC`, off until measured, and only when the judgement
model reads images.
"""
from __future__ import annotations

import inspect
import json
import os
import re
from types import SimpleNamespace
from unittest import mock

from app.acceptance import screenshot_rubric
from app.graph import delivery
from app.observability.run_kpis import kpis
from app.stacks import contract

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
ON = {"SCREENSHOT_RUBRIC": "on"}
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
REPLY = json.dumps({
    "layout": {"score": 4, "note": "aligned at both widths"},
    "contrast": {"score": 5, "note": "readable"},
    "empty_states": {"score": 1, "note": "not shown"},
    "error_states": {"score": 2, "note": "a bare 500"},
})


class _Model:
    def __init__(self):
        self.asked = []

    def invoke(self, messages, **_):
        self.asked.append(messages)
        return SimpleNamespace(content=REPLY)


def _page(tmp_path, monkeypatch):
    monkeypatch.setattr(contract, "read", lambda root: {"project": "app"})
    (tmp_path / "app" / "test-results").mkdir(parents=True)
    (tmp_path / "app" / "test-results" / "page-desktop.png").write_bytes(PNG)
    monkeypatch.setattr("app.models.vision.the_reviewer_reads_images", lambda: True)
    return tmp_path


def test_on_each_item_is_scored_kept_and_reaches_the_kpis(tmp_path, monkeypatch):
    root, model = _page(tmp_path, monkeypatch), _Model()
    with mock.patch.dict(os.environ, ON):
        result = screenshot_rubric.score(root, model)

    assert result["mean"] == 3.0 and result["items"]["error_states"]["score"] == 2
    assert json.loads((root / screenshot_rubric.RUBRIC_FILE).read_text())["mean"] == 3.0
    text, *images = model.asked[0][-1].content
    assert len(images) == 1 and images[0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert not BANNED.search(text["text"])
    assert kpis([{"kind": "screenshot_rubric", "mean": 3.0}])["screenshot_rubric"] == 3.0


def test_off_unseen_or_without_screenshots_nothing_is_asked(tmp_path, monkeypatch):
    root, model = _page(tmp_path, monkeypatch), _Model()
    with mock.patch.dict(os.environ, {"SCREENSHOT_RUBRIC": ""}):
        assert screenshot_rubric.score(root, model) is None
    monkeypatch.setattr("app.models.vision.the_reviewer_reads_images", lambda: False)
    with mock.patch.dict(os.environ, ON):
        assert screenshot_rubric.score(root, model) is None
    assert model.asked == []
    assert kpis([])["screenshot_rubric"] is None


def test_the_release_scores_it_and_nothing_depends_on_the_score():
    source = inspect.getsource(delivery.release)
    call = "screenshot_rubric.score(root"
    assert call in source
    line = next(l for l in source.splitlines() if call in l)
    assert line.strip().startswith(call), "the score is never assigned, so it can never gate the release"
