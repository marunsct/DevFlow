"""Fast delivery can be told to run the judgement model's code review (Q amendment); it is off by default."""
from __future__ import annotations

from types import SimpleNamespace

from app import delivery
from app.graph import engineering


def test_it_is_off_unless_the_owner_sets_it():
    assert delivery.reviews_code_when_fast({}) is False
    assert delivery.reviews_code_when_fast({"FAST_CODE_REVIEW": "true"}) is True
    assert delivery.reviews_code_when_fast({"FAST_CODE_REVIEW": "no"}) is False


def test_a_fast_run_with_it_on_reaches_the_review(tmp_path, monkeypatch):
    monkeypatch.setattr(delivery, "fast", lambda environment=None: True)
    monkeypatch.setattr(delivery, "reviews_code_when_fast", lambda environment=None: True)
    monkeypatch.setattr(engineering.ci, "load", lambda root, label: None)
    monkeypatch.setattr(engineering.ci, "diff_since", lambda root, commit: "")
    monkeypatch.setattr(engineering, "_root", lambda state: str(tmp_path))
    reached = []
    monkeypatch.setattr(engineering.ci, "diff_since", lambda root, commit: reached.append(1) or "")

    update = engineering.code_review({}, {}, SimpleNamespace())

    assert reached == [1] and update["stage"] == "test_and_triage"


def test_a_fast_run_with_it_off_skips_the_review(tmp_path, monkeypatch):
    monkeypatch.setattr(delivery, "fast", lambda environment=None: True)
    monkeypatch.setattr(delivery, "reviews_code_when_fast", lambda environment=None: False)
    monkeypatch.setattr(engineering, "_root", lambda state: str(tmp_path))
    monkeypatch.setattr(engineering.ci, "diff_since", lambda root, commit: (_ for _ in ()).throw(AssertionError("reviewed")))

    assert engineering.code_review({}, {}, SimpleNamespace())["stage"] == "test_and_triage"
