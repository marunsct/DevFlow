"""The ten-minute audit prints what it could not see (HR2.O.1), and the impact report weighs mutation and quality
(HR2.E.5).

Measured on one day: 137 salvaged replies, 102 pause cancellations, 150 paused minutes and a 110:1 prefill:decode
stage, none of them on any audit line; `mutation_score` and `quality_score` were ledger columns in no comparison.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts" / "loop"


def test_the_audit_counts_salvage_cancellations_and_the_stage_s_ratio():
    text = (SCRIPTS / "audit_live.py").read_text(encoding="utf-8")
    for line in ("salvaged replies:", "cancelled by a pause", "prefill:decode in", "memory block"):
        assert line in text, line
    assert 'rec.get("salvaged")' in text and 'rec.get("finish_reason") == "length"' in text


def test_mutation_and_quality_are_impact_kpis_better_when_higher():
    spec = importlib.util.spec_from_file_location("impact", SCRIPTS / "impact.py")
    impact = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(impact)
    kpis = dict(impact.KPIS)
    assert kpis["mutation_score"] is False and kpis["quality_score"] is False
