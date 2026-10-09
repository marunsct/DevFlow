"""When stack-pack.json is missing, the contract is inferred from workspace artifacts.

If a scaffold failed its smoke test or was left to the agents, .harness/stack-pack.json
was not written. Every later stage (kept files, QA locators, assertion linters,
failure pages) relies on the pack. Inferring the pack from decisions or the technology
stack document ensures the harness still protects kept files and lints acceptance tests.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.acceptance import suite
from app.stacks import contract, pack_named


def test_inferred_from_decisions_when_stack_pack_json_missing(tmp_path: Path) -> None:
    harness_dir = tmp_path / ".harness"
    harness_dir.mkdir(parents=True)
    decisions = [
        {
            "id": "DR-1",
            "point": "stack",
            "decision": "JavaScript / None - Browser app in plain JavaScript modules",
            "options": ["Browser app in plain JavaScript modules"],
            "rationale": "Support tier: pack-supported - the browser-javascript pack's scaffold",
        }
    ]
    (harness_dir / "decisions.json").write_text(json.dumps(decisions), encoding="utf-8")
    (tmp_path / ".project-directory").write_text("my-app\n", encoding="utf-8")

    assert contract.read(tmp_path) is None

    found = contract.the_pack(tmp_path)
    assert found is not None
    pack, record = found
    assert pack.name == "browser-javascript"
    assert record.get("pack") == "browser-javascript"
    assert record.get("project") == "my-app"

    # Confirms it self-healed by persisting CONTRACT_FILE
    assert contract.read(tmp_path) is not None
    assert (tmp_path / ".harness" / "stack-pack.json").is_file()

    # Confirms kept_paths works
    kept = contract.kept_paths(tmp_path)
    assert "my-app/playwright.config.js" in kept


def test_inferred_from_technology_stack_document(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True)
    content = """# Technology Stack
## Selected Technology Stack
- **Language:** JavaScript
- **Framework:** None (plain HTML, CSS and JavaScript modules)
- **Kind of product:** browser app
## Rationale
The "Browser app in plain JavaScript modules" stack meets all constraints.
"""
    (docs_dir / "technology_stack.md").write_text(content, encoding="utf-8")
    project_dir = tmp_path / "web-app"
    project_dir.mkdir()
    (project_dir / "package.json").write_text('{"name": "web-app"}', encoding="utf-8")

    found = contract.the_pack(tmp_path)
    assert found is not None
    pack, record = found
    assert pack.name == "browser-javascript"
    assert record.get("project") == "web-app"


def test_custom_stack_without_pack_returns_none(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True)
    content = """# Technology Stack
- **Language:** Haskell
- **Framework:** Yesod
"""
    (docs_dir / "technology_stack.md").write_text(content, encoding="utf-8")

    assert contract.the_pack(tmp_path) is None


def test_the_pack_above_with_inferred_pack(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True)
    content = "Browser app in plain JavaScript modules"
    (docs_dir / "technology_stack.md").write_text(content, encoding="utf-8")
    nested_file = tmp_path / "src" / "deep" / "index.js"
    nested_file.parent.mkdir(parents=True)
    nested_file.write_text("console.log(1);", encoding="utf-8")

    found = contract.the_pack_above(nested_file)
    assert found is not None
    assert found[0].name == "browser-javascript"

