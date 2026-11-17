"""A fixer's memory and a whole-file rewrite's request put what holds for every fix first (LR.52, `STABLE_MEMORY_ORDER`).

A prompt cache reuses a request's prefix up to its first differing byte. The fixer's memory led with the code every
fix changes, so the acceptance criteria and the specification behind it, the same for every fixer of a sprint, were
read again on each call. With the switch on the same blocks come documents first; what is held does not change.
"""
from __future__ import annotations

import os
import re
from types import SimpleNamespace

from app.agents import project_memory, stable_memory_order
from app.graph import rewritten_fixes

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

SPEC = "# Technical specification\n\n" + "".join(
    f"## Section {n}\n" + ("Words about something unrelated. " * 60) + "\n\n" for n in range(40)
) + "## Storage\nNotes are saved to DATA_DIR/notes.json and read back on start.\n"
CRITERIA = "# Acceptance criteria\n- AC-1 Notes survive a restart\n- AC-2 A note has a title\n"


def _project(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "technical_specification.md").write_text(SPEC)
    (tmp_path / "docs" / "acceptance_criteria.md").write_text(CRITERIA)
    (tmp_path / "docs" / "sprint_plan.md").write_text("# Sprint plan\n" + "Plans. " * 2000)
    (tmp_path / "notes-api").mkdir()
    (tmp_path / "notes-api" / "storage.py").write_text("def save(note):\n    pass\n")
    (tmp_path / "notes-api" / "titles.py").write_text("def title(note):\n    return ''\n")
    return tmp_path


def _render(root, switch, **kw):
    previous = os.environ.get("STABLE_MEMORY_ORDER")
    os.environ["STABLE_MEMORY_ORDER"] = switch
    try:
        return project_memory.render(root, 200_000, **kw)
    finally:
        if previous is None:
            os.environ.pop("STABLE_MEMORY_ORDER", None)
        else:
            os.environ["STABLE_MEMORY_ORDER"] = previous


def _blocks(text):
    """The memory's blocks, each without the blank line that joins it to the next, and without the closing lists."""
    body = text.split("\nNot included here")[0]
    return sorted(block.strip() for block in re.split(r"(?m)^(?==== )", body) if block.startswith("=== "))


def test_the_switch_is_off_in_code_and_says_its_words(monkeypatch):
    monkeypatch.delenv("STABLE_MEMORY_ORDER", raising=False)
    assert stable_memory_order.ON_BY_DEFAULT is False and not stable_memory_order.enabled()
    monkeypatch.setenv("STABLE_MEMORY_ORDER", "on")
    assert stable_memory_order.enabled()
    assert not BANNED.search(stable_memory_order.SAID)


def test_on_a_fixer_s_memory_leads_with_the_documents(tmp_path):
    root = _project(tmp_path)
    text, held = _render(root, "on", focus="Storage: notes do not survive", for_a_fixer=True)
    assert stable_memory_order.SAID in text
    criteria, spec = text.index("=== docs/acceptance_criteria.md"), text.index("=== docs/technical_specification.md")
    assert criteria < spec < text.index("=== notes-api/storage.py") and spec < text.index("=== notes-api/titles.py")
    assert "DATA_DIR/notes.json" in text and "Plans. Plans." not in text


def test_the_order_changes_and_nothing_else(tmp_path):
    root = _project(tmp_path)
    on, held_on = _render(root, "on", focus="Storage: notes do not survive", for_a_fixer=True)
    off, held_off = _render(root, "off", focus="Storage: notes do not survive", for_a_fixer=True)
    assert stable_memory_order.SAID not in off
    assert off.index("=== notes-api/storage.py") < off.index("=== docs/acceptance_criteria.md")
    assert held_on == held_off and _blocks(on) == _blocks(off)


def test_two_fixers_share_the_documents_as_one_prefix(tmp_path):
    root = _project(tmp_path)
    first, _ = _render(root, "on", focus="notes-api/storage.py\nStorage: notes do not survive", for_a_fixer=True)
    second, _ = _render(root, "on", focus="notes-api/titles.py\nA note has no title", for_a_fixer=True)
    shared = os.path.commonprefix([first, second])
    assert "AC-2 A note has a title" in shared


def test_another_stage_s_memory_is_the_same_with_the_switch_on(tmp_path):
    root = _project(tmp_path)
    assert _render(root, "on", focus="Plan the sprint.") == _render(root, "off", focus="Plan the sprint.")


def _ask(root, path, defect, failure, switch, monkeypatch):
    monkeypatch.setenv("STABLE_MEMORY_ORDER", switch)
    return rewritten_fixes.fix_request(root, path, defect, failure, None, None, [], [])


STORE = SimpleNamespace(description="Notes are lost on restart", expected_behavior="They survive",
                        actual_behavior="AC-1 failed", affected_files=["notes-api/storage.py"], reproduction_steps=[])
TITLE = SimpleNamespace(description="A note shows no title", expected_behavior="Its title",
                        actual_behavior="AC-2 failed", affected_files=["notes-api/titles.py"], reproduction_steps=[])


def test_on_a_rewrite_s_request_puts_the_project_before_the_defect(tmp_path, monkeypatch):
    root = _project(tmp_path)
    text = _ask(root, "notes-api/storage.py", STORE, "AC-1 failed: notes lost", "on", monkeypatch)
    assert text.index("--- The project ---") < text.index("--- The defect ---") < text.index("--- What failed ---")
    assert text.index("--- The file to correct: `notes-api/storage.py` ---") < text.index("--- The defect ---")
    assert text.rstrip().endswith("reply with it unchanged.")
    off = _ask(root, "notes-api/storage.py", STORE, "AC-1 failed: notes lost", "off", monkeypatch)
    assert off.index("--- The defect ---") < off.index("--- The project ---")
    assert off.startswith("Correct the file `notes-api/storage.py`")


def test_on_two_rewrites_share_their_stable_part(tmp_path, monkeypatch):
    root = _project(tmp_path)
    pair_on = [_ask(root, "notes-api/storage.py", STORE, "AC-1 failed", "on", monkeypatch),
               _ask(root, "notes-api/titles.py", TITLE, "AC-2 failed", "on", monkeypatch)]
    pair_off = [_ask(root, "notes-api/storage.py", STORE, "AC-1 failed", "off", monkeypatch),
                _ask(root, "notes-api/titles.py", TITLE, "AC-2 failed", "off", monkeypatch)]
    assert "AC-2 A note has a title" in os.path.commonprefix(pair_on)
    assert len(os.path.commonprefix(pair_on)) > len(os.path.commonprefix(pair_off))


def test_the_new_words_ban_the_product_s_nouns(tmp_path, monkeypatch):
    root = _project(tmp_path)
    text = _ask(root, "notes-api/storage.py", STORE, "AC-1 failed", "on", monkeypatch)
    first = text.split("\n\n", 1)[0]
    for words in (first, "--- The file to correct:", stable_memory_order.SAID):
        assert not BANNED.search(words.split("The stack:")[0]), words
