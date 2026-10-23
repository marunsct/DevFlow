"""Resume a failed run the moment the model server answers again: `loop.sh resume-when-ready [run]`.

The owner's model server sometimes stops (a crash, a restart, the host's network). A run then fails with a
connection error and keeps its checkpoints; resuming it is refused while the model is unreachable and works
once it is back. This polls `loop.sh ready` and, on the first ALL READY, resumes the run in place with
`loop.sh resume`, so model time is not lost to the audit interval and an outage needs nobody awake. It starts
no model and changes no setting. Run it in the background; it ends after the resume, or after `--give-up-hours`.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

HERE = Path(__file__).resolve().parent
LOOP = str(HERE / "loop.sh")


def wait_and_resume(run: str, ready: Callable[[], bool], resume: Callable[[str], bool],
                    sleep: Callable[[float], None] = time.sleep, every: float = 60.0,
                    give_up_after: float | None = None, clock: Callable[[], float] = time.monotonic,
                    say: Callable[[str], None] = print) -> str:
    """"resumed", "gave up", or "refused" (the server answered but the resume was not accepted twice in a row)."""
    started = clock()
    refused = 0
    while True:
        if ready():
            if resume(run):
                say(f"resumed {run}")
                return "resumed"
            refused += 1
            say(f"the server answers but {run} was not resumed ({refused})")
            if refused >= 2:
                return "refused"
        else:
            refused = 0
        if give_up_after is not None and clock() - started >= give_up_after:
            return "gave up"
        sleep(every)


def _ready() -> bool:
    return subprocess.run([LOOP, "ready"], capture_output=True, text=True).returncode == 0


def _resume(run: str) -> bool:
    done = subprocess.run([LOOP, "resume", run], capture_output=True, text=True)
    return done.returncode == 0 and "resumed" in done.stdout.lower()


def main(argv: list[str]) -> int:
    run = next((a for a in argv[1:] if not a.startswith("--")), "")
    hours = next((float(a.split("=", 1)[1]) for a in argv[1:] if a.startswith("--give-up-hours=")), 36.0)
    if not run:
        print("usage: resume_when_ready.py <run> [--give-up-hours=36]")
        return 2
    result = wait_and_resume(run, _ready, _resume, give_up_after=hours * 3600)
    print(result)
    return 0 if result == "resumed" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
