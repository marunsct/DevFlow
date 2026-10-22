"""`docs/STATE.md` is the one file a session must read, and it stays short (plan MF.6).

A session read about 12,000 lines - some 150,000 tokens - before acting, and
the plan grew by about thirty rows a day.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "docs" / "STATE.md"


def test_it_exists_and_stays_within_150_lines():
    lines = STATE.read_text(encoding="utf-8").splitlines()
    assert 0 < len(lines) <= 150, len(lines)


def test_it_says_what_is_live_what_is_off_the_last_runs_and_the_next_action():
    text = STATE.read_text(encoding="utf-8")
    for heading in ("## Live now", "## Off until measured", "## The last three runs", "## Next actions"):
        assert heading in text, heading


def test_the_agent_instructions_send_a_session_there_first():
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert agents.index("docs/STATE.md") < agents.index("docs/HANDOVER.md")


def test_old_narratives_live_in_the_archive_not_the_handovers():
    assert (ROOT / "docs" / "archive" / "handover-before-2026-10-14.md").is_file()
    assert "### 2.1 What changed on 2026-10-12" not in (ROOT / "docs" / "HANDOVER.md").read_text(encoding="utf-8")
