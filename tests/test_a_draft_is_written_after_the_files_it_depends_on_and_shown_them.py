"""A product's files are drafted in waves of what they depend on, each later file shown the earlier ones it uses.

Deep review 2026-11-18, item 1.6: drafting wrote every product file in one wave, each shown its siblings as they were
on disk - on a first draft, nothing. Measured: a Rust run's handlers took one kind of shared state while the entry
file applied another, and every route answered 500; C# runs declared one interface twice in two files and wrote a
service that called a registry nobody wrote. Behind `DRAFTING_IN_WAVES`.
"""
from __future__ import annotations

import re
import types

import pytest

from app.agents.principal_architect import TechnicalSpecificationOutput
from app.agents.technical_lead import SpecialistTask
from app.graph import drafting
from app.graph.drafting_waves import drafting_waves
from app.observability.switch_firing import fired

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

SHAPES, HANDLERS, ENTRY = "src/models.rs", "src/handlers.rs", "src/main.rs"
WRITTEN = {
    SHAPES: "pub struct AppState { pub notes: Vec<String> }\n",
    HANDLERS: "pub async fn list_notes(State(state): State<AppState>) -> Json<Vec<String>> { Json(state.notes) }\n",
    ENTRY: "fn main() { let app = Router::new().with_state(AppState::default()); }\n",
}


def _specification(*plan: str) -> TechnicalSpecificationOutput:
    return TechnicalSpecificationOutput(file_plan=list(plan))


def _order(*files: str, interfaces: tuple[str, ...] = ()) -> SpecialistTask:
    return SpecialistTask(specialist_role="backend", task_description="build the service",
                          acceptance_criteria=["works"], files=list(files), interfaces=list(interfaces))


class _Model:
    """The model endpoint: answers each file's request with that file's text, and keeps every request it was sent."""

    def __init__(self):
        self.requests: list[tuple[str, str]] = []

    def bind(self, **_):
        return self

    def invoke(self, messages, **_):
        request = messages[-1].content
        path = re.search(r"Write the file `([^`]+)`", request).group(1)
        self.requests.append((path, request))
        return types.SimpleNamespace(content=f"```\n{WRITTEN[path]}```")


def _drafted(tmp_path, monkeypatch, switch: str, diagnose=None) -> _Model:
    monkeypatch.setenv("DRAFTING_IN_WAVES", switch)
    model = _Model()

    def write(root, path, content):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)

    specification = _specification(
        f"{ENTRY}: starts the server and builds the router with the shared state; imports from {HANDLERS} and {SHAPES}",
        f"{HANDLERS}: the request handlers; imports from {SHAPES}",
        f"{SHAPES}: the shared state and the record shapes",
    )
    # The lead listed the entry file first: drafted in that order, it was written before anything it wires.
    orders = [_order(ENTRY), _order(HANDLERS, SHAPES)]
    drafting.draft_work_orders(orders, specification, None, str(tmp_path), model, write=write, workers=1,
                               diagnose=diagnose)
    return model


def test_the_entry_file_is_drafted_last_and_shown_the_handlers_it_wires(tmp_path, monkeypatch):
    model = _drafted(tmp_path, monkeypatch, "on")

    order = [path for path, _ in model.requests]
    entry_request = dict(model.requests)[ENTRY]
    assert order == [SHAPES, HANDLERS, ENTRY]
    assert "State(state): State<AppState>" in entry_request
    assert "pub struct AppState" in dict(model.requests)[HANDLERS]


def test_a_later_file_s_request_says_the_earlier_files_are_written_and_is_seen_as_the_switch_acting(tmp_path, monkeypatch):
    model = _drafted(tmp_path, monkeypatch, "on")

    entry_request = dict(model.requests)[ENTRY]
    assert "do not declare again" in entry_request
    assert fired([{"kind": "model_request", "messages": entry_request}]) == ["DRAFTING_IN_WAVES"]


def test_with_the_switch_off_the_files_are_drafted_in_one_wave_as_listed(tmp_path, monkeypatch):
    model = _drafted(tmp_path, monkeypatch, "off")

    assert [path for path, _ in model.requests] == [ENTRY, HANDLERS, SHAPES]


def test_an_earlier_wave_the_compiler_reports_an_error_in_is_repaired_before_the_next_is_drafted(tmp_path, monkeypatch):
    reports = {SHAPES: [f"- In `{SHAPES}` line 1: expected `;`"]}

    def diagnose(files):
        return [line for f in files for line in reports.pop(f, [])]

    model = _drafted(tmp_path, monkeypatch, "on", diagnose=diagnose)

    assert [path for path, _ in model.requests] == [SHAPES, SHAPES, HANDLERS, ENTRY]
    repair = model.requests[1][1]
    assert "expected `;`" in repair
    assert HANDLERS in repair and ENTRY in repair


def test_a_long_earlier_file_is_shown_by_all_its_definitions_not_cut_at_its_head(tmp_path):
    (tmp_path / "src").mkdir()
    filler = "".join(f"pub fn helper_{n}() -> u32 {{\n" + "    let _ = 1;\n" * 20 + f"    {n}\n}}\n" for n in range(40))
    (tmp_path / SHAPES).write_text(filler + "pub struct AppState { pub notes: Vec<String> }\n")

    request = drafting.draft_request(tmp_path, ENTRY, _order(ENTRY), _specification(), None, written_before=[SHAPES])

    assert "pub struct AppState" in request


def test_a_product_of_two_code_files_is_one_wave():
    assert drafting_waves(["src/models.py", "src/main.py"], [], _specification(
        "src/main.py: entry; imports from src/models.py")).waves == [["src/models.py", "src/main.py"]]


def test_a_file_the_plan_says_another_uses_is_drafted_before_it():
    plan = _specification("lib/core.ts: the engine; used by lib/cli.ts", "lib/cli.ts: the command line",
                          "lib/format.ts: output formatting; imports from lib/core.ts")

    waves = drafting_waves(["lib/cli.ts", "lib/format.ts", "lib/core.ts"], [], plan)

    assert waves.waves == [["lib/core.ts"], ["lib/cli.ts", "lib/format.ts"]]
    assert waves.needs == {"lib/cli.ts": ["lib/core.ts"], "lib/format.ts": ["lib/core.ts"]}


def test_with_no_plan_the_data_shapes_come_first_and_the_entry_file_last():
    paths = ["App/Program.cs", "App/Services/NoteService.cs", "App/Interfaces/INoteRegistry.cs", "App/Data/NoteStore.cs"]

    waves = drafting_waves(paths, [], _specification(), entrypoints=["Program.cs"])

    assert waves.waves == [
        ["App/Interfaces/INoteRegistry.cs", "App/Data/NoteStore.cs"], ["App/Services/NoteService.cs"], ["App/Program.cs"],
    ]
    assert waves.needs["App/Program.cs"][0] == "App/Services/NoteService.cs"


def test_a_contract_a_work_order_calls_in_another_order_s_file_orders_its_files_after_it():
    orders = [_order("pkg/api.go", "pkg/view.go", interfaces=("calls Lookup(id) in pkg/catalogue.go",)),
              _order("pkg/catalogue.go")]

    waves = drafting_waves(["pkg/api.go", "pkg/view.go", "pkg/catalogue.go"], orders, _specification())

    assert waves.waves == [["pkg/catalogue.go"], ["pkg/api.go", "pkg/view.go"]]


def test_a_chain_deeper_than_three_is_drafted_in_three_waves_with_the_top_last():
    plan = _specification("a.py: imports from b.py", "b.py: imports from c.py", "c.py: imports from d.py", "d.py: base")

    waves = drafting_waves(["a.py", "b.py", "c.py", "d.py"], [], plan)

    assert waves.waves == [["d.py"], ["b.py", "c.py"], ["a.py"]]


def test_files_that_name_one_another_are_still_each_drafted_once():
    plan = _specification("x.js: imports from y.js", "y.js: imports from z.js", "z.js: imports from x.js")

    waves = drafting_waves(["x.js", "y.js", "z.js"], [], plan)

    assert sorted(path for wave in waves.waves for path in wave) == ["x.js", "y.js", "z.js"]


@pytest.mark.parametrize("text", [drafting.WRITTEN_BEFORE, drafting.STILL_TO_COME])
def test_what_a_drafted_file_is_told_of_the_other_waves_uses_no_product_word(text):
    assert not BANNED.search(text)
