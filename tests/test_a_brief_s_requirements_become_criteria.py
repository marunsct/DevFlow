"""A brief's requirement and constraint lines that name something the product must have become criteria (plan PQ.1).

Measured on a medium brief: its "User Interface: Modern web application with responsive design", "Frontend: React or
Vue.js", "Database migrations required" and "Docker containerization" became no criterion; the sprint plan put the
interface out of scope in every sprint and the product shipped with none. A brief that already numbers what it asks
for keeps its criteria as they were.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.acceptance import suite
from app.acceptance.criteria import from_brief, number

ROOT = Path(__file__).resolve().parents[1]

MEDIUM = """# Product Brief: Team board

## Requirements
1. **User Interface**: Modern web application with responsive design
2. **Features**:
   - User registration and authentication
   - Create, read, update, delete items
3. **Data Storage**: PostgreSQL database with proper schema

## Technical Constraints
- Backend: Python/FastAPI or Node.js/Express
- Frontend: React or Vue.js
- Database migrations required
- Docker containerization

## Acceptance Criteria
- Users can register, login, logout securely
- API documentation available (Swagger/OpenAPI)
"""


def _texts(brief: str) -> list[str]:
    return [criterion.text for criterion in number(brief)]


def test_an_interface_migrations_and_a_container_the_brief_requires_are_criteria() -> None:
    texts = _texts(MEDIUM)

    assert texts[:4] == [
        "User registration and authentication", "Create, read, update, delete items",
        "Users can register, login, logout securely", "API documentation available (Swagger/OpenAPI)",
    ]
    assert texts[4:] == [
        "User Interface: Modern web application with responsive design",
        "Database migrations required",
        "Docker containerization",
    ]


def test_a_kind_an_existing_criterion_carries_is_not_added_again() -> None:
    """"Frontend: React or Vue.js" asks for the interface the "User Interface" line already added; the API documentation
    is the brief's own criterion."""
    texts = _texts(MEDIUM)

    assert "Frontend: React or Vue.js" not in texts
    assert sum("Swagger" in text for text in texts) == 1


@pytest.mark.parametrize("family", ["web-todo", "web-todo-react", "fullstack-bookmarks", "notes-api", "wordstats-cli",
                                    "textkit-lib", "tasks-api", "tasks-api-change"])
def test_a_benchmark_brief_keeps_the_criteria_it_lists(family: str) -> None:
    """Their interface, storage and stack lines are carried by their own criteria or are choices of how it is built."""
    brief = (ROOT / "benchmarks" / family / "brief.md").read_text(encoding="utf-8")

    assert set(_texts(brief)) <= set(from_brief(brief))


@pytest.mark.parametrize("line", [
    "- Database migrations not required",
    "- No Docker",
    "- Runs without a container",
])
def test_a_line_that_rules_a_kind_out_asks_for_nothing(line: str) -> None:
    brief = "# B\n## Features\n- Add a note\n- Delete a note\n## Technical Constraints\n" + line + "\n"

    assert _texts(brief) == ["Add a note", "Delete a note"]


def test_a_terminal_program_s_user_interface_line_is_no_page() -> None:
    brief = ("# B\n## Requirements\n1. **User Interface**: a command-line program\n2. **Features**:\n"
             "   - Count the words\n   - Count the lines\n")

    assert _texts(brief) == ["Count the words", "Count the lines"]


def test_an_out_of_scope_list_asks_for_nothing() -> None:
    brief = "# B\n## Features\n- Add a note\n- Delete a note\n## Out of scope\n- Docker containerization\n"

    assert _texts(brief) == ["Add a note", "Delete a note"]


# --- the decision log --------------------------------------------------------------------------------------------

@pytest.fixture
def gated(monkeypatch):
    """The QA author's model answering with no blockers; the product planned as one sprint."""
    monkeypatch.setenv("DELIVERY_MODE", "fast")
    monkeypatch.setattr("app.graph.workflow._run_gated_agent",
                        lambda state, config, *, stage_name, agent, initial_request, output_key, next_stage:
                        {output_key: SimpleNamespace(blockers=[]), "stage": next_stage})
    monkeypatch.setattr("app.agents.specialists.create_specialist_agent", lambda *a, **k: object())


def _state(root: Path, brief: str) -> dict[str, Any]:
    (root / ".project-directory").write_text("board\n")
    (root / "board").mkdir(exist_ok=True)
    return {
        "repository": SimpleNamespace(root_path=str(root)),
        "document": SimpleNamespace(text=brief),
        "product_intake": SimpleNamespace(product_name="Board", success_measures=[]),
        "stack_selection": SimpleNamespace(technology_stack=SimpleNamespace(product_kind="fullstack")),
    }


def _author(root: Path, brief: str) -> dict[str, Any]:
    from app.graph import acceptance_nodes as nodes

    ctx = nodes.Context(model=None, judgement_model=None, checkpointer=None, repo_root=None)
    return nodes.acceptance_author(_state(root, brief), {"configurable": {"thread_id": "t"}}, ctx)


def test_what_was_added_and_what_carries_each_line_is_a_recorded_decision(tmp_path, gated) -> None:
    update = _author(tmp_path, MEDIUM)

    [record] = update["decisions"]
    assert record["point"] == "acceptance_tests"
    assert record["decision"].startswith("AC-5, AC-6, AC-7 added")
    why = record["rationale"]
    assert '"Frontend: React or Vue.js": carried by AC-5' in why
    assert '"Docker containerization": added as AC-7' in why
    assert '"Backend: Python/FastAPI or Node.js/Express": a choice of how the product is built' in why
    assert "not built in this release" in why
    assert "AC-7" in (tmp_path / "docs" / "decision_log.md").read_text(encoding="utf-8")
    assert [c.id for c in suite.criteria(tmp_path)][-1] == "AC-7"


def test_a_brief_that_lists_what_it_asks_for_records_no_such_decision(tmp_path, gated) -> None:
    brief = (ROOT / "benchmarks" / "web-todo" / "brief.md").read_text(encoding="utf-8")

    update = _author(tmp_path, brief)

    assert not update.get("decisions")


# --- a behaviour a constraint line states (plan PQ.1, the rest) ------------------------------------------------------

#: The medium brief as it was uploaded: its constraint "Authentication: JWT tokens with refresh mechanism" became no
#: criterion, because "User registration and authentication (JWT-based)" carried the line's kind.
DASHBOARD = (ROOT / "tests" / "captured" / "brief-a-task-management-dashboard.md").read_text(encoding="utf-8")


def test_a_behaviour_stated_under_the_constraints_is_a_criterion() -> None:
    texts = _texts(DASHBOARD)

    assert texts[-1] == "Authentication: JWT tokens with refresh mechanism"
    assert texts.count("Authentication: JWT tokens with refresh mechanism") == 1


def test_the_behaviour_added_is_named_in_the_decision(tmp_path, gated) -> None:
    update = _author(tmp_path, DASHBOARD)

    [record] = update["decisions"]
    assert '"Authentication: JWT tokens with refresh mechanism": added as AC-17' in record["rationale"]
    assert 'the behaviour "refresh mechanism"' in record["rationale"]


@pytest.mark.parametrize("line", [
    "- Java, with Spring Boot",
    "- React with TypeScript, built with Vite",
    "- Data Storage: PostgreSQL database with proper schema",
    "- Authentication: JWT tokens without refresh",
])
def test_a_technology_or_a_quality_after_with_stays_a_constraint(line: str) -> None:
    brief = "# B\n## Features\n- Add a note\n- Delete a note\n## Technical Constraints\n" + line + "\n"

    assert _texts(brief) == ["Add a note", "Delete a note"]


def test_a_behaviour_a_criterion_already_names_is_not_added_again() -> None:
    brief = ("# B\n## Features\n- Sign in\n- A signed-in person's session is refreshed before it expires\n"
             "## Technical Constraints\n- Authentication: JWT tokens with refresh mechanism\n")

    assert _texts(brief) == ["Sign in", "A signed-in person's session is refreshed before it expires"]
