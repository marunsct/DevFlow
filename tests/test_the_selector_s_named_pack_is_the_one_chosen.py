"""A pack the stack selector named in its rationale is chosen when a field was left out.

Measured on one run: the selector's rationale read "The available stack
'Browser app in React with its own HTTP service in FastAPI' matches the
brief's constraints ... React was chosen over Vue.js", and its frontend field
read "not stated". A full-stack pack fits only the component framework the
stack names, so none fitted, and the agents set a medium project up by hand
where the run before it had a proven scaffold.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.stacks import choose_pack

RATIONALE = (
    "The available stack 'Browser app in React with its own HTTP service in FastAPI' matches "
    "the brief's constraints. React was chosen over Vue.js."
)


def _stack(frontend: str = "not stated", framework: str = "FastAPI") -> SimpleNamespace:
    return SimpleNamespace(
        language="Python and TypeScript", framework=framework, frontend_framework=frontend,
        database="PostgreSQL", testing_framework="Vitest, pytest, Playwright", product_kind="fullstack",
    )


def test_the_measured_stack_gets_the_pack_its_rationale_chose():
    assert choose_pack(_stack(), "A task dashboard", rationale=RATIONALE).name == "fullstack-react-fastapi"


def test_without_the_rationale_nothing_is_guessed():
    assert choose_pack(_stack(), "A task dashboard") is None


def test_a_framework_the_stack_did_name_still_decides():
    """The rationale cannot override a field the stack filled in: Vue named, React's pack refused."""
    assert choose_pack(_stack(frontend="Vue"), "A task dashboard", rationale=RATIONALE).name == "fullstack-vue-fastapi"
    assert choose_pack(_stack(framework="Django"), "A task dashboard", rationale=RATIONALE).name == "fullstack-django"


def test_two_packs_named_settles_nothing():
    both = RATIONALE + " The available stack 'Browser app in Vue with its own HTTP service in FastAPI' would do too."
    assert choose_pack(_stack(), "A task dashboard", rationale=both) is None
