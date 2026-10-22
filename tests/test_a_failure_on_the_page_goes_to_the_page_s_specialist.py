"""In a product with a page and a service, a failure met on the page goes to the page's specialist.

One run handed every defect to the backend specialist; every page test had
failed its first control on the scaffold's stub page, and no fixer in two
rounds ever wrote the page.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.graph import acceptance_nodes
from app.graph.workflow import _the_served_app_is_the_scaffold_s_stub


def _state(kind):
    return {"stack_selection": SimpleNamespace(technology_stack=SimpleNamespace(product_kind=kind))}


def test_a_page_control_that_never_appeared_is_the_page_s_in_a_fullstack_product(monkeypatch):
    monkeypatch.setattr(acceptance_nodes, "_stack", lambda state: state["stack_selection"].technology_stack)

    assert acceptance_nodes._owner_for(_state("fullstack"), "[AC-1] register: locator.fill: Timeout 3000ms exceeded.") == "ui_ux"
    assert acceptance_nodes._owner_for(_state("fullstack"), "page.goto: net::ERR_CONNECTION_REFUSED") == "ui_ux"
    assert acceptance_nodes._owner_for(_state("fullstack"), "POST /api/tasks answered 500") == "backend"
    assert acceptance_nodes._owner_for(_state("browser_app"), "") == "ui_ux"
    assert acceptance_nodes._owner_for(_state("http_api"), "locator.fill: Timeout") == "backend"


def test_a_stub_page_component_is_the_page_s_and_a_stub_service_the_service_s():
    assert _the_served_app_is_the_scaffold_s_stub("app/src/App.tsx", "backend").owner == "ui_ux"
    assert _the_served_app_is_the_scaffold_s_stub("app/pkg/main.py", "backend").owner == "backend"
