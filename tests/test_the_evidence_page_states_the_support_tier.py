"""The review and release evidence page states the run's support tier (Initiative AG).

It was stated in the stack decision only, not where a reader of the result looks.
"""

from __future__ import annotations

import json

from app.graph import delivery


def _state(root):
    return {"repository": type("R", (), {"root_path": str(root)})()}


def test_a_run_no_pack_covers_is_marked_custom(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(delivery, "_root", lambda state: str(tmp_path))
    page = delivery.evidence(_state(tmp_path), 1, "the goal")
    assert "Support tier: custom stack" in page


def test_a_pack_run_names_its_pack(tmp_path, monkeypatch) -> None:
    (tmp_path / ".harness").mkdir()
    (tmp_path / ".harness" / "stack-pack.json").write_text(json.dumps({"pack": "fullstack-react-fastapi", "project": "x"}))
    monkeypatch.setattr(delivery, "_root", lambda state: str(tmp_path))
    page = delivery.evidence(_state(tmp_path), 1, "the goal")
    assert "Support tier: pack-supported - the fullstack-react-fastapi pack" in page
