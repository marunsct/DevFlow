"""Every finding a harness check raises against the acceptance suite, recorded with the check that raised it.

Harness review Q1: the suite's mechanical checks (about fifty) send it back to its writers, and nobody measured how
often each one was right - false findings held runs for hours (an unawaited-call check, a whole-page lookup check,
a shared-count check). Each finding is written here as the review raises it; `scripts/loop/check_precision.py`
reads every run's file and reports, per check, how often its finding was acted on and gone the next round (the
writers changed the test and the check agreed) and how often it came back unchanged or was overruled by a dispute.
Recording only: no finding is changed, dropped or added here.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

FILE = ".harness/check-findings.jsonl"
#: Test names a finding cites, so the report can tell whether the writers changed the test it was about.
_A_TEST_NAME = re.compile(r"`?(test_[A-Za-z0-9_]+|[A-Za-z0-9_./-]+\.(?:spec|test)\.[jt]sx?)`?")


def _fingerprint(text: str) -> str:
    """The finding with its numbers and quoted values taken out: the same finding again reads the same."""
    plain = re.sub(r"`[^`]*`|\"[^\"]*\"|\d+", "_", str(text))
    return hashlib.sha1(" ".join(plain.split()).encode("utf-8")).hexdigest()[:12]


def noted(root: str | Path, review_round: int, check: str, findings: Sequence[Any] | None) -> list[Any]:
    """`findings` unchanged, each one recorded under `check`. Never raises."""
    found = list(findings or [])
    if not found or not root:
        return found
    try:
        path = Path(root) / FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as out:
            for text in found:
                text = str(text)
                out.write(json.dumps({
                    "at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
                    "round": int(review_round or 0),
                    "check": check,
                    "fingerprint": _fingerprint(text),
                    "tests": sorted(set(_A_TEST_NAME.findall(text)))[:12],
                    "text": text[:600],
                }) + "\n")
    except Exception:  # noqa: BLE001 - a finding is sent back whether or not it is recorded
        logger.debug("Could not record a check's finding", exc_info=True)
    return found


def read(root: str | Path) -> list[dict[str, Any]]:
    """Every finding recorded in this workspace, oldest first; [] when none."""
    try:
        lines = (Path(root) / FILE).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows = []
    for line in lines:
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


__all__ = ["FILE", "noted", "read"]
