"""The unit-test and acceptance-test documents of a finished run (plans DT.1, DT.6).

Runs on the host against a copy of the run's workspace - `loop.sh documents
<run>` makes the copy, leaving out what installs made:

    python scripts/loop/documents.py <workspace copy> <run> <out dir> [completion gaps JSON]

Writes `unit-test-report.md`, `acceptance-test-report.md` and `facts.json`
into the out dir. Harness-written from what the run recorded; no model.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from app.handover.facts import document_facts
from app.handover.test_documents import acceptance_test_document, unit_test_document


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print(__doc__)
        return 2
    workspace, run, out = Path(argv[1]), argv[2], Path(argv[3])
    try:
        gaps = json.loads(argv[4]) if len(argv) > 4 and argv[4].strip() else []
    except ValueError:
        gaps = []
    facts = document_facts(workspace, run_id=run, completion_gaps=gaps if isinstance(gaps, list) else [])
    out.mkdir(parents=True, exist_ok=True)
    (out / "facts.json").write_text(json.dumps(facts, indent=1), encoding="utf-8")
    (out / "unit-test-report.md").write_text(unit_test_document(facts), encoding="utf-8")
    (out / "acceptance-test-report.md").write_text(acceptance_test_document(facts), encoding="utf-8")
    print(f"{len(facts['unit_tests'])} unit tests, {len(facts['criteria'])} criteria -> {out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
