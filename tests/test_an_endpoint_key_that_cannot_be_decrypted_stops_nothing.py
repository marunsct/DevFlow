"""A stored endpoint key that no longer decrypts is reported and skipped; it does not stop whoever asked for the keys.

Measured in the suite: `model_ready.py` ended in a NameError raised by the handler meant to catch this, so the check
that decides whether a run may start could not answer.
"""
from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock

from cryptography.fernet import Fernet

from app.server import auth, runtime_settings


def test_a_key_that_cannot_be_decrypted_is_left_out(monkeypatch):
    box = Fernet(Fernet.generate_key())
    good = box.encrypt(b"the-key").decode()
    cursor = MagicMock()
    cursor.fetchall.return_value = [("endpoint-a", "not a token"), ("endpoint-b", good)]
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor

    @contextmanager
    def connected():
        yield connection

    monkeypatch.setattr(auth, "get_db_connection", connected)
    monkeypatch.setattr(runtime_settings, "ensure_table", lambda *_: None)
    monkeypatch.setattr(runtime_settings, "_fernet", lambda: box)

    assert runtime_settings.endpoint_keys() == {"endpoint-b": "the-key"}
