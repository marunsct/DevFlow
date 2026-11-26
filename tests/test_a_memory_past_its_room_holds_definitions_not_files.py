"""Past its memory's room, a fixer's or a builder's files are held as the definitions its work reaches (plan KG.5).

Measured: a fixer's five-file path of 12,800 tokens was handed over as whole files when it needed four functions, and a
file past the memory's room was only named, and read. With `DEFINITIONS_BEFORE_FILES` on, the route's handler, what it
calls (one hop of the code graph) and an outline of the rest are held instead; where the files fit, as before.

The project is a real product's files (`tests/captured/projects/typescript-notes-api`); the lines were read from them.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from app.agents import project_memory

PROJECTS = Path(__file__).parent / "captured" / "projects"
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
ROUTES = "typescript-notes-api/src/routes.ts"
STORE = "typescript-notes-api/src/store.ts"
VALIDATION = "typescript-notes-api/src/validation.ts"
#: FX.2's section, as `localised_fix.section` writes it for this product's failing `POST /notes`.
FIX_REQUEST = f"""Make AC-2 pass: creating a note answers 201.

--- Where the failure is handled (found by the harness) ---
Found from the route reached by `POST /notes`:
- `{ROUTES}`
and what those import:
- `{STORE}`
- `{VALIDATION}`
Where each route is answered:
- `POST /notes` is answered by `createNoteHandler` in `{ROUTES}`, lines 31-57
Start from these files: the cause is in them or in what they call.
"""


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.delenv("SWITCH_OVERRIDES_FROM_SETTINGS", raising=False)
    shutil.copytree(PROJECTS / "typescript-notes-api", tmp_path / "typescript-notes-api")
    (tmp_path / ".project-directory").write_text("typescript-notes-api")
    return tmp_path


def _fixer_memory(workspace: Path, budget: int) -> str:
    memory, _held = project_memory.render(workspace, budget, focus=FIX_REQUEST, for_a_fixer=True, sliced=True,
                                          localised=(ROUTES, STORE, VALIDATION))
    return memory


def test_a_fixer_past_its_room_holds_the_handler_and_what_it_calls_and_outlines_the_rest(workspace, monkeypatch):
    monkeypatch.setenv("DEFINITIONS_BEFORE_FILES", "on")
    memory = _fixer_memory(workspace, 9_000)
    # The handler the route is answered by, whole and numbered as in the file.
    assert "31: async function createNoteHandler(c: Context): Promise<Response> {" in memory
    assert "51:     const note = store.createNote(currentStore, result.data!.title, result.data!.body);" in memory
    # One hop: the two definitions it calls, in the files they are in.
    assert "86: export function createNote(store: Store, title: string, body: string): Note {" in memory
    assert "38: export function validateNoteBody(body: unknown): ValidationResult {" in memory
    # The rest by line, not by body.
    assert "59-71  async function listNotesHandler(c: Context): Promise<Response>" in memory
    assert "const notes = store.getAllNotes(currentStore);" not in memory
    assert "store.notes.splice" not in memory


def test_a_builder_past_its_room_holds_the_definition_its_work_order_names(workspace, monkeypatch):
    monkeypatch.setenv("DEFINITIONS_BEFORE_FILES", "on")
    order = f"Change `{STORE}` so that `createNote` trims the title before it saves the note."
    memory, _held = project_memory.render(workspace, 3_000, focus=order, sliced=True)
    assert "87:   const nextId = Math.max(...store.notes.map(n => n.id), 0) + 1;" in memory
    # `createNote` saves through `saveStore`, held too; what it does not reach is outlined.
    assert "57: export function saveStore(store: Store): void {" in memory
    assert "118-128  export function deleteNote(store: Store, id: number): void" in memory
    assert "store.notes.splice" not in memory


def test_files_that_fit_are_held_whole_as_before(workspace, monkeypatch):
    monkeypatch.setenv("DEFINITIONS_BEFORE_FILES", "on")
    memory = _fixer_memory(workspace, 200_000)
    assert "const notes = store.getAllNotes(currentStore);" in memory
    assert "held as the definitions this work reaches" not in memory


def test_with_the_switch_off_the_files_are_held_whole(workspace, monkeypatch):
    monkeypatch.setenv("DEFINITIONS_BEFORE_FILES", "off")
    memory = _fixer_memory(workspace, 9_000)
    assert "held as the definitions this work reaches" not in memory


def test_what_the_memory_says_of_them_uses_no_product_word(workspace, monkeypatch):
    monkeypatch.setenv("DEFINITIONS_BEFORE_FILES", "on")
    memory = _fixer_memory(workspace, 9_000)
    said = [line for line in memory.splitlines() if line.startswith(("=== ", "The rest of", "What those call"))]
    assert said and not BANNED.search("\n".join(said))
