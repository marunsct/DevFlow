"""A specification that writes its sign-up body with bare placeholders still gives the release probes a sign-in.

Measured on one run: the specification wrote `POST /signup — request body: {"username": <string>, "password":
<string>}`. The body reader kept nothing from it (a dash and "request body:" stood between the write and its body, and
`<string>` is neither JSON nor a quoted placeholder), so the probes had no body carrying a password, signed in as no
one, and every signed-in line answered 401: the release called a product that passed every hidden test broken.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.acceptance import interface_contract as ic

SIGN_UP = 'POST /signup — request body: {"username": <string>, "password": <string>}. Missing fields returns 400 with {"error": "missing fields"}.'
SIGN_IN = 'POST /signin — request body: {"username": <string>, "password": <string>}. Success returns 200 with {"token": <string>}.'


def _spec(*lines: str) -> SimpleNamespace:
    return SimpleNamespace(api_and_event_contracts=list(lines))


def test_a_body_after_a_dash_and_its_label_is_read_with_placeholder_fields():
    bodies = ic.example_bodies(_spec(SIGN_UP))

    assert {"username": "example", "password": "example"} in bodies


def test_a_body_written_straight_after_its_write_is_still_read():
    bodies = ic.example_bodies(_spec('POST /notes with {"title": "Buy milk"} returns 201 with {"id": 1}.'))

    assert bodies[0] == {"title": "Buy milk"}


def test_an_answer_body_after_a_status_is_not_read_as_a_request():
    assert not [m for m in ic._A_WRITE_WITH_ITS_BODY.finditer('POST /signup returns 409 with {"error": "taken"}')]  # noqa: SLF001


def test_the_probe_signs_in_with_the_body_the_specification_wrote():
    checks, _ = ic.parse(["AC-1 POST /signup -> 201", "AC-2 POST /signin -> 200", "AC-3 POST /items -> 201"])

    plan = ic.sign_in_plan(checks, ic.example_bodies(_spec(SIGN_UP, SIGN_IN)))

    assert plan is not None
    assert plan["signup"] == "/signup" and plan["signin"] == "/signin"
    assert set(plan["body"]) == {"username", "password"}


def test_a_placeholder_secret_is_sent_as_one_a_sign_up_with_rules_accepts():
    checks, _ = ic.parse(["AC-1 POST /signup -> 201", "AC-2 POST /signin -> 200"])

    plan = ic.sign_in_plan(checks, ic.example_bodies(_spec(SIGN_UP)))

    secret = plan["body"]["password"]
    assert secret != "example"
    assert len(secret) >= 12
    assert any(c.isupper() for c in secret) and any(c.isdigit() for c in secret) and any(not c.isalnum() for c in secret)


def test_a_secret_the_specification_gave_is_kept():
    checks, _ = ic.parse(["AC-1 POST /signup -> 201", "AC-2 POST /signin -> 200"])

    plan = ic.sign_in_plan(checks, [{"username": "ana", "password": "correct horse"}])

    assert plan["body"]["password"] == "correct horse"
