"""The reasoning probe summarises replies honestly and sends nothing unless told to (plan item AR)."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("reasoning_probe_under_test", ROOT / "scripts/loop/reasoning_probe.py")
probe = importlib.util.module_from_spec(spec)
sys.modules["reasoning_probe_under_test"] = probe
spec.loader.exec_module(probe)


def _row(variant, tokens, reasoning, answer, finish="stop"):
    return {"variant": variant, "output_tokens": tokens, "reasoning_chars": reasoning, "answer_chars": answer, "finish_reason": finish}


def test_a_variant_that_halves_the_replies_is_honoured_and_a_lost_reply_is_counted():
    rows = [_row("baseline", 4000, 14000, 0, "length"), _row("baseline", 3000, 11000, 400),
            _row("effort_low", 900, 2000, 700), _row("effort_low", 1100, 2500, 800),
            _row("thinking_off", 3900, 13000, 0, "length"), _row("thinking_off", 3800, 12500, 200)]

    table = probe.summarise(rows)
    said = probe.honoured(table)

    assert [line["variant"] for line in table] == ["baseline", "effort_low", "thinking_off"]
    assert table[0]["lost_replies"] == 1 and table[1]["lost_replies"] == 0
    assert said.startswith("honoured by effort_low")
    assert "thinking_off" in said.split("\n", 1)[1]


def test_a_server_that_ignores_every_variant_is_reported_as_ignoring_them():
    rows = [_row(v, 3000, 10000, 300) for v in ("baseline", "baseline", "effort_low", "effort_low")]

    assert probe.honoured(probe.summarise(rows)).startswith("the server does not shorten replies")


def test_without_the_word_run_it_prints_the_plan_and_sends_nothing():
    done = subprocess.run([sys.executable, str(ROOT / "scripts/loop/reasoning_probe.py"), "plan"], capture_output=True, text=True)

    assert "Nothing was sent" in done.stdout and done.returncode == 0
