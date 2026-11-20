"""A build stage that drops a declaration the pack holds is told so on its own writes, before it returns.

Measured on one Java run: a work order rewrote `pom.xml` without `<finalName>app</finalName>`, the build made a jar of
another name and the pack's start file (`java -jar target/app.jar`) could not start the product. The pack-contract
check raised it only at the next test round; meanwhile the next stage worked 30 minutes and 76 model calls on a product
that could not start. The same check now runs on the files a stage changed when it ends, with no model call.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from langchain_core.messages import AIMessage, ToolMessage

from app.graph import workflow
from app.stacks import contract, entry_exports, pack_named

BANNED = ("task", "tasks", "to-do", "todo", "button", "click", "checkbox")


def _a_spring_project(tmp_path, monkeypatch, keep_the_jar_name: bool):
    monkeypatch.setenv("PACK_ENTRY_EXPORTS_KEPT", "on")
    pack = pack_named("java-spring-api")
    contract.write(tmp_path, pack, "notes-api", "Notes", None, scaffolded=True)
    for relative, text in pack.render("notes-api", "Notes", None).items():
        (tmp_path / "notes-api" / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "notes-api" / relative).write_text(text)
    if not keep_the_jar_name:
        pom = tmp_path / "notes-api" / "pom.xml"
        pom.write_text(re.sub(r"\s*<finalName>app</finalName>", "", pom.read_text()))
    return {"repository": SimpleNamespace(root_path=str(tmp_path))}


def _it_wrote(path: str) -> dict:
    return {"messages": [
        AIMessage(content="", tool_calls=[{"name": "write_artifact", "id": "w1", "args": {"relative_path": path}}]),
        ToolMessage(content='{"status": "written"}', tool_call_id="w1"),
    ]}


def test_a_stage_that_dropped_the_jar_name_is_told_the_file_and_the_line_to_restore(tmp_path, monkeypatch):
    state = _a_spring_project(tmp_path, monkeypatch, keep_the_jar_name=False)

    told = workflow._diagnostics_in_files_touched(
        state, _it_wrote("notes-api/pom.xml"), SimpleNamespace(changed_files=[]), "specialist_backend_0")

    assert len(told) == 1
    assert "`notes-api/pom.xml`" in told[0]
    assert "Restore this exact line: `<finalName>app</finalName>`" in told[0]


def test_a_whole_file_pass_is_told_it_too(tmp_path, monkeypatch):
    """Drafting and a fix's rewrite are given the same findings for the files they wrote."""
    state = _a_spring_project(tmp_path, monkeypatch, keep_the_jar_name=False)

    told = workflow._diagnostics_in_files_touched(
        state, {"messages": []}, SimpleNamespace(changed_files=["notes-api/pom.xml"]), "drafting",
        most=workflow.MOST_DIAGNOSTICS_FOR_A_PASS)

    assert any("<finalName>app</finalName>" in line and "`notes-api/pom.xml`" in line for line in told)


def test_a_stage_that_kept_the_declaration_is_told_nothing(tmp_path, monkeypatch):
    state = _a_spring_project(tmp_path, monkeypatch, keep_the_jar_name=True)

    told = workflow._diagnostics_in_files_touched(
        state, _it_wrote("notes-api/pom.xml"), SimpleNamespace(changed_files=[]), "specialist_backend_0")

    assert told == []


def test_a_stage_that_did_not_change_the_file_is_not_told_of_it(tmp_path, monkeypatch):
    state = _a_spring_project(tmp_path, monkeypatch, keep_the_jar_name=False)

    told = entry_exports.what_a_stage_broke(state["repository"].root_path, ["notes-api/README.md"])

    assert told == []


def test_the_check_never_raises(tmp_path, monkeypatch):
    state = _a_spring_project(tmp_path, monkeypatch, keep_the_jar_name=False)

    def broken(*_args, **_kwargs):
        raise RuntimeError("unreadable")

    monkeypatch.setattr(entry_exports, "callers_passing_arguments", broken)

    assert entry_exports.what_a_stage_broke(state["repository"].root_path, ["notes-api/pom.xml"]) == []
    assert entry_exports.what_a_stage_broke(str(tmp_path / "nowhere"), ["pom.xml"]) == []
    assert entry_exports.what_a_stage_broke(state["repository"].root_path, 7) == []


def test_what_the_stage_is_asked_uses_none_of_the_banned_words(tmp_path, monkeypatch):
    state = _a_spring_project(tmp_path, monkeypatch, keep_the_jar_name=False)
    told = workflow._diagnostics_in_files_touched(
        state, _it_wrote("notes-api/pom.xml"), SimpleNamespace(changed_files=[]), "specialist_backend_0")
    asked: list[str] = []
    # The follow-up goes to the model; its text is what this reads.
    monkeypatch.setattr(workflow, "_nudge_for_the_structured_response",
                        lambda *args, text="", **kwargs: asked.append(text))

    workflow._ask_about_high_confidence_diagnostics(None, "thread", None, told, None, "specialist_backend_0")

    assert asked and "<finalName>app</finalName>" in asked[0]
    for word in BANNED:
        assert not re.search(rf"\b{re.escape(word)}\b", asked[0], re.IGNORECASE), word
