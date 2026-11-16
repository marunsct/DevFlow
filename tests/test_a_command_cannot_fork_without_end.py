"""A command the agents run cannot fork without end and take every run down (LR.40).

Found in the launch review: in in-container mode a command had data and file-size limits only; a fork bomb in one run's
command would exhaust the worker's processes and stop every run.
"""
from __future__ import annotations

import resource
import subprocess
import sys

from app.tools import sandbox


def test_the_child_gets_a_process_ceiling():
    done = subprocess.run([sys.executable, "-c", "import resource; print(resource.getrlimit(resource.RLIMIT_NPROC)[0])"],
                          capture_output=True, text=True, preexec_fn=sandbox._apply_limits)
    soft = int(done.stdout.strip())
    hard = resource.getrlimit(resource.RLIMIT_NPROC)[1]
    assert soft == (sandbox.MOST_PROCESSES if hard == resource.RLIM_INFINITY else min(sandbox.MOST_PROCESSES, hard))
    assert sandbox.MOST_PROCESSES >= 1024
