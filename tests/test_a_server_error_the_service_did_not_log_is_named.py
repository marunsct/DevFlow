"""A test that met a 500 the service never logged is told so, and where such a 500 comes from.

Measured on one run: a catch-all error handler answered every failure with a bare 500 and logged nothing, the
service log held only its start-up lines, and two fix rounds and a re-planned sprint went at sign-in blind.
"""
from types import SimpleNamespace

from app.acceptance import suite


def _result(message):
    test = SimpleNamespace(name="test_signin", outcome="failed", message=message)
    return SimpleNamespace(report=SimpleNamespace(tests=[test]))


def _the_log(tmp_path, text):
    log = tmp_path / "tasks-api" / suite.SERVICE_LOG
    log.parent.mkdir(parents=True)
    log.write_text(text)


def test_a_500_with_nothing_logged_is_named(tmp_path, monkeypatch):
    monkeypatch.setattr(suite, "replace", lambda obj, **changes: SimpleNamespace(**{**vars(obj), **changes}))
    _the_log(tmp_path, "[INFO] Starting gunicorn 22.0.0\n[INFO] Booting worker with pid: 1\n")
    result = _result("assert 500 == 200  +  where 500 = <Response [500 INTERNAL SERVER ERROR]>")

    suite._with_the_errors_the_service_logged(tmp_path, "tasks-api", result)

    message = result.report.tests[0].message
    assert "logged no error" in message
    assert "without logging" in message


def test_a_logged_traceback_is_still_given_instead(tmp_path, monkeypatch):
    monkeypatch.setattr(suite, "replace", lambda obj, **changes: SimpleNamespace(**{**vars(obj), **changes}))
    _the_log(tmp_path, 'Traceback (most recent call last):\n  File "/w/tasks_api/auth.py", line 9\nValueError: bad salt\n')
    result = _result("assert 500 == 200")

    suite._with_the_errors_the_service_logged(tmp_path, "tasks-api", result)

    message = result.report.tests[0].message
    assert "ValueError: bad salt" in message and "logged no error" not in message


def test_the_note_uses_none_of_the_banned_words():
    import re

    assert not re.search(r"\b(task|tasks|to-do|todo|button|click|checkbox)\b", suite.UNLOGGED_SERVER_ERROR, re.I)
