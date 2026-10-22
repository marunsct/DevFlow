"""A model's preference between whole-file writes and edits follows what was measured (Initiative BH).

Aider measured whole-file replies 100% well formed against 92-95% for diffs on a
large Qwen; this harness's own `replace_lines` failed 40-68% of the time. The
fitness probe now measures both for the served model and keeps the rates; the
preference is read from them, never assumed.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.models import fitness, registry


def test_the_preference_follows_the_measurement(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    assert registry.edit_preference("m-1") == ""

    registry.record_edit_rates("m-1", {"whole": 1.0, "edit": 0.67})
    assert registry.edit_preference("m-1") == "whole"
    registry.record_edit_rates("m-1", {"whole": 1.0, "edit": 1.0})
    assert registry.edit_preference("m-1") == "edit"
    assert "prefer edits" in registry.describe("m-1")


class _Model:
    """Writes whole files well, and edits with a passage that is not in the file half the time."""

    def __init__(self):
        self.mode, self.asked = "", 0

    def bind_tools(self, tools):
        self.mode = tools[0]["function"]["name"]
        return self

    def invoke(self, messages):
        self.asked += 1
        text = messages[-1].content
        path = text.split("The file ", 1)[1].split(" holds", 1)[0]
        before = text.split("```\n", 1)[1].split("```", 1)[0]
        wanted = next(w for p, b, c, w in fitness.EDIT_SAMPLES if p == path)
        first = before.splitlines()[0]
        if self.mode == "write_file":
            args = {"file_path": path, "content": before + wanted + "\n"}
        elif self.asked % 2:
            args = {"file_path": path, "find": first, "replace": first + "\n" + wanted}
        else:
            args = {"file_path": path, "find": "not in the file", "replace": wanted}
        return SimpleNamespace(tool_calls=[{"name": self.mode, "args": args}])


def test_the_probe_measures_both_forms():
    rates = fitness.edit_probe(_Model())

    assert rates["whole"] == 1.0
    assert 0.3 <= rates["edit"] <= 0.7
