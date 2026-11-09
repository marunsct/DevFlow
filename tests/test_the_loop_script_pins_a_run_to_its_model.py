"""`loop.sh` can start a run pinned to a model and pin or unpin a live run, and the script still parses."""

from __future__ import annotations

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "loop" / "loop.sh"


def test_the_script_parses():
    assert subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True).returncode == 0


def test_start_sends_the_pin_options_only_when_asked():
    """PIN_MODEL turns on `pin_model`; PIN_URL and PIN_MODEL_NAME ride along only with it."""
    text = SCRIPT.read_text()
    assert '${PIN_MODEL:+, \\"pin_model\\": true}' in text
    assert "pin_base_url" in text and "pin_model_name" in text


def test_pin_calls_the_endpoint_with_the_operator_login_and_no_key():
    """`pin on|off [run-id]` posts to model-pin with a bearer token from the loop operator account and nothing secret."""
    text = SCRIPT.read_text()
    block = text[text.index("\npin)"): text.index("\nrewind)")]
    assert "/model-pin" in block and "LOOP_USER" in block and "LOOP_PASSWORD" in block
    assert "api_key" not in block.lower()
    assert "usage: loop.sh pin on|off" in block
