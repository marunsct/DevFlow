"""A stand-in runner for a setup's proof that reports the failure check's two tests as a working runner does (LF.1594).

A setup's proof runs each declared command once more with a failing and a raising test added
(`app.stacks.runner_check`); a stand-in that writes a fixed passing report would read as a runner that cannot report
a failure. `reporting_failures(run, root)` wraps such a stand-in: while those tests are in the project, every report
the command writes names both as failed, and the command exits 1.
"""

from __future__ import annotations

import re
from pathlib import Path

_CHECK = "*harness_failure_report_check*"
_BOTH = ("<testcase name='fails_on_purpose'><failure message='1 != 2'/></testcase>"
         "<testcase name='raises_on_purpose'><error message='RuntimeError'/></testcase>")


def reporting_failures(run, root):
    """`run`, answering as a runner that reports failures does; `root` is the directory commands run below."""
    def wrapped(argv, category, working_directory):
        project = Path(root) / working_directory
        checking = project.is_dir() and any(path.is_file() for path in project.rglob(_CHECK))
        before = set(project.rglob("*.xml")) if checking else set()
        outcome = run(argv, category, working_directory)
        if not checking:
            return outcome
        for report in set(project.rglob("*.xml")) - before:
            text = report.read_text(encoding="utf-8").rstrip()
            report.write_text(re.sub(r"(</testsuites?>)$", _BOTH + r"\1", text), encoding="utf-8")
        return {**outcome, "returncode": "1"}
    return wrapped
