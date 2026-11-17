"""The bad-body probe sends bytes that cannot be parsed, not a JSON string of them (found live).

Measured on two runs (C# and Ruby): Playwright JSON-encodes a string `data` sent as `application/json`, so the probe
sent `"{\\"unparsable\\": "` - a valid JSON string - while its defect said "a JSON body that cannot be parsed". Both
products refused truly unparsable bytes with 422 (checked by hand); the probe kept failing them, and both sprints were
planned again chasing a case their fixers had already handled.
"""
from __future__ import annotations

from app.acceptance import interface_contract as ic


def _check():
    checks, _ = ic.parse(["AC-1 POST /notes -> 201"])
    return checks[0]


def test_the_playwright_probe_sends_raw_bytes():
    text = ic._a_bad_body_test('"t"', _check())
    assert f"data: Buffer.from({ic._js(ic.A_BODY_NOTHING_CAN_PARSE)})" in text
    assert f"data: {ic._js(ic.A_BODY_NOTHING_CAN_PARSE)}," not in text


def test_the_emptied_field_probe_still_sends_its_json_object():
    check = _check()
    from dataclasses import replace

    emptied = replace(check, emptied="title", blank=False)
    text = ic._an_emptied_field_test('"t"', emptied, [{"title": "a", "body": "b"}])
    assert 'data: {"title": "", "body": "b"}' in text and "Buffer.from" not in text
