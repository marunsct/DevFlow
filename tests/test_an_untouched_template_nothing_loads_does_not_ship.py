"""The pack's untouched template that nothing loads does not ship beside the product (harness review HR2.PR.4).

16 products shipped the browser pack's unchanged `src/main.js` stub beside the `app.js` the page loads.
"""
from __future__ import annotations

import inspect

import pytest

from app.graph import delivery
from app.stacks import contract, pack_named
from app.stacks.scaffold import remove_untouched_templates_nothing_loads


@pytest.fixture
def workspace(tmp_path):
    pack = pack_named("browser-javascript")
    contract.write(tmp_path, pack, "app", "App")
    for relative, content in pack.render("app", "App").items():
        (tmp_path / "app" / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "app" / relative).write_text(content)
    return tmp_path


def test_the_untouched_main_beside_an_app_the_page_loads_is_removed(workspace) -> None:
    page = workspace / "app" / "index.html"
    page.write_text(page.read_text().replace("src/main.js", "app.js"))
    (workspace / "app" / "app.js").write_text("export function start() {}\n")

    assert remove_untouched_templates_nothing_loads(workspace) == ["app/src/main.js"]
    assert not (workspace / "app" / "src" / "main.js").exists()
    assert (workspace / "app" / "app.js").exists() and (workspace / "app" / "scripts" / "serve.mjs").exists()


def test_a_template_the_page_still_loads_stays(workspace) -> None:
    assert remove_untouched_templates_nothing_loads(workspace) == []
    assert (workspace / "app" / "src" / "main.js").exists()


def test_a_changed_template_is_the_product_s_and_stays(workspace) -> None:
    page = workspace / "app" / "index.html"
    page.write_text(page.read_text().replace("src/main.js", "app.js"))
    main = workspace / "app" / "src" / "main.js"
    main.write_text(main.read_text() + "\nexport const changed = true;\n")
    assert remove_untouched_templates_nothing_loads(workspace) == []
    assert main.exists()


def test_the_release_does_it_on_the_way_out() -> None:
    source = inspect.getsource(delivery.release)
    assert source.index("remove_untouched_templates_nothing_loads(root)") < source.index("deferred = suite.deferred(root)")
