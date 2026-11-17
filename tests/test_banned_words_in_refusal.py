from __future__ import annotations

import re
import uuid

import pytest


@pytest.mark.parametrize("lines", [3, 80], ids=["a short file, shown", "a long file, to be read"])
def test_no_banned_words_in_unseen_file_refusal_prompt(tmp_path, monkeypatch, lines) -> None:
    """The refusal a stage gets for writing over another stage's file it has not seen."""
    from app.agents import stage_memory
    from app.analysis import project_memory
    from app.tools.repository import RepositoryToolError, write_approved_artifact

    stage_memory.forget_everything()
    monkeypatch.setattr(stage_memory, "current_stage_key", lambda: f"t-{uuid.uuid4()}:specialist_ui_ux_0")
    monkeypatch.setattr("app.observability.transcript._stage_from_config", lambda fallback: "specialist_ui_ux_0")
    (tmp_path / "notes-app").mkdir()
    (tmp_path / "notes-app" / "page.html").write_text("".join(f"<p>{n}</p>\n" for n in range(lines)), encoding="utf-8")
    project_memory.record(tmp_path, "notes-app/page.html", "specialist_backend_4")

    with pytest.raises(RepositoryToolError) as refused:
        write_approved_artifact(tmp_path, "notes-app/page.html", "<main></main>\n")
    stage_memory.forget_everything()

    message = str(refused.value)
    assert "'specialist_backend_4' wrote the version there now" in message
    for word in ("task", "tasks", "to-do", "todo", "button", "click", "checkbox"):
        assert not re.search(rf"\b{re.escape(word)}\b", message, re.IGNORECASE), word



def test_no_banned_words_in_read_only_rules() -> None:
    from app.agents import role_agent
    banned = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")
    found = False
    for line in role_agent._READ_ONLY_RULES.splitlines():
        if "Do not call tools to edit or write files" in line or "Any code or verification changes" in line:
            found = True
            for word in banned:
                assert not re.search(
                    rf"\b{re.escape(word)}\b", line, re.IGNORECASE
                ), f"Found banned word '{word}' in line: {line}"
    assert found


def test_no_banned_words_in_technical_lead_file_modification_rules() -> None:
    from app.agents import technical_lead
    banned = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")
    found = False
    for line in technical_lead._SYSTEM_PROMPT.splitlines():
        if "Do not modify application source code" in line or "Do not attempt to change repository files directly" in line:
            found = True
            for word in banned:
                assert not re.search(
                    rf"\b{re.escape(word)}\b", line, re.IGNORECASE
                ), f"Found banned word '{word}' in line: {line}"
    assert found


