"""`ship-live` fails loudly when the deploy never replaced the containers.

Measured: Docker Desktop hung on a container create, the hung compose was stopped, the old worker kept running, and
`ship-live` resumed the runs and exited 0 with "running" - a deploy that did not land read as one that did.
"""
from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "loop" / "ship_live.sh"


def test_a_deploy_without_an_image_check_ends_non_zero():
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'grep -q "image matches" || landed=0' in text
    tail = text[text.index('if [ "$landed" = 0 ]'):]
    assert "DID NOT LAND" in tail and "exit 2" in tail
    assert text.index('deployed=$(') < text.index('for run in "${paused[@]}"; do\n  timeout 120 "$L" resume')
