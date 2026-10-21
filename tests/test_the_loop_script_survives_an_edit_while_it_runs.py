"""`loop.sh` edited while one of its long commands runs does not fail when that command ends.

Bash reads a script as it goes: after a command it reads on from the byte where
that command ended. A deploy waited an hour for a stage boundary while
`loop.sh` was edited, and on finishing read the grown file from its old offset -
"syntax error near unexpected token `)'" at a line in the middle of another
command. The dispatch is one group, parsed whole, that exits inside itself.
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

LOOP = Path(__file__).resolve().parents[1] / "scripts" / "loop" / "loop.sh"


def test_an_edit_during_a_command_is_not_read_when_it_ends(tmp_path):
    text = LOOP.read_text()
    start = text.index('case "${1:-status}" in\n') + len('case "${1:-status}" in\n')
    end = text.rindex("\nesac\n") + 1
    script = tmp_path / "scripts" / "loop" / "loop.sh"
    script.parent.mkdir(parents=True)
    # The real preamble and the real framing; the commands replaced by one that waits.
    script.write_text(text[:start] + "wait) sleep 2 ;;\n" + text[end:])

    running = subprocess.Popen(["bash", str(script), "wait"], cwd=tmp_path,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(0.7)
    grown = script.read_text()
    script.write_text(grown.replace("wait) sleep 2 ;;\n", "wait) sleep 2 ;;\n" + "other) echo 'a (longer' ;;\n" * 40))
    out, err = running.communicate(timeout=30)

    assert running.returncode == 0 and "syntax error" not in err, err
