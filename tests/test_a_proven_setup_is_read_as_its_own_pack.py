"""Readers of the run's pack read it through the contract, so a proven custom setup is found too (harness review HR2.SS.6).

Five readers looked the pack up by name, which finds nothing for a proven custom setup: its support tier read as
"no pack fits" and its entry and served files were unknown to the checks that read them.
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace

from app.graph import delivery
from app.server import runs
from app.stacks import scaffold, support_tier


def test_a_proven_setup_has_its_own_support_tier() -> None:
    tier = support_tier(SimpleNamespace(name="proven-setup"))
    assert tier.startswith("Support tier: proven setup")
    assert "pack's scaffold" not in tier


def test_the_run_page_s_tier_reads_the_contract_s_pack(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("app.stacks.contract.read", lambda root: {"pack": "proven-setup", "project": "notes"})
    monkeypatch.setattr("app.stacks.contract.the_pack", lambda root: (SimpleNamespace(name="proven-setup"), {}))
    assert runs._support_tier_of(tmp_path).startswith("Support tier: proven setup")


def test_no_reader_looks_the_pack_up_by_its_recorded_name() -> None:
    for source in (inspect.getsource(scaffold), inspect.getsource(delivery), inspect.getsource(runs._support_tier_of)):
        assert 'pack_named(str(record.get("pack")' not in source
        assert 'pack_named(str((contract.read(repo_root)' not in source
