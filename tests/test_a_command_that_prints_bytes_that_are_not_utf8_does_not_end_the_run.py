"""A command whose output holds bytes that are not UTF-8 is read with them replaced, never a crash of the run.

Measured on a Go run: its testing builder's command printed byte 0xb9 (not valid UTF-8); the sandbox read the output as
strict UTF-8, `UnicodeDecodeError` rose out of `subprocess` through the tool, and the whole run failed.
"""
from __future__ import annotations

import sys

from app.tools import sandbox


def test_output_with_a_byte_that_is_not_utf8_is_read_with_it_replaced(tmp_path):
    script = "import sys; sys.stdout.buffer.write(b'ok \\xb9 done\\n'); sys.stderr.buffer.write(b'\\xff\\n')"

    result = sandbox._run_and_watch_the_tree([sys.executable, "-c", script], cwd=str(tmp_path),
                                             env={"PATH": "/usr/bin:/bin"}, timeout=30)

    assert result.returncode == 0
    assert result.stdout.startswith("ok ") and result.stdout.rstrip().endswith("done")
    assert "�" in result.stdout
