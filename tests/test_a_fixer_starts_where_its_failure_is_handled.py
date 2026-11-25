"""A fixer is told where its failure is handled, and its memory holds those files whole (plan FX.2, LF.1416).

Measured on a medium run: fixers of an acceptance criterion briefed "Affected files: (none identified)" read 26-34
times and changed nothing. Their memory held the locked suite's test file and helper that the failing tests' output
named, not the route and service files the failing request `POST /api/register` passes through; those five files
were read 91 times in three fixers, 63 of them again.
"""
from __future__ import annotations

import json
import re

import pytest
from langchain_core.messages import AIMessage

import the_fix_stage

from app.acceptance import suite
from app.agents import project_memory

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

#: What a locked suite's failing tests printed for a sign-up that answered 500: the request, the test's own frame.
PRINTED = ("Error: expect(received).toBe(expected)\n\n    Expected: 201\n    Received: 500\n\n"
           "      56 |   const second = await request.post('/api/register', {\n"
           "        at /workspace/shop/acceptance/auth.spec.js:27:29\n")


def _product(root, route_line: str = '@router.post("/register", status_code=201)') -> None:
    """A service whose sign-up route lives in `routes/auth.py` and uses `services/accounts.py`, mounted under `/api`
    by `main.py`; a locked suite beside it; and enough other code that the memory cannot hold everything."""
    (root / "shop" / "app" / "routes").mkdir(parents=True)
    (root / "shop" / "app" / "services").mkdir(parents=True)
    (root / "shop" / "acceptance").mkdir(parents=True)
    (root / "shop" / "app" / "__init__.py").write_text("")
    (root / "shop" / "app" / "routes" / "__init__.py").write_text("")
    (root / "shop" / "app" / "services" / "__init__.py").write_text("")
    (root / "shop" / "app" / "main.py").write_text(
        "from fastapi import FastAPI\nfrom app.routes.auth import router\n\napp = FastAPI()\n"
        'app.include_router(router, prefix="/api")\n')
    (root / "shop" / "app" / "routes" / "auth.py").write_text(
        "from fastapi import APIRouter\nfrom app.services.accounts import sign_up\n\nrouter = APIRouter()\n\n\n"
        f"{route_line}\ndef register(body: dict):\n    return sign_up(body)\n")
    (root / "shop" / "app" / "services" / "accounts.py").write_text(
        "def sign_up(body):\n    # stores the account\n    return {'id': 1, **body}\n" + "# the account rules\n" * 300)
    for n in range(12):
        (root / "shop" / "app" / f"widgets_{n}.py").write_text(f"def widget_{n}():\n    return {n}\n"
                                                                + "# what it does\n" * 400)
    (root / "shop" / "acceptance" / "auth.spec.js").write_text(
        "const { test, expect } = require('@playwright/test');\n" + "// sign-up steps\n" * 600)
    (root / "shop" / "playwright.config.js").write_text("module.exports = { testDir: './acceptance' };\n")
    from app.tools.repository import PROJECT_MARKER

    (root / PROJECT_MARKER).write_text("shop\n")


def _measured(root) -> None:
    """The suite's last run: AC-1's two tests answered 500 on `POST /api/register`."""
    path = root / suite.RESULT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"ran": True, "criteria": {"AC-1": {"id": "AC-1", "text": "Sign up", "status": "failed",
        "tests": [{"name": "[AC-1] signs up", "outcome": "failed", "message": PRINTED},
                  {"name": "[AC-1] refuses a second sign-up", "outcome": "failed", "message": PRINTED}]}}}))


def _fix_request(root, monkeypatch) -> str:
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", "60000")
    monkeypatch.setattr(suite, "relative_directory", lambda repo_root: "shop/acceptance")
    defect = the_fix_stage.a_defect("[AC-1] Sign up - the acceptance suite says this does not work yet.",
                                    affected_files=[], expected_behavior="Sign up", actual_behavior="500")
    _, seen = the_fix_stage.run(root, the_fix_stage.a_state(root, defect), real_brief=True)
    return seen.requests[0]


def test_a_fixer_of_a_failing_request_is_told_the_route_that_handles_it_and_what_it_imports(tmp_path, monkeypatch):
    _product(tmp_path)
    _measured(tmp_path)

    request = _fix_request(tmp_path, monkeypatch)

    shown = request[request.index("--- Where the failure is handled"):]
    shown = shown[:shown.index("\n---", 4)]
    assert "`shop/app/routes/auth.py`" in shown and "`shop/app/services/accounts.py`" in shown
    assert "widgets_" not in shown and "auth.spec.js" not in shown
    assert not BANNED.search(shown)


def test_the_memory_holds_the_handler_whole_and_not_the_locked_test_its_output_names(tmp_path, monkeypatch):
    _product(tmp_path)
    _measured(tmp_path)
    request = _fix_request(tmp_path, monkeypatch)

    memory = project_memory.render_for_a_stage(tmp_path, None, request, "defect_fix_2_0")[0]

    assert "=== shop/app/routes/auth.py ===" in memory
    assert "=== shop/app/services/accounts.py ===" in memory
    assert "=== shop/acceptance/auth.spec.js ===" not in memory


@pytest.mark.parametrize("route_line", [
    "router.post('/register', async (req, res) => res.status(201).json(signUp(req.body)));",
    '@app.route("/api/register", methods=["POST"])',
    '    r.HandleFunc("/api/register", Register).Methods("POST")',
    '    @PostMapping("/register")',
    "  post '/register' do",
])
def test_the_route_is_found_in_any_language_s_spelling(tmp_path, route_line):
    from app.graph import localised_fix

    _product(tmp_path, route_line=route_line)

    found = localised_fix.where(tmp_path, "INFO: 127.0.0.1 - \"POST /api/register HTTP/1.1\" 500")

    assert found.found == ["shop/app/routes/auth.py"]


def test_a_route_of_another_method_or_path_is_not_the_handler(tmp_path):
    from app.graph import localised_fix

    _product(tmp_path, route_line='@router.get("/register")')

    assert localised_fix.where(tmp_path, "POST /api/register 500").found == []
    assert localised_fix.where(tmp_path, "GET /api/accounts/3 404").found == []


def test_the_product_s_frames_in_a_trace_place_the_failure(tmp_path):
    from app.graph import localised_fix

    _product(tmp_path, route_line="")
    trace = ('Traceback (most recent call last):\n  File "/workspace/shop/app/services/accounts.py", line 3, in sign_up\n'
             '  File "/usr/lib/python3/site-packages/starlette/routing.py", line 70\nKeyError: \'email\'')

    found = localised_fix.where(tmp_path, trace)

    assert found.found == ["shop/app/services/accounts.py"]


class _Answers:
    """A model that answers each call with `reply` and counts the calls."""

    def __init__(self, reply: str) -> None:
        self.reply, self.calls = reply, 0

    def invoke(self, messages, **kwargs):
        self.calls += 1
        return AIMessage(content=self.reply)


def test_a_failure_nothing_places_is_localised_by_one_call(tmp_path, monkeypatch):
    from app.graph import localised_fix

    monkeypatch.setattr("app.agents.thinking.without_reasoning", lambda model: model)
    _product(tmp_path, route_line="")
    model = _Answers(json.dumps({"files": ["shop/app/services/accounts.py"], "symbols": ["sign_up"],
                                 "hypothesis": "the account is stored without its email"}))

    found = localised_fix.where(tmp_path, "The sign-up page shows no message.", model=model, ask=True)

    assert found.found == ["shop/app/services/accounts.py"] and model.calls == 1


def test_a_defect_that_names_its_files_asks_no_localisation(tmp_path, monkeypatch):
    from app.graph import localised_fix

    monkeypatch.setattr("app.agents.thinking.without_reasoning", lambda model: model)
    _product(tmp_path, route_line="")
    model = _Answers("{}")

    found = localised_fix.where(tmp_path, "The sign-up page shows no message.", named=["shop/app/main.py"],
                                model=model, ask=True)

    assert found.found == [] and model.calls == 0
