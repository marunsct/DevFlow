"""A package manager's own cache is not the product the brief constrains.

One run's milestone reviewer was told, as a finding "checked
deterministically against what was built": "aab42732f01924e5/package.json
declares `serve`. The brief rules that out". That manifest was npx's cache,
written under the sandbox's HOME at `.agent-home/.npm/_npx/aab42732f01924e5/`.
The reviewer then listed `/aab42732f01924e5`, which does not exist.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.agents.brief_constraints import what_the_brief_forbids_that_is_there

BRIEF = """# Brief
## Technical Constraints
- No external dependencies beyond basic HTML/CSS/JS
"""


def _workspace(tmp_path: Path) -> Path:
    app = tmp_path / "simple-to-do-list-app"
    app.mkdir()
    (app / "package.json").write_text(json.dumps({"name": "app"}), encoding="utf-8")
    cache = tmp_path / ".agent-home" / ".npm" / "_npx" / "aab42732f01924e5"
    cache.mkdir(parents=True)
    (cache / "package.json").write_text(
        json.dumps({"dependencies": {"serve": "^14"}}), encoding="utf-8"
    )
    return tmp_path


def test_npx_s_cache_is_not_reported(tmp_path: Path) -> None:
    findings = what_the_brief_forbids_that_is_there(BRIEF, str(_workspace(tmp_path)))

    assert not [f for f in findings if "serve" in f or "aab42732" in f]


def test_the_product_s_own_dependency_still_is(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    (root / "simple-to-do-list-app" / "package.json").write_text(
        json.dumps({"dependencies": {"lodash": "^4"}}), encoding="utf-8"
    )

    findings = what_the_brief_forbids_that_is_there(BRIEF, str(root))

    assert any("lodash" in f for f in findings)
