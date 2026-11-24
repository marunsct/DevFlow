"""A fixer's request holds its defect's fresh evidence first, and standing context sized to what the defect touches.

Measured on a medium run (27 fix stages): the opening request averaged about 104,000 characters of role prompt and
project memory, 14,800 of facts, 11,000 of the whole API and 8,700 of setup - and about 5,000 of the defect's own
evidence. Six fixers were shown a server log from a measurement up to ten hours old and a revert story about a start
fault already fixed; the round's own shared-cause defect was in no related fixer's request. On a small run the request
was about 52,000 characters and fitted (LF.1270).
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace

import the_fix_stage

from app import ci
from app.acceptance import suite
from app.agents import project_memory
from app.sprint import Defect

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

STALE = ("[AC-3] lists items: assert 500 == 201\n"
         "What the product's server logged while the suite ran:\n"
         "OLD LOG: ImportError: cannot import name 'engine' (app/db.py:3)\n"
         "A fix was tried and reverted, because it broke what passed before it: the product no longer builds or "
         "starts after it (ImportError: cannot import name 'engine'); acceptance: [AC-1] signs up.")
FRESH_MESSAGE = ("AssertionError: assert 404 == 201\n  -> POST http://127.0.0.1:8000/api/items\n"
                 "  at app/routes/items.py:41")


def _measured(root) -> None:
    """The latest measurement: AC-3's test answered 404 at /api/items, the server logged a fresh error, it started."""
    path = root / suite.RESULT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "ran": True, "criteria": {"AC-3": {"id": "AC-3", "text": "List items", "status": "failed", "tests": [
            {"name": "[AC-3] lists items", "outcome": "failed", "message": FRESH_MESSAGE}]}},
        "server_log": "NEW LOG: KeyError: 'owner_id' (app/routes/items.py:41)",
    }))
    ci.save(root, ci.Snapshot(label="latest", acceptance={"[AC-1] signs up": "passed"}, acceptance_ran=True))


def _project(root, others: int, size: int) -> None:
    """A product whose items route is the defect's file, beside `others` route files of `size` characters each."""
    (root / "app" / "routes").mkdir(parents=True, exist_ok=True)
    (root / "app" / "routes" / "items.py").write_text("from app.db import engine\n\ndef list_items():\n    return []\n")
    (root / "app" / "db.py").write_text("engine = None\n")
    for n in range(others):
        (root / "app" / "routes" / f"widget_{n}.py").write_text(f"# widgets {n}\n" + "x = 1\n" * (size // 6))


def _specification(resources: list[str]) -> SimpleNamespace:
    endpoints = [f"{verb} /api/{name} - {what} {name}"
                 for name in resources for verb, what in (("GET", "lists"), ("POST", "creates"))]
    return SimpleNamespace(
        api_and_event_contracts=endpoints,
        data_contracts=[f"{name[:-1].capitalize()}: {{id, name, owner_id}}" for name in resources],
        error_catalogue=[f"404 when the {name[:-1]} does not exist" for name in resources],
        interface_design=["The page lists everything"],
    )


def _defects() -> list[Defect]:
    common = {"severity": "major", "reproduction_steps": "Run the acceptance suite.", "owner": "backend"}
    own = Defect(description="[AC-3] List items - the acceptance suite says this does not work yet.",
                 expected_behavior="List items", actual_behavior=STALE, affected_files=["app/routes/items.py"],
                 found_in_round=0, attempts=[{"stage": "defect_fix_1_0", "files": ["app/routes/items.py"],
                                              "outcome": "left open: its tests still fail"}], **common)
    cause = Defect(description="4 acceptance tests across 2 criteria stop at every request under `/api/items`, "
                               "answered 404.",
                   expected_behavior="The step answers as the interface says.",
                   actual_behavior="A prefix given twice answers 404 for every route under it.",
                   found_in_round=1, kind="failing_test",
                   evidence=[{"test": "[AC-3] lists items", "criterion": "AC-3"},
                             {"test": "[AC-4] creates an item", "criterion": "AC-4"}], **common)
    return [own, cause]


def _requested(root, monkeypatch, resources: list[str]) -> str:
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", "100000")
    monkeypatch.setenv("DECISION_LEDGER", "on")
    # The shared cause's own fixer has run this round, and left it open.
    state = the_fix_stage.a_state(root, *_defects(), technical_specification=_specification(resources),
                                  fixes_tried=["defect_fix_2_1"])
    _, seen = the_fix_stage.run(root, state, real_brief=True)
    return seen.requests[0]


def _target() -> int:
    from app.graph.fixer_request_shape import opening_target

    return opening_target()


def test_a_medium_request_opens_with_fresh_evidence_and_fits_its_target(tmp_path, monkeypatch):
    _project(tmp_path, others=40, size=4_000)
    _measured(tmp_path)
    resources = ["items", *(f"widget{n}s" for n in range(60))]

    request = _requested(tmp_path, monkeypatch, resources)

    assert request.startswith("A test failure has been assigned to you to fix.")
    assert "NEW LOG: KeyError: 'owner_id'" in request and "OLD LOG" not in request
    assert "no longer builds or starts" not in request
    # The round's shared cause is named, ahead of the standing context.
    assert request.index("stop at every request under `/api/items`") < request.index("GET /api/items")
    assert "GET /api/items - lists items" in request and "/api/widget1s" not in request
    # What is kept whole stays: the earlier attempt at this defect, as measured.
    assert "defect_fix_1_0" in request
    # The opening request is the request and the project memory the fixer is given with it.
    memory = project_memory.render_for_a_stage(tmp_path, None, request, "defect_fix_2_0")[0]
    assert len(request) + len(memory) <= _target()
    # The project memory holds the defect's file and what it imports, and names the rest.
    assert "=== app/routes/items.py ===" in memory and "=== app/db.py ===" in memory
    assert "=== app/routes/widget_7.py ===" not in memory


def test_a_small_request_is_as_built_with_its_evidence_fresh(tmp_path, monkeypatch):
    _project(tmp_path, others=2, size=300)
    _measured(tmp_path)

    request = _requested(tmp_path, monkeypatch, ["items", "widgets"])

    assert request.startswith("The workspace is rooted at '/'")
    assert request.index("--- Defect ---") < request.index("GET /api/items")
    assert "GET /api/widgets" in request and "The page lists everything" in request
    assert "NEW LOG: KeyError: 'owner_id'" in request and "OLD LOG" not in request
    assert "no longer builds or starts" not in request
    assert "[AC-3] lists items: AssertionError: assert 404 == 201" in request


def test_a_revert_note_about_a_start_that_still_fails_is_kept(tmp_path, monkeypatch):
    _project(tmp_path, others=2, size=300)
    _measured(tmp_path)
    ci.save(tmp_path, ci.Snapshot(label="latest", acceptance_ran=False, problem="The product did not start"))

    request = _requested(tmp_path, monkeypatch, ["items"])

    assert "no longer builds or starts" in request


def test_what_the_reshaped_request_says_names_no_product_word(tmp_path, monkeypatch):
    from app.graph import fixer_request_shape

    _project(tmp_path, others=40, size=4_000)
    _measured(tmp_path)
    request = _requested(tmp_path, monkeypatch, ["items", *(f"widget{n}s" for n in range(60))])
    said = [fixer_request_shape.STANDING_HEADING, request[request.index(fixer_request_shape.CAUSE_HEADING):][:900]]
    said += [line for line in request.splitlines() if line.startswith(("Only the routes", "Left out to keep"))]

    for text in said:
        assert not BANNED.search(text), text


def test_past_its_target_still_the_largest_standing_sections_go_and_the_evidence_never_does():
    from app.graph.fixer_request_shape import EVIDENCE, KEPT, STANDING, Part, shaped

    parts = [
        Part(STANDING, "--- The technology stack ---\n" + "stack line\n" * 300),
        Part(EVIDENCE, "--- Defect ---\nthe list answers 404\n" + "its output\n" * 400),
        Part(KEPT, "--- Earlier attempts ---\nchanged `app/x.py` -> left open\n"),
        Part(STANDING, "--- Where the data lives ---\nan embedded file\n"),
    ]

    request = shaped(parts, target=6_000, memory=1_000)

    assert request.startswith("--- Defect ---") and request.count("its output") == 400
    assert "left open" in request and "an embedded file" in request
    assert "stack line" not in request and "The technology stack" in request.split("Left out", 1)[1]


def test_a_shared_cause_s_fixer_is_shown_its_tests_as_the_latest_measurement_found_them(tmp_path, monkeypatch):
    """Such a defect names no criterion, so its fixer was shown the last failing command - perhaps another stage's."""
    _project(tmp_path, others=2, size=300)
    _measured(tmp_path)
    own, cause = _defects()
    state = the_fix_stage.a_state(tmp_path, cause, own, technical_specification=_specification(["items"]),
                                  fixes_tried=["defect_fix_2_1"])

    _, seen = the_fix_stage.run(tmp_path, state, real_brief=True)

    assert "--- What its failing tests printed ---" in seen.requests[0]
    assert "-> POST http://127.0.0.1:8000/api/items" in seen.requests[0]


def test_past_its_target_the_facts_keep_its_files_and_what_binds_every_stage():
    from app.agents.start_breaks import HEADING as START_BREAKS
    from app.graph.fixer_request_shape import KEPT, split_facts

    facts = ("\n\n--- The facts this work is built and judged under ---\n"
             "- The project lives in `./`.\n"
             "- Code the product does not run: `app/routes/widget_3.py` is imported by nothing.\n"
             "- Code the product does not run: `app/routes/items.py` is imported by nothing.\n"
             f"\n\n{START_BREAKS}\n- 2 fixes in a row changed the product so that it no longer started.\n")

    parts = split_facts(facts, {"app/routes/items.py"})
    cut = "".join(p.cut if p.cut is not None else p.text for p in parts)

    assert "app/routes/items.py" in cut and "widget_3" not in cut and "The project lives" in cut
    assert [p.kind for p in parts if "no longer started" in p.text] == [KEPT]
