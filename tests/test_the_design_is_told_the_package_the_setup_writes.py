"""The design stages are told the Python package the setup will write: the one the brief names, else the directory's.

Measured on one run: the brief said `import textkit`; the stages were told the setup writes
`text_toolkit_library/__init__.py` (named from the directory) while the setup wrote `textkit/`. The design review called
the plan contradictory, the design was escalated, and two rulings sided with the path that was never made.
"""
from pathlib import Path
from types import SimpleNamespace

from app.graph import workflow
from app.stacks import the_python_package

BRIEF = "# Text toolkit\nA small library, used as `import textkit`.\n"


def test_the_brief_s_module_wins_over_the_directory():
    assert the_python_package("text-toolkit-library", BRIEF) == "textkit"
    assert the_python_package("text-toolkit-library", "# no module named") == "text_toolkit_library"


def test_the_facts_name_the_brief_s_package(tmp_path, monkeypatch):
    (tmp_path / ".project-directory").write_text("text-toolkit-library\n")
    monkeypatch.setattr("app.tools.repository.pinned_project_directory", lambda root: "text-toolkit-library")
    stack = SimpleNamespace(language="Python", framework="", product_kind="library")
    state = {
        "stack_selection": SimpleNamespace(technology_stack=stack),
        "document": SimpleNamespace(text=BRIEF),
        "repository": SimpleNamespace(root_path=str(tmp_path)),
    }
    facts = "\n".join(workflow._the_scaffold_s_facts(state))
    assert "textkit/" in facts and "text_toolkit_library" not in facts
