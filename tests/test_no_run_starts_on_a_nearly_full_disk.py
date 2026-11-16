"""No run starts on a nearly full disk, and the audit says how much is free (LR.3).

Measured twice: the disk the database lives on filled, Postgres stopped and every run failed; nothing checked the
space before a run started, and runs sat stopped for eleven hours.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GB = 1024 ** 3


def _disk_ready():
    spec = importlib.util.spec_from_file_location("disk_ready", ROOT / "scripts" / "loop" / "disk_ready.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_under_the_floor_is_refused_near_it_warned_and_above_it_ok():
    verdict = _disk_ready().verdict
    assert verdict("/d", 1000 * GB, 30 * GB, min_gb=50, min_percent=5)[0] == 1
    assert verdict("/d", 10000 * GB, 300 * GB, min_gb=50, min_percent=5)[0] == 1  # 3% free
    code, line = verdict("/d", 1000 * GB, 80 * GB, min_gb=50, min_percent=5)
    assert code == 0 and line.startswith("DISK LOW")
    assert verdict("/d", 1000 * GB, 400 * GB, min_gb=50, min_percent=5) == (0, "DISK OK /d: 400 GB free (40%)")


def test_ready_bench_and_audit_read_the_disk():
    loop = (ROOT / "scripts" / "loop" / "loop.sh").read_text()
    ready = loop[loop.index("\nready)"):loop.index("\nfitness)")]
    assert "disk_ready.py" in ready and 'echo "NOT ALL READY"' in ready
    bench = loop[loop.index("not starting: the disk is nearly full") - 200:]
    assert bench.index("disk_ready.py") < bench.index("model_ready.py")
    audit = loop[loop.index("\naudit)"):loop.index("\ndeep-audit)")]
    assert "disk_ready.py" in audit


def test_the_nightly_trims_only_the_model_server_s_old_or_huge_logs():
    loop = (ROOT / "scripts" / "loop" / "loop.sh").read_text()
    nightly = loop[loop.index("\nnightly)"):]
    nightly = nightly[:nightly.index("\n  ;;")]
    assert "-name '*.log'" in nightly and "-delete" in nightly and "server-logs" in nightly
    assert nightly.index("-delete") < nightly.index('"$0" backup')
