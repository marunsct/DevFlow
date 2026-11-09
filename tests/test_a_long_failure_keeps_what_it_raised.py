"""A long test failure keeps its end - the exception raised - not only its first frames.

Measured on a run whose product stopped starting: pytest shortens a long message attribute to its first lines and
"[+35 more lines; full report in element text]", and the body was cut from its start, so eleven fixers in a row saw
neither the exception the service raised nor its last lines.
"""
from __future__ import annotations

from xml.sax.saxutils import escape

from app.acceptance.junit import MAX_MESSAGE_CHARS, parse

FRAMES = "\n".join(f'  File "/x/lib/module_{n}.py", line {n}, in call\n    do_{n}()' for n in range(80))


def _report(message: str, body: str) -> str:
    return ('<testsuite><testcase classname="acceptance.test_start" name="test_starts">'
            f'<failure message="{escape(message, {chr(34): "&quot;"})}">{escape(body)}</failure>'
            '</testcase></testsuite>')


def test_the_exception_at_the_end_of_a_long_traceback_is_kept():
    body = "Failed: The service did not start:\n" + FRAMES + "\nAttributeError: module 'app' has no attribute 'asgi'"
    message = "Failed: The service did not start:\n<module>\n[+35 more lines; full report in element text]"
    case = parse(_report(message, body)).tests[0]
    assert "has no attribute 'asgi'" in case.message
    assert "more lines; full report" not in case.message
    assert case.message.startswith("Failed: The service did not start:")
    assert len(case.message) <= MAX_MESSAGE_CHARS


def test_a_short_failure_is_kept_whole():
    case = parse(_report("assert 1 == 2", "def test(): assert 1 == 2\nE   assert 1 == 2")).tests[0]
    assert case.message == "def test(): assert 1 == 2\nE   assert 1 == 2"


def test_a_message_the_body_repeats_is_kept_once():
    """Measured live: every failure was printed twice - pytest's message, then a body that begins with it."""
    body = "assert 404 == 200\n +  where 404 = <Response [404 Not Found]>.status_code\nclient = <httpx.Client>"
    case = parse(_report("assert 404 == 200\n +  where 404 = <Response [404 Not Found]>.status_code", body)).tests[0]
    assert case.message == body
