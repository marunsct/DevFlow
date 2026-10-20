"""Every stage that judges the work reads the facts the stages that build it were given (plan CM.1).

Measured on one run: every fixer was told which code the product does not run,
and the milestone review that accepted the release was not - it passed a
product whose planned modules, 59% of its lines, nothing imported. Earlier, a
review undid the file-database fallback the architect had been told to plan.
One function writes the facts; each builder and judge request ends with them.
"""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest

from app.agents import shared_facts
from app.agents.shared_facts import HEADING, facts_from_the_workspace, the_facts_section, with_the_facts

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

GRAPH = Path(__file__).resolve().parent.parent / "src" / "app" / "graph"

#: The request builders of the stages that judge built work.
JUDGES = ("acceptance_review", "advice_review", "milestone_review", "security_review", "code_review", "dispute")
#: And of the stages that build or fix it.
BUILDERS = ("specialist_task", "test_run", "defect_fix")


@pytest.fixture(autouse=True)
def _on(monkeypatch):
    monkeypatch.setenv("SHARED_FACTS", "on")


def test_it_is_off_until_its_before_and_after_runs_switch_it_on(tmp_path, monkeypatch):
    monkeypatch.delenv("SHARED_FACTS")
    assert shared_facts.ON_BY_DEFAULT is False and not shared_facts.enabled()
    assert the_facts_section(_workspace(tmp_path)) == ""


def _workspace(tmp_path: Path) -> Path:
    (tmp_path / ".harness").mkdir()
    (tmp_path / ".harness" / "stack-pack.json").write_text(json.dumps(
        {"pack": "fullstack-react-fastapi", "project": "app", "package": "board", "title": "Board"}))
    for name, text in {
        "src/App.tsx": "export function App() {}\nexport function login() {}\nexport function useAuth() {}\n",
        "src/main.tsx": "import { App } from './App';\n",
        "src/contexts/Auth.tsx": "export function login() {}\nexport function useAuth() {}\n",
        "board/main.py": "app = object()\n",
    }.items():
        path = tmp_path / "app" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return tmp_path


def test_a_judge_reads_the_layout_and_the_code_the_product_does_not_run(tmp_path):
    root = _workspace(tmp_path)

    section = the_facts_section(root)

    assert HEADING in section
    assert "- What the product serves, and the acceptance suite runs through: `app/src/App.tsx`, `app/board/main.py`." in section
    assert "- Where the data lives:" in section
    assert "Code the product does not run:" in section and "`app/src/contexts/Auth.tsx`" in section


def test_a_stage_still_building_reads_the_layout_alone(tmp_path):
    root = _workspace(tmp_path)

    facts = facts_from_the_workspace(root, built=False)

    assert facts and not any("does not run" in line or "stub" in line for line in facts)
    assert all(line in facts_from_the_workspace(root) for line in facts)


def test_before_a_pack_is_set_up_a_request_is_left_as_it_was(tmp_path):
    request = {"messages": [{"role": "user", "content": "Review this."}]}
    assert with_the_facts(request, tmp_path)["messages"][-1]["content"] == "Review this."


def test_every_judge_and_builder_request_in_the_graph_ends_with_the_facts():
    sources = {path.name: path.read_text(encoding="utf-8") for path in GRAPH.glob("*.py")}
    missing = []
    for name in (*JUDGES, *BUILDERS):
        calls = [
            (file, text.count("\n", 0, match.start()))
            for file, text in sources.items()
            for match in re.finditer(rf"\bbuild_{name}_request\(", text)
            if not text[max(0, match.start() - 4):match.start()].endswith("def ")
        ]
        assert calls, f"no call of build_{name}_request in the graph"
        for file, line in calls:
            following = "\n".join(sources[file].splitlines()[max(0, line - 3):line + 45])
            if "with_the_facts(" not in following:
                missing.append(f"{file}:{line + 1} build_{name}_request")
    assert not missing, missing


def test_the_one_shot_drafts_and_rewrites_and_the_architect_read_the_same_function():
    from app.graph import drafting, rewritten_fixes, workflow

    assert "the_facts_section(root, built=False)" in inspect.getsource(drafting.draft_request)
    assert "the_facts_section(root)" in inspect.getsource(rewritten_fixes.fix_request)
    assert "layout_facts(" in inspect.getsource(workflow._the_scaffold_s_facts)


def test_the_new_lines_name_no_ui_control_or_unit_of_work():
    source = inspect.getsource(shared_facts)
    said = " ".join(re.findall(r'f?"([^"\n]*)"', source))
    assert not BANNED.search(said), BANNED.findall(said)
