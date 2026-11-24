"""A review is handed the files it judges in its project memory, numbered, instead of reading them by tool (LF.1284).

Measured on one medium run (19-21 files): the code review read 19 files six to eight times each over twenty minutes,
the security review made 155 reads of 21 files and was summarised 11 times in 31 calls, and the
security-and-reliability advice review made 112 reads with 6 summaries in 19 calls. Each was told to open what its
request did not show; the reads went into the conversation, a summary dropped them, and the review read them again.
A product whose files today's request and memory already show is sent exactly as before.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.runnables.config import var_child_runnable_config

from app import ci
from app.agents import project_memory
from app.agents.security_reviewer import SecurityReviewOutput, build_security_review_request
from app.agents.specialists import SpecialistOutput
from app.graph import engineering
from app.tools.version_control import initialise_repository
from workflow_node_stubs import run_node, two_work_orders

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
HELD = "Held whole in the project memory for this review"
NUMBERED = "(numbered lines, under review)"
CONFIG = {"configurable": {"thread_id": "t"}}


def _settings(monkeypatch, window: int) -> None:
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", str(window))
    monkeypatch.setenv("PROJECT_MEMORY", "on")
    # On in every run: the memory's order does not follow the request (the premium project-intelligence bundle).
    monkeypatch.setenv("CANONICAL_MEMORY", "on")


def _routes(root, count: int, size: int, suffix: str = ".py") -> list[str]:
    names = []
    for n in range(count):
        name = f"app/routes/r{n:02}{suffix}"
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        body = f'VALUE_{n:02} = "route {n}"\n' + "".join(f"# what route {n} does, line {k}\n"
                                                        for k in range(size // 32))
        (root / name).write_text(body)
        names.append(name)
    return names


def _specification(root, size: int) -> None:
    (root / "docs").mkdir(exist_ok=True)
    sections = "".join(f"## Section {k}\n" + "The product keeps its records.\n" * 30 for k in range(size // 960))
    (root / "docs" / "technical_specification.md").write_text("# Specification\n" + sections)


def _security_review(monkeypatch, root, changed: list[str]) -> str:
    seen = run_node(monkeypatch, root, "security_review", answer=SecurityReviewOutput(status="passed"),
                    milestone_plan=two_work_orders(),
                    specialist_outputs={"specialist_backend_0": SpecialistOutput(changed_files=changed)},
                    overrides={"app.graph.workflow._in_parallel_mode": lambda: False})
    ((stage, request),) = seen.requests
    assert stage == "security_review"
    return request["messages"][-1]["content"]


def _memory(root, opening: str, stage: str) -> tuple[str, dict[str, str]]:
    return project_memory.render_for_a_stage(root, None, opening, stage)


def test_a_review_s_memory_holds_the_code_under_review_before_the_plans(tmp_path, monkeypatch):
    _settings(monkeypatch, 65_536)
    _specification(tmp_path, 58_000)
    changed = _routes(tmp_path, 12, 3_000)

    opening = _security_review(monkeypatch, tmp_path, changed)
    memory, held = _memory(tmp_path, opening, "security_review")

    assert set(changed) <= set(held)
    assert memory.index("=== app/routes/r00.py") < memory.index("=== docs/technical_specification.md")
    assert '     1\tVALUE_00 = "route 0"' in memory, "numbered, so a finding cites a line without a read"


def test_a_security_review_shows_a_product_in_any_language(tmp_path):
    sources = {"main.go": "package main\n\nfunc main() { serve() }\n",
               "src/lib.rs": "pub fn serve() -> u16 { 8080 }\n",
               "src/main/java/App.java": "public class App { public static void main(String[] a) {} }\n"}
    for name, text in sources.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text)

    request = build_security_review_request(list(sources), "none", str(tmp_path))["messages"][0]["content"]

    assert all(text in request for text in sources.values())
    assert "None of the changed files could be read" not in request


def test_a_review_is_not_told_to_open_files_it_already_holds(tmp_path, monkeypatch):
    _settings(monkeypatch, 262_144)
    _specification(tmp_path, 5_000)
    changed = _routes(tmp_path, 30, 3_000)

    opening = _security_review(monkeypatch, tmp_path, changed)
    _, held = _memory(tmp_path, opening, "security_review")

    assert set(changed) <= set(held)
    assert "Open each of them" not in opening and "not shown" not in opening
    assert opening.count("VALUE_05 = ") == 0, "a held file is not repeated in the request"
    assert HELD in opening and "`app/routes/r29.py`" in opening


def _code_review(monkeypatch, root) -> tuple[str, str]:
    seen: list = []

    def gated(state, config, **kwargs):
        seen.append((kwargs["stage_name"], kwargs["initial_request"]["messages"][0]["content"]))
        from app.agents.code_reviewer import CodeReviewOutput

        return {kwargs["output_key"]: CodeReviewOutput(approved=True), "stage": "code_review"}

    monkeypatch.setattr("app.graph.workflow._run_gated_agent", gated)
    monkeypatch.setattr("app.agents.code_reviewer.create_code_reviewer_agent", lambda *a, **k: object())
    state = {"repository": SimpleNamespace(root_path=str(root)), "review_defects": [],
             "milestone_plan": SimpleNamespace(delegated_tasks=[
                 SimpleNamespace(title="Routes", task_description="Write the routes", specialist_role="backend")])}
    engineering.code_review(state, CONFIG, SimpleNamespace(judgement_model=None, checkpointer=None, repo_root=None,
                                                           allow_subdirectories=True))
    ((stage, opening),) = seen
    return stage, opening


def _a_first_sprint(root, count: int, size: int) -> tuple[list[str], str]:
    initialise_repository(root)
    ci.save(root, ci.Snapshot(label="accepted", commit=ci.head(root)), accepted=True)
    changed = _routes(root, count, size)
    ci.commit(root, "the first sprint's routes")
    return changed, ci.load(root, "accepted").commit


def test_a_new_file_is_not_sent_as_a_diff_and_as_itself(tmp_path, monkeypatch):
    _settings(monkeypatch, 65_536)
    _specification(tmp_path, 40_000)
    changed, _ = _a_first_sprint(tmp_path, 12, 3_000)

    stage, opening = _code_review(monkeypatch, tmp_path)
    memory, _ = _memory(tmp_path, opening, stage)

    both = opening + memory
    assert [both.count(f"VALUE_{n:02} = ") for n in range(len(changed))] == [1] * len(changed)


def test_a_product_whose_files_fit_is_reviewed_as_before(tmp_path, monkeypatch):
    """Guard: a small product's security, advice and code review requests and memories carry nothing of this."""
    _settings(monkeypatch, 65_536)
    _specification(tmp_path, 3_000)
    changed, since = _a_first_sprint(tmp_path, 3, 300)

    security = _security_review(monkeypatch, tmp_path, changed)
    advice = run_node(monkeypatch, tmp_path, "advice_review", answer=SimpleNamespace(not_built=[], design_problems=[]),
                      milestone_plan=two_work_orders(), specialist_advice={"backend": ["Validate every input."]},
                      technical_specification=SimpleNamespace(specialist_advice_decisions=[], interface_design=[]),
                      specialist_outputs={"specialist_backend_0": SpecialistOutput(changed_files=changed)})
    ((advice_stage, advice_request),) = advice.requests
    stage, code = _code_review(monkeypatch, tmp_path)

    for name in changed:
        assert f"--- {name} ---\n{(tmp_path / name).read_text()}" in security
    assert f"--- The diff ---\n{ci.diff_since(tmp_path, since)}\n" in code
    for each, at in ((security, "security_review"), (advice_request["messages"][-1]["content"], advice_stage),
                     (code, stage)):
        assert HELD not in each
        assert NUMBERED not in _memory(tmp_path, each, at)[0]


def test_a_milestone_review_of_a_product_past_its_room_holds_the_changed_files(tmp_path, monkeypatch):
    from app.agents.milestone_reviewer import MilestoneReviewOutput

    _settings(monkeypatch, 65_536)
    _specification(tmp_path, 58_000)
    changed = _routes(tmp_path, 12, 3_000)

    seen = run_node(monkeypatch, tmp_path, "milestone_review",
                    answer=MilestoneReviewOutput(status="accepted", findings=[], acceptance_evidence="ok",
                                                 documentation_reviewed=True, tests_reviewed=True),
                    milestone_plan=two_work_orders(),
                    specialist_outputs={"specialist_backend_0": SpecialistOutput(changed_files=changed)})
    stage, request = seen.requests[0]
    opening = request["messages"][-1]["content"]

    assert HELD in opening
    assert set(changed) <= set(_memory(tmp_path, opening, stage)[1])


def test_an_advice_review_of_a_product_past_its_room_holds_the_changed_files(tmp_path, monkeypatch):
    """The security-and-reliability advice review of the measured run read 112 times: it was given names only."""
    _settings(monkeypatch, 65_536)
    _specification(tmp_path, 58_000)
    changed = _routes(tmp_path, 12, 3_000)

    seen = run_node(monkeypatch, tmp_path, "advice_review", answer=SimpleNamespace(not_built=[], design_problems=[]),
                    milestone_plan=two_work_orders(), specialist_advice={"backend": ["Validate every input."]},
                    technical_specification=SimpleNamespace(specialist_advice_decisions=[], interface_design=[]),
                    specialist_outputs={"specialist_backend_0": SpecialistOutput(changed_files=changed)})
    ((stage, request),) = seen.requests
    opening = request["messages"][-1]["content"]

    assert HELD in opening
    assert set(changed) <= set(_memory(tmp_path, opening, stage)[1])


def test_a_review_s_first_read_of_a_numbered_file_is_answered_from_the_memory(tmp_path, monkeypatch):
    """With the file numbered in the memory, a copy in the conversation is the one a summary deletes."""
    _settings(monkeypatch, 65_536)
    monkeypatch.setenv("FIRST_REREAD_ANSWERED", "on")  # built in: a held file's first read gets its numbered lines
    _specification(tmp_path, 58_000)
    changed = _routes(tmp_path, 12, 3_000)
    opening = _security_review(monkeypatch, tmp_path, changed)
    middleware = project_memory.build_project_memory_middleware(str(tmp_path))

    class Request(SimpleNamespace):
        def override(self, **changes):
            return Request(**{**self.__dict__, **changes})

    token = var_child_runnable_config.set({"configurable": {"app_stage": "security_review"}})
    try:
        middleware.wrap_model_call(Request(messages=[HumanMessage(content=opening)], model=None), lambda r: None)
        read = SimpleNamespace(tool_call={"name": "read_file", "id": "r1", "args": {"file_path": changed[0]}})
        answer = middleware.wrap_tool_call(read, lambda request: "the file from disk")
    finally:
        var_child_runnable_config.reset(token)

    assert isinstance(answer, ToolMessage) and project_memory.HELD_POINTER in answer.content
    assert "VALUE_00" not in answer.content


def test_what_a_review_is_told_of_its_held_files_uses_none_of_the_banned_words(tmp_path, monkeypatch):
    from app.agents.advice_review import build_advice_review_request
    from app.agents.code_reviewer import build_code_review_request

    (tmp_path / "a.py").write_text("x = 1\n")
    texts = [
        build_security_review_request(["a.py", "b.py"], "", str(tmp_path), held=["b.py"])["messages"][0]["content"],
        build_advice_review_request("backend", [], "", "", ["b.py"], held=["b.py"])["messages"][0]["content"],
        build_code_review_request("", "", "", "", held=["b.py"])["messages"][0]["content"],
    ]
    assert all(HELD in text for text in texts)
    assert not any(BANNED.search(text) for text in texts)
