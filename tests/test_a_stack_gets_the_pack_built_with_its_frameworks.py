"""A stack gets the pack built with the frameworks it chose - both of them, for a full-stack product.

Measured on the three brief_medium runs: the stack was Python on FastAPI with
a React page on Vite. No pack had a React page and a FastAPI service, so the
runs had no scaffold; and the language a stack was matched on was one word,
read TypeScript before Python, so a pack for both could not have matched it.
A stack whose page was Vue on Vite fitted the React pack, which names Vite.
"""

from __future__ import annotations

import importlib.util
import sys
from types import SimpleNamespace

import pytest

from app.stacks import choose_pack, pack_named, supported_stacks_note
from app.stacks.packs import ALL_PACKS


def _stack(language, framework, frontend="", kind=""):
    return SimpleNamespace(
        language=language, framework=framework, frontend_framework=frontend,
        database="PostgreSQL", testing_framework="", product_kind=kind,
    )


@pytest.mark.parametrize("stack, chosen", [
    (_stack("Python", "FastAPI", "React on Vite", "fullstack"), "fullstack-react-fastapi"),
    (_stack("Python", "FastAPI", "Vue 3", "fullstack"), "fullstack-vue-fastapi"),
    (_stack("JavaScript", "Express", "React", "fullstack"), "fullstack-react-express"),
    (_stack("TypeScript", "Node.js / Express", "Vue.js", "fullstack"), "fullstack-vue-express"),
    (_stack("JavaScript", "Express", "None (plain HTML, CSS and JavaScript modules)", "fullstack"), "fullstack-node"),
    (_stack("TypeScript", "Vue", "Vue.js on Vite", "browser_app"), "browser-vue"),
    (_stack("JavaScript", "React.js", "", "browser_app"), "browser-react"),
    (_stack("JavaScript", "None (plain HTML, CSS and JavaScript modules)", "None", "browser_app"), "browser-javascript"),
    (_stack("Python", "FastAPI", "", "http_api"), "python-http-api"),
])
def test_the_pack_built_with_what_the_stack_chose(stack, chosen):
    assert choose_pack(stack, "").name == chosen


@pytest.mark.parametrize("stack", [
    _stack("Python", "FastAPI", "Svelte", "fullstack"),
    _stack("Python", "Django", "React", "fullstack"),
    _stack("TypeScript", "None", "", "browser_app"),
])
def test_no_pack_built_with_something_else(stack):
    assert choose_pack(stack, "") is None


def test_the_stack_selector_is_offered_every_pack():
    note = supported_stacks_note()

    for pack in ALL_PACKS:
        assert pack.title in note


def _the_service(tmp_path, page: bool):
    """The FastAPI pack's service as scaffolded, with a built page or without one."""
    files = pack_named("fullstack-react-fastapi").render("shop", "Shop", "shop_svc")
    (tmp_path / "shop_svc").mkdir()
    (tmp_path / "shop_svc" / "main.py").write_text(files["shop_svc/main.py"])
    if page:
        (tmp_path / "dist" / "assets").mkdir(parents=True)
        (tmp_path / "dist" / "index.html").write_text("<!doctype html><title>Shop</title>")
        (tmp_path / "dist" / "assets" / "app.js").write_text("console.log('page')")
    spec = importlib.util.spec_from_file_location("shop_svc_main", tmp_path / "shop_svc" / "main.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["shop_svc_main"] = module
    spec.loader.exec_module(module)
    from fastapi.testclient import TestClient

    return module.app, TestClient(module.app)


class TestTheFastapiService:
    def test_serves_the_page_at_any_address_that_is_not_the_api(self, tmp_path):
        _, client = _the_service(tmp_path, page=True)

        assert "<title>Shop</title>" in client.get("/").text
        assert "<title>Shop</title>" in client.get("/projects/7").text
        assert client.get("/assets/app.js").text == "console.log('page')"

    def test_routes_added_after_it_still_answer(self, tmp_path):
        app, client = _the_service(tmp_path, page=True)

        @app.get("/api/items")
        def items():
            return [{"id": 1}]

        assert client.get("/api/items").json() == [{"id": 1}]

    def test_an_unknown_api_address_is_a_json_404(self, tmp_path):
        _, client = _the_service(tmp_path, page=True)

        response = client.get("/api/nothing-here")
        assert response.status_code == 404
        assert response.json() == {"detail": "Not Found"}

    def test_with_no_page_built_it_is_the_api_alone(self, tmp_path):
        _, client = _the_service(tmp_path, page=False)

        assert client.get("/api/health").json() == {"status": "ok"}
        assert client.get("/").status_code == 404
