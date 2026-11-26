"""The map of a seeded codebase names its entry point and the modules a change touches, in every language (KG.9).

The map found entry points only where the code graph followed imports by pattern (Python, JavaScript/TypeScript): a
seeded Go or Java codebase got no entry point at all, and past 80 files its directories ranked their modules by
importers, which those languages showed none of. Now a file defining `main` is an entry point in any language, a file
whose names another file uses is not one, and modules are ranked by how much of the project reaches them, the names
the request uses weighing more; the modules defining those names are listed with what uses them and their tests.

The Go and Java projects and their suites are real products' files (`tests/captured/projects/README.md`).
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from app.acceptance.regression_contract import mark_seeded
from app.agents import code_map

CAPTURED = Path(__file__).parent / "captured"
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _seeded(tmp_path: Path, name: str) -> Path:
    shutil.copytree(CAPTURED / "projects" / name, tmp_path / name)
    shutil.copytree(CAPTURED / "project-tests" / name, tmp_path / name, dirs_exist_ok=True)
    (tmp_path / ".project-directory").write_text(name)
    mark_seeded(tmp_path, {"type": "git"})
    return tmp_path


def _mapped(root: Path, brief: str) -> str:
    """The request a planning stage sends with the map, as `with_the_map` writes it for a request carrying `brief`."""
    request = {"messages": [{"role": "user", "content": brief}]}
    return code_map.with_the_map(request, root)["messages"][-1]["content"]


def _line(text: str, starting: str) -> str:
    return next(line for line in text.splitlines() if line.startswith(starting))


def _listed_under(text: str, heading: str) -> list[str]:
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(heading)) + 1
    found = []
    for line in lines[start:]:
        if not line.startswith("- "):
            break
        found.append(line)
    return found


def test_a_go_codebase_s_entry_point_is_its_main_and_not_the_router_main_calls(tmp_path):
    text = _mapped(_seeded(tmp_path, "go-notes-api"), "Let each note carry tags, and let the store list notes by tag.")

    assert _line(text, "Entry points").endswith(": go-notes-api/main.go.")
    [store] = _listed_under(text, "Where the names this request uses are defined")
    assert store.startswith("- go-notes-api/store/store.go: Note, Store")
    assert "used by go-notes-api/server.go" in store


def test_a_java_codebase_s_entry_point_is_its_application_and_the_service_comes_with_its_test(tmp_path):
    text = _mapped(_seeded(tmp_path, "java-notes-api"), "Add a search to the note service: notes whose title holds a word.")

    entry = _line(text, "Entry points").split(": ", 1)[1]
    assert entry.startswith("java-notes-api/src/main/java/app/notes_api/Application.java,")
    assert "service/NoteService.java" not in entry and "repository/NoteRepository.java" not in entry
    named = _listed_under(text, "Where the names this request uses are defined")
    service = next(line for line in named if "service/NoteService.java: NoteService" in line)
    assert "used by java-notes-api/src/main/java/app/notes_api/controller/NoteController.java" in service
    assert "tests java-notes-api/src/test/java/app/notes_api/NoteServiceTest.java" in service
    assert not BANNED.findall(text)


def _a_large_codebase(root: Path) -> Path:
    """95 handlers that all use one shared module; ten of them use the monthly report, two the invoice total."""
    files = {"app/shared.py": "def load_settings():\n    return {}\n",
             "app/reports.py": "def monthly_report():\n    return []\n",
             "app/billing.py": "def invoice_total(lines):\n    return sum(lines)\n"}
    for number in range(95):
        uses = "from app.reports import monthly_report\n" if number < 10 else ""
        uses += "from app.billing import invoice_total\n" if number < 2 else ""
        files[f"app/handlers/handler{number:02d}.py"] = (f"from app.shared import load_settings\n{uses}\n\n"
                                                         f"def handle_{number}():\n    return load_settings()\n")
    for relative, body in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    mark_seeded(root, {"type": "archive"})
    return root


def test_past_80_files_the_main_modules_come_first_and_the_request_s_names_move_theirs_up(tmp_path):
    root = _a_large_codebase(tmp_path)

    plain = _listed_under(_mapped(root, "Read me."), "Main modules")
    asked = _mapped(root, "Change how the invoice total is rounded.")

    assert plain[:3] == ["- app/shared.py: load_settings", "- app/reports.py: monthly_report",
                         "- app/billing.py: invoice_total"]
    assert _listed_under(asked, "Main modules")[:2] == ["- app/shared.py: load_settings",
                                                        "- app/billing.py: invoice_total"]
    assert _listed_under(asked, "Where the names this request uses are defined") == [
        "- app/billing.py: invoice_total (used by app/handlers/handler00.py, app/handlers/handler01.py)"]
    assert not BANNED.findall(asked)
