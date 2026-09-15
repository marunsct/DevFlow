"""A stack selection has to record every choice the brief asks for.

Measured on run-c4f17841 (brief_medium), whose brief names both
"Backend: Python/FastAPI or Node.js/Express" and "Frontend: React or Vue.js":

    {"language": "Python", "framework": "FastAPI", "database": "PostgreSQL",
     "testing_framework": "pytest",
     "additional_tools": ["Celery with Redis", "Prometheus + Grafana"]}

The frontend appears only in the rationale prose, which no later stage reads,
because `TechnologyStack` had one `framework` field and it was spent on the
backend. Celery, Redis, Prometheus and Grafana are in none of the brief's
requirements; the rationale justifies them by "future features like
notifications" and observability.
"""

from __future__ import annotations

from app.agents.tools_models import TechnologyStack


def test_a_full_stack_selection_can_record_both_frameworks():
    stack = TechnologyStack(
        language="Python",
        framework="FastAPI",
        frontend_framework="React",
        database="PostgreSQL",
        testing_framework="pytest",
    )

    assert stack.framework == "FastAPI"
    assert stack.frontend_framework == "React"


def test_a_client_only_product_needs_no_frontend_framework():
    """A static site has no separate frontend to choose."""
    stack = TechnologyStack(
        language="JavaScript",
        framework="none",
        database="localStorage",
        testing_framework="none",
    )

    assert stack.frontend_framework == ""


def test_a_checkpoint_written_before_the_field_existed_still_loads():
    """The field is optional so resuming an older run does not fail."""
    stack = TechnologyStack.model_validate(
        {
            "language": "Python",
            "framework": "FastAPI",
            "database": "PostgreSQL",
            "testing_framework": "pytest",
            "additional_tools": [],
        }
    )

    assert stack.frontend_framework == ""


def test_the_selector_is_told_a_rationale_is_not_a_selection():
    from app.agents.stack_selector import _SYSTEM_PROMPT

    assert "frontend_framework" in _SYSTEM_PROMPT
    assert "not a selection" in _SYSTEM_PROMPT


def test_the_selector_is_told_not_to_tool_for_features_that_do_not_exist():
    """Celery, Redis, Prometheus and Grafana, for an MVP with none of them."""
    from app.agents.stack_selector import _SYSTEM_PROMPT

    assert "does not have yet is not part of this" in _SYSTEM_PROMPT
