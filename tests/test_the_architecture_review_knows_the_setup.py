"""The architecture review judges the specification against the setup it is built in.

Measured live: told where the data lives, the architect wrote the file-database
fallback the setup needs - the service reads `DATABASE_URL` and, unset, keeps a
file database, which is what every test runs on. The reviewer was never told
that, raised it as a major finding ("contradicts the hard constraint 'Database
must be PostgreSQL'"), and the revision made `DATABASE_URL` required with "no
fallback database ... in any environment": a service no test can start.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from app.agents.architecture_reviewer import build_architecture_review_request
from app.agents.stack_selector import StackSelectorOutput, TechnologyStack
from app.graph import workflow

from tests.test_graph_routing import (  # noqa: F401 - the routing tests' fixtures
    ScriptedAgents, _approved_review, _document, _graph, _intake, _repository, _script_through_sprint, _spec,
    _tools, agents, responds_with,
)
from app.graph.workflow import start_workflow

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _fullstack() -> StackSelectorOutput:
    return StackSelectorOutput(
        technology_stack=TechnologyStack(
            language="Python", framework="FastAPI", frontend_framework="React", database="PostgreSQL",
            testing_framework="pytest, Playwright", product_kind="fullstack", additional_tools=[],
        ),
        rationale="A page with its own service.",
    )


def test_the_review_request_carries_the_setup_and_how_to_weigh_it():
    request = build_architecture_review_request(
        "spec", "/", "A brief.", environment="- Where the data lives: a file database under `DATA_DIR`.",
    )
    text = request["messages"][0]["content"]

    assert "a file database under `DATA_DIR`" in text
    assert "not a departure from the brief" in text
    assert not BANNED.search(text.split("--- Technical specification")[0])


def test_the_setup_for_the_review_says_where_the_data_lives(tmp_path):
    (tmp_path / ".project-directory").write_text("board-app\n")
    state = {"stack_selection": _fullstack(), "document": SimpleNamespace(text=""),
             "repository": SimpleNamespace(root_path=str(tmp_path))}

    told = workflow._the_setup_for_the_review(state)

    assert "Where the data lives" in told and "must work on that file database" in told
    assert "`board-app/src/App.tsx`" in told
    assert "write the file plan" not in told and not BANNED.search(told)


def test_the_reviewer_is_handed_it(agents, tmp_path):
    agents.script("product_manager", [responds_with(_intake())])
    agents.script("tools_models", [responds_with(_tools())])
    agents.script("stack_selector", [responds_with(_fullstack())])
    agents.script("principal_architect", [responds_with(_spec())])
    agents.script("architecture_review", [responds_with(_approved_review())])
    _script_through_sprint(agents)

    start_workflow(_graph(), _document(), _repository(tmp_path), "run-review-setup")

    assert "Where the data lives" in agents.last_request_text("architecture_review")
