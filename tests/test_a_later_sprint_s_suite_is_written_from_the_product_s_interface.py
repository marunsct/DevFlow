"""A later sprint's suite writer is handed the product's interface, not its source (PA.12).

Measured on one medium run: a later sprint's acceptance suite writer, one visit of 30 minutes, made 123 model calls,
118 of them reads and 3 writes - the product's schemas read 21 times, a service 19, an earlier sprint's test file 21.
Across the run the writer made 764 reads of 43 files, about half of them the product's source, read for the routes,
the shapes they take and give and the earlier tests' helpers. These drive the real nodes on a three-sprint plan, as
`test_the_suite_is_written_a_sprint_at_a_time` does; the model calls and the sandbox's edge are the stand-ins.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.agents import project_memory

from test_the_suite_is_written_a_sprint_at_a_time import (
    CONFIG, CTX, PROJECT, RealPytest, Writers, _plan, _state, _workspace, nodes, suite,
)

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

ROUTES = '''from fastapi import APIRouter

from .schemas import ItemCreate, ItemOut

router = APIRouter(prefix="/items")


@router.post("/", status_code=201)
def create_item(
    payload: ItemCreate,
) -> ItemOut:
    return save(payload)


def save(payload):
    kept = dict(payload)  # INNER_WORKINGS of the product
    return kept
'''
SCHEMAS = '''from pydantic import BaseModel


class Tag(BaseModel):
    label: str


class ItemCreate(BaseModel):
    name: str
    tags: list[Tag] = []


class ItemOut(BaseModel):
    id: int
    name: str


class NeverNamed(BaseModel):
    UNUSED_FIELD: str
'''
MAIN = '''from fastapi import FastAPI

from . import routes

app = FastAPI()
app.include_router(routes.router, prefix="/api")
'''
HELPERS = '''import json


def make_item(client, name: str = "first") -> dict:
    return json.loads(client.post("/api/items/", json={"name": name}).text)
'''


class Recorded(Writers):
    """QA's agent loop at its edge, recording the memory each writer stage would open on."""

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.memories: list[str] = []

    def __call__(self, state, config, *, stage_name, agent, initial_request, output_key, next_stage):
        if output_key == "__acceptance_author__":
            text = initial_request["messages"][-1]["content"]
            self.memories.append(project_memory.render_for_a_stage(self.root, None, text, stage_name)[0])
        return super().__call__(state, config, stage_name=stage_name, agent=agent, initial_request=initial_request,
                                output_key=output_key, next_stage=next_stage)


def _write_and_lock(root: Path, index: int) -> dict:
    state = _state(root, sprint_plan=_plan(), current_sprint_index=index)
    started = nodes.sprint_acceptance(state, CONFIG, CTX)
    written = nodes.acceptance_author({**state, **started}, CONFIG, CTX)
    return nodes.acceptance_review({**state, **started, **written}, CONFIG, CTX)


@pytest.fixture
def sprint_two(tmp_path, monkeypatch):
    """Sprint one's tests locked with a helper of theirs, its product built, and sprint two's tests written."""
    monkeypatch.setenv("DELIVERY_MODE", "thorough")
    writers = Recorded(_workspace(tmp_path))
    runner = RealPytest(tmp_path)
    monkeypatch.setattr("app.graph.workflow._run_gated_agent", writers)
    monkeypatch.setattr("app.agents.specialists.create_specialist_agent", lambda *a, **k: object())
    monkeypatch.setattr("app.agents.acceptance_reviewer.create_acceptance_reviewer_agent", lambda *a, **k: object())
    monkeypatch.setattr(suite, "_sandbox_runner", lambda root: runner)
    nodes.acceptance_author(_state(tmp_path), CONFIG, CTX)
    writers.also = {f"{PROJECT}/acceptance/helpers.py": HELPERS}
    _write_and_lock(tmp_path, 0)
    writers.also = {}
    app = tmp_path / PROJECT / "app"
    app.mkdir(parents=True, exist_ok=True)
    for name, text in (("routes.py", ROUTES), ("schemas.py", SCHEMAS), ("main.py", MAIN), ("__init__.py", "")):
        (app / name).write_text(text)
    _write_and_lock(tmp_path, 1)
    return writers


def _the_section(request: str) -> str:
    return request.split("--- The product as the earlier sprints built it")[1].split("\n--- ")[0]


def test_its_request_holds_the_routes_the_code_declares_with_their_handlers(sprint_two):
    section = _the_section(sprint_two.asked[-1][1])

    assert "`items/app/routes.py:8`" in section and '@router.post("/", status_code=201)' in section
    assert "def create_item( payload: ItemCreate, ) -> ItemOut:" in section
    assert "`items/app/main.py:6`" in section and 'prefix="/api"' in section, "where a group of routes is mounted"
    assert 'APIRouter(prefix="/items")' in section


def test_its_request_holds_the_shapes_those_handlers_take_and_give(sprint_two):
    section = _the_section(sprint_two.asked[-1][1])

    assert "class ItemCreate(BaseModel):" in section and "tags: list[Tag] = []" in section
    assert "class ItemOut(BaseModel):" in section and "id: int" in section
    assert "class Tag(BaseModel):" in section, "a shape a shape names"
    assert "UNUSED_FIELD" not in section, "only the shapes the routes name"
    assert "INNER_WORKINGS" not in section


def test_its_request_holds_the_signatures_of_the_earlier_tests_helpers(sprint_two):
    section = _the_section(sprint_two.asked[-1][1])

    assert "`items/acceptance/helpers.py:4`" in section
    assert 'def make_item(client, name: str = "first") -> dict:' in section
    assert "json.loads" not in section, "the signature, not the body"
    assert "test_ac1_holds" not in section, "a test is no helper"


def test_its_memory_leaves_the_product_s_source_out_and_says_so(sprint_two):
    memory = sprint_two.memories[-1]

    assert "INNER_WORKINGS" not in memory and "=== items/app/routes.py" not in memory
    assert "Not included: the product's source, 4 files" in memory and "items/app/schemas.py" in memory
    assert f"=== {PROJECT}/acceptance/helpers.py ===" in memory, "the earlier sprint's tests are still held"


def test_the_first_sprint_s_writers_are_handed_neither(sprint_two):
    first_request = sprint_two.asked[0][1]

    assert "--- The product as the earlier sprints built it" not in first_request
    assert "Not included: the product's source" not in sprint_two.memories[0]


def test_another_stage_still_holds_the_product_s_source(sprint_two):
    memory, _ = project_memory.render_for_a_stage(sprint_two.root, None, "Review the sprint.", "code_review_0_0")

    assert "INNER_WORKINGS" in memory


def test_the_section_is_bounded_on_a_large_product(tmp_path):
    from app.acceptance import product_interface

    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "routes.py").write_text("".join(
        f'@router.get("/things/{n}")\ndef thing_{n}(payload: Shape{n}) -> Shape{n}:\n    return {n}\n\n\n'
        for n in range(400)))
    (tmp_path / "app" / "shapes.py").write_text("".join(
        f"class Shape{n}(BaseModel):\n" + "".join(f"    field_{k}: str\n" for k in range(40)) + "\n\n"
        for n in range(400)))

    section = product_interface.block(tmp_path, [])

    most = (product_interface.MOST_ROUTE_CHARACTERS + product_interface.MOST_SHAPE_CHARACTERS
            + product_interface.MOST_HELPER_CHARACTERS)
    assert '@router.get("/things/0")' in section and "and 3" in section
    assert len(section) < most + 2_000


@pytest.mark.parametrize("line", [
    '@app.get("/items/{id}")', "router.post('/items', create)", '@GetMapping("/items")',
    'r.HandleFunc("/items", list)', '.route("/items", get(list_items))', "app.use('/api', router)",
])
def test_a_route_is_read_in_each_language_s_spelling(line):
    from app.acceptance import product_interface

    assert product_interface.declares_a_route(line)


@pytest.mark.parametrize("line", [
    'open("/data/notes.db")', 'logger.info("stored in /tmp")', 'DATA = Path("/var/lib")', '# get "/items" later',
])
def test_a_path_that_is_no_route_is_not_read_as_one(line):
    from app.acceptance import product_interface

    assert not product_interface.declares_a_route(line)


def test_the_words_it_adds_hold_to_the_house_rules(sprint_two):
    section = _the_section(sprint_two.asked[-1][1])
    memory = sprint_two.memories[-1]
    added = "\n".join(line for line in section.splitlines() if not line.startswith(("- `", "`", "    ")))
    said = memory[memory.index("Not included: the product's source"):].split("\n")[0]

    assert not BANNED.search(added) and not BANNED.search(re.sub(r"\(.*?\)", "", said))
