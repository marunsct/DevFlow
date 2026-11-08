"""A page that does not load the pack's entry script, beside a real copy of the program there, is named (2026-11-08).

Measured on a run (hidden 10/10): the page ran its whole program in an inline script, while the 410-line `src/main.js`
the pack's page loads was loaded by nothing. Fixes were made in it, and all twelve changes the mutation check made to
it went unnoticed (mutation score 0).
"""
from __future__ import annotations

import pytest

from app.stacks import contract, pack_named
from app.stacks.scaffold import code_the_product_does_not_run


@pytest.fixture
def workspace(tmp_path):
    pack = pack_named("browser-javascript")
    contract.write(tmp_path, pack, "app", "App")
    for relative, content in pack.render("app", "App").items():
        (tmp_path / "app" / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "app" / relative).write_text(content)
    return tmp_path


def _a_program(lines: int) -> str:
    return "".join(f"export const value{n} = {n};\n" for n in range(lines))


def test_an_inline_page_beside_an_unloaded_program_is_named(workspace) -> None:
    page = workspace / "app" / "index.html"
    page.write_text(page.read_text().replace('<script type="module" src="src/main.js"></script>',
                                             '<script type="module">const tasks = [];</script>'))
    (workspace / "app" / "src" / "main.js").write_text(_a_program(60))
    found = [p for p in code_the_product_does_not_run(workspace) if "does not load" in p]
    assert found and "`app/index.html` does not load `app/src/main.js` (60 lines)" in found[0]


def test_a_page_that_loads_its_entry_or_a_bare_stub_is_not_named(workspace) -> None:
    (workspace / "app" / "src" / "main.js").write_text(_a_program(60))
    assert not [p for p in code_the_product_does_not_run(workspace) if "does not load" in p]
    page = workspace / "app" / "index.html"
    page.write_text(page.read_text().replace('<script type="module" src="src/main.js"></script>', "<script></script>"))
    (workspace / "app" / "src" / "main.js").write_text("// stub\n")
    assert not [p for p in code_the_product_does_not_run(workspace) if "does not load" in p]
